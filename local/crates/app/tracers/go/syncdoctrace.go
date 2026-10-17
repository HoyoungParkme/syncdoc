// Package syncdoctrace 는 싱크독의 Go 실행 기록 도우미다 (SYNC-INFRA-001 9.9 · SYNC-MS-027#trace.go_overlay, 카드 L34).
// view_arc 의 viewarctrace 를 옮겼다. `syncdoc-local trace`가 대상 모듈 안 패키지(<모듈>/syncdoctrace)로 겹쳐 넣고
// (go build -overlay), 계측한 함수 첫머리에서
//
//	defer syncdoctrace.Exit(syncdoctrace.Enter("파일:줄", "a", a, …))
//
// 로 부른다 — 첫 인자는 그래프 함수 열쇠다. 원본 파일은 고치지 않는다. 고루틴별 스택으로 부모를 정하고, *http.Request 를 받은
// 함수(gin·echo 의 문맥 포함)가 빈 스택에서 들어오면 요청 기록 하나를 연다(라우트 등록 때 핸들러를 돌려주는 함수가 시작 때
// 불려도 요청이 아니다). 기록 꼴은 다른 기록기와 같다(SYNCDOC_TRACE_OUT/<id>.json — 기록 도구가 올린다). 이름은
// SYNCDOC_TRACE_SPANS 의 이름 표에서.
// 값은 reflect 로 필드만 읽는다(String() 같은 메서드를 부르지 않는다 — 잠금을 쥔 채 부르면 교착될 수 있어서).
// recover 하지 않는다: 대상의 패닉 출력이 바뀌지 않게. 패닉으로 빠져나간 함수도 끝 시각은 남는다.
package syncdoctrace

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	maxEvents = 20000
	maxFiles  = 300
)

var (
	secret      = regexp.MustCompile(`(?i)pass|secret|token|api_?key|apikey|authoriz|credential|private`)
	secretField = regexp.MustCompile(`(?i)((?:\w*(?:pass|secret|token|api_?key|apikey|authoriz|credential|private)\w*)['"]?\s*[:=]\s*)('[^']*'|"[^"]*"|[^,)}\s]+)`)
	traceDir    = os.Getenv("SYNCDOC_TRACE_OUT")
	jobs        = os.Getenv("SYNCDOC_TRACE_JOB") == "1"
	namesOnce   sync.Once
	names       map[string]string
	mu          sync.Mutex
	writeMu     sync.Mutex
	stacks      = map[uint64][]*Tok{}
	seq         atomic.Int64
	requestType = reflect.TypeOf((*http.Request)(nil))
	writerType  = reflect.TypeOf((*http.ResponseWriter)(nil)).Elem()
)

type event struct {
	I      int               `json:"i"`
	Parent int               `json:"parent"`
	Fn     string            `json:"fn"`
	Name   string            `json:"name,omitempty"`
	Args   map[string]string `json:"args,omitempty"`
	T0     float64           `json:"t0"`
	T1     *float64          `json:"t1,omitempty"`
}

type rec struct {
	id, kind, method, path, query, startedAt string
	start                                    time.Time
	events                                   []*event
	truncated, done                          bool
}

// Tok 는 열린 호출 하나다. nil 이면 기록하지 않는 호출.
type Tok struct {
	r    *rec
	i    int
	gid  uint64
	root bool
	kv   []any
}

func goid() uint64 {
	var b [64]byte
	s := b[:runtime.Stack(b[:], false)]
	s = bytes.TrimPrefix(s, []byte("goroutine "))
	if i := bytes.IndexByte(s, ' '); i > 0 {
		id, _ := strconv.ParseUint(string(s[:i]), 10, 64)
		return id
	}
	return 0
}

func now(r *rec) float64 {
	return float64(time.Since(r.start).Microseconds()/10) / 100
}

// short: 그래프 함수 이름 — 범위 파일의 이름 표, 없으면 열쇠 그대로
func short(id string) string {
	namesOnce.Do(func() {
		var spans struct {
			Names map[string]string `json:"names"`
		}
		if b, err := os.ReadFile(os.Getenv("SYNCDOC_TRACE_SPANS")); err == nil {
			_ = json.Unmarshal(b, &spans)
		}
		names = spans.Names
	})
	if n, ok := names[id]; ok && n != "" {
		return n
	}
	return id
}

// Enter 는 함수 진입이다. kv 는 이름, 값, 이름, 값 …
func Enter(id string, kv ...any) *Tok {
	if traceDir == "" {
		return nil
	}
	g := goid()
	mu.Lock()
	defer mu.Unlock()
	st := stacks[g]
	var parent *Tok
	for k := len(st) - 1; k >= 0; k-- {
		if !st[k].r.done {
			parent = st[k]
			break
		}
	}
	var r *rec
	pi, root := -1, false
	if parent == nil {
		req := requestOf(kv)
		switch {
		case req != nil:
			r = newRec(req.Method, req.URL.Path, maskQuery(req.URL.RawQuery), "")
		case jobs:
			r = newRec("JOB", short(id), "", "job")
		default:
			return nil
		}
		root = true
	} else {
		r, pi = parent.r, parent.i
	}
	if len(r.events) >= maxEvents {
		r.truncated = true
		return nil
	}
	ev := &event{I: len(r.events), Parent: pi, Fn: id, Name: short(id), Args: args(kv), T0: now(r)}
	r.events = append(r.events, ev)
	t := &Tok{r: r, i: ev.I, gid: g, root: root, kv: kv}
	stacks[g] = append(st, t)
	return t
}

// Exit 는 함수 끝이다(defer 로 불린다).
func Exit(t *Tok) {
	if t == nil {
		return
	}
	mu.Lock()
	ev := t.r.events[t.i]
	end := now(t.r)
	ev.T1 = &end
	st := stacks[t.gid]
	for k := len(st) - 1; k >= 0; k-- {
		if st[k] == t {
			st = append(st[:k], st[k+1:]...)
			break
		}
	}
	if len(st) == 0 {
		delete(stacks, t.gid)
	} else {
		stacks[t.gid] = st
	}
	var done *rec
	var status *int
	if t.root {
		t.r.done = true
		done = t.r
		if t.r.kind == "job" {
			ok := 200
			status = &ok
		} else {
			status = statusOf(t.kv)
		}
	}
	mu.Unlock()
	if done != nil {
		write(done, status)
	}
}

func newRec(method, path, query, kind string) *rec {
	return &rec{
		id:        fmt.Sprintf("%d-%d-%d", time.Now().UnixMilli(), os.Getpid(), seq.Add(1)),
		kind:      kind,
		method:    method,
		path:      path,
		query:     query,
		startedAt: time.Now().UTC().Format("2006-01-02T15:04:05.000Z"), // 밀리초까지 — 다른 기록기와 같다
		start:     time.Now(),
	}
}

// requestOf: 인자 중 *http.Request — 그 자체, Request 필드(gin.Context), Request() 메서드(echo.Context)
func requestOf(kv []any) *http.Request {
	for k := 1; k < len(kv); k += 2 {
		if r, ok := kv[k].(*http.Request); ok && r != nil {
			return r
		}
		v := reflect.ValueOf(kv[k])
		if !v.IsValid() {
			continue
		}
		if v.Kind() == reflect.Pointer && !v.IsNil() && v.Elem().Kind() == reflect.Struct {
			if f := v.Elem().FieldByName("Request"); f.IsValid() && f.Type() == requestType && f.CanInterface() && !f.IsNil() {
				return f.Interface().(*http.Request)
			}
		}
		if m := v.MethodByName("Request"); m.IsValid() && m.Type().NumIn() == 0 && m.Type().NumOut() == 1 && m.Type().Out(0) == requestType {
			if r, ok := m.Call(nil)[0].Interface().(*http.Request); ok && r != nil {
				return r
			}
		}
	}
	return nil
}

// statusOf: 응답 상태 — net/http 의 응답(status 필드), gin 의 Writer.Status(), echo 의 Response().Status
func statusOf(kv []any) *int {
	for k := 1; k < len(kv); k += 2 {
		if s, ok := statusIn(reflect.ValueOf(kv[k]), 0); ok {
			return &s
		}
	}
	return nil
}

func statusIn(v reflect.Value, depth int) (int, bool) {
	if !v.IsValid() || depth > 2 {
		return 0, false
	}
	for v.Kind() == reflect.Interface || v.Kind() == reflect.Pointer {
		if v.IsNil() {
			return 0, false
		}
		v = v.Elem()
	}
	if v.Kind() != reflect.Struct {
		return 0, false
	}
	for _, name := range []string{"status", "Status"} {
		if f := v.FieldByName(name); f.IsValid() && f.CanInt() && f.Int() >= 100 && f.Int() < 600 {
			return int(f.Int()), true
		}
	}
	for _, name := range []string{"Writer", "ResponseWriter", "response", "Response"} {
		if f := v.FieldByName(name); f.IsValid() {
			if s, ok := statusIn(f, depth+1); ok {
				return s, true
			}
		}
	}
	return 0, false
}

func args(kv []any) map[string]string {
	if len(kv) < 2 {
		return nil
	}
	out := map[string]string{}
	for k := 0; k+1 < len(kv) && k < 12; k += 2 {
		name, _ := kv[k].(string)
		if secret.MatchString(name) {
			out[name] = "***"
			continue
		}
		out[name] = secretField.ReplaceAllString(repr(reflect.ValueOf(kv[k+1]), 0), "$1***")
	}
	return out
}

// repr: 필드만 읽는 짧은 표현(160자). 메서드를 부르지 않는다
func repr(v reflect.Value, depth int) string {
	s := reprRaw(v, depth)
	if len(s) > 160 {
		s = s[:157] + "…"
	}
	return s
}

func reprRaw(v reflect.Value, depth int) string {
	if !v.IsValid() {
		return "nil"
	}
	t := v.Type()
	if t.Implements(writerType) || (t.Kind() == reflect.Interface && t == writerType) {
		return "ResponseWriter"
	}
	if t == requestType && !v.IsNil() {
		r := (*http.Request)(v.UnsafePointer())
		return "Request(" + r.Method + " " + r.URL.Path + ")"
	}
	switch v.Kind() {
	case reflect.String:
		s := v.String()
		if len(s) > 60 {
			s = s[:59] + "…"
		}
		return strconv.Quote(s)
	case reflect.Bool:
		return strconv.FormatBool(v.Bool())
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return strconv.FormatInt(v.Int(), 10)
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64, reflect.Uintptr:
		return strconv.FormatUint(v.Uint(), 10)
	case reflect.Float32, reflect.Float64:
		return strconv.FormatFloat(v.Float(), 'g', 6, 64)
	case reflect.Pointer, reflect.Interface:
		if v.IsNil() {
			return "nil"
		}
		if depth > 2 {
			return t.String()
		}
		return reprRaw(v.Elem(), depth)
	case reflect.Slice, reflect.Array:
		return fmt.Sprintf("%s(%d)", t.String(), v.Len())
	case reflect.Map:
		return fmt.Sprintf("%s(%d)", t.String(), v.Len())
	case reflect.Func, reflect.Chan, reflect.UnsafePointer:
		return t.String()
	case reflect.Struct:
		if depth > 0 {
			return t.Name() + "{…}"
		}
		var b strings.Builder
		b.WriteString(t.Name() + "{")
		n := 0
		for k := 0; k < t.NumField() && n < 4; k++ {
			f := t.Field(k)
			if n > 0 {
				b.WriteString(", ")
			}
			n++
			if secret.MatchString(f.Name) {
				b.WriteString(f.Name + ": ***")
				continue
			}
			b.WriteString(f.Name + ": " + reprRaw(v.Field(k), depth+1))
		}
		if t.NumField() > 4 {
			b.WriteString(", …")
		}
		b.WriteString("}")
		return b.String()
	}
	return t.String()
}

func maskQuery(q string) string {
	if len(q) > 200 {
		q = q[:200]
	}
	return secretField.ReplaceAllString(q, "$1***")
}

func write(r *rec, status *int) {
	ms := now(r)
	for _, ev := range r.events {
		if ev.T1 == nil {
			e := ms
			ev.T1 = &e
		}
	}
	if r.kind == "job" && len(r.events) < 2 && ms < 50 {
		return // 아주 작은 작업
	}
	root := ""
	for _, ev := range r.events {
		if ev.Parent == -1 {
			root = ev.Fn
			break
		}
	}
	record := struct {
		Version   int      `json:"version"`
		Kind      string   `json:"kind,omitempty"`
		ID        string   `json:"id"`
		Method    string   `json:"method"`
		Path      string   `json:"path"`
		Query     string   `json:"query"`
		Status    *int     `json:"status"`
		Error     *string  `json:"error"`
		StartedAt string   `json:"startedAt"`
		Ms        float64  `json:"ms"`
		Truncated bool     `json:"truncated"`
		Events    []*event `json:"events"`
	}{1, r.kind, r.id, r.method, r.path, r.query, status, nil, r.startedAt, ms, r.truncated, r.events}
	summary := struct {
		ID        string  `json:"id"`
		Kind      string  `json:"kind,omitempty"`
		Method    string  `json:"method"`
		Path      string  `json:"path"`
		Status    *int    `json:"status"`
		Error     *string `json:"error"`
		StartedAt string  `json:"startedAt"`
		Ms        float64 `json:"ms"`
		Calls     int     `json:"calls"`
		Root      string  `json:"root"`
	}{r.id, r.kind, r.method, r.path, status, nil, r.startedAt, ms, len(r.events), root}
	body, err := json.Marshal(record)
	if err != nil {
		return
	}
	line, _ := json.Marshal(summary)
	writeMu.Lock()
	defer writeMu.Unlock()
	if err := os.MkdirAll(traceDir, 0o755); err != nil {
		return
	}
	tmp := filepath.Join(traceDir, "."+r.id+".tmp")
	if os.WriteFile(tmp, body, 0o644) != nil || os.Rename(tmp, filepath.Join(traceDir, r.id+".json")) != nil {
		fmt.Fprintln(os.Stderr, "[syncdoc] 기록을 쓰지 못했습니다")
		return
	}
	if f, err := os.OpenFile(filepath.Join(traceDir, "index.jsonl"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644); err == nil {
		_, _ = f.Write(append(line, '\n'))
		_ = f.Close()
	}
	prune()
}

func prune() {
	entries, err := os.ReadDir(traceDir)
	if err != nil {
		return
	}
	var names []string
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for k := 0; k < len(names)-maxFiles; k++ {
		_ = os.Remove(filepath.Join(traceDir, names[k]))
	}
}
