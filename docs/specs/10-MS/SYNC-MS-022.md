---
doc_id: SYNC-MS-022
type: MS
title: MINISPEC — codegraph — 코드 호출 그래프와 명세 대조 (Rust)
status: approved
upstream: [SYNC-DOM-004, SYNC-MS-011, SYNC-INFRA-001, SYNC-STD-004]
---

# MINISPEC — codegraph (싱크독_로컬 Rust)

## 0. 이 문서가 다루는 것

`crates/codegraph`(순수 함수 — DB 없음)와 `crates/core/src/codegraph`(`CodeGraphService`)의 함수(목록은 1장). 클래스 명세 [[SYNC-DOM-004]] 4.11. 파이썬 판 [[SYNC-MS-011]]과 **같은 이름·같은 처리·같은 그래프 모양**이고, 이 문서는 다른 점만 적는다([[SYNC-STD-001]] 2.10). 「호출하는 것」과 테스트 관점은 제 것을 적는다.

**카드 L12 몫은 추출·줄이기·보강·대조·층과 그래프 행이다(2026-10-11).** 커뮤니티(Louvain·허브 라벨)는 카드 L13이 이 문서에 더한다 — 그 전에는 함수마다 `community`가 없고(null) `communities`가 빈 목록이다.

**graphify가 없다**([[SYNC-INFRA-001]] 9.2 — graphify는 파이썬 전용이다). 그래서
- 저장소에 커밋된 `graphify-out/graph.json`이 있으면 파이썬 판처럼 그것을 원형으로 쓴다([[#codegraph.load]]) — 그때 두 판의 그래프는 같은 원형에서 같은 줄이기·보강을 거쳐 **바이트까지 같다**. 에이전트 판단 2026-10-11(사용자 목표 「끝까지」) — [[SYNC-CODE-002]] 4장 미결을 이렇게 닫았다
- 없으면 [[#codegraph.extract]]가 graphify 대신 원형을 만든다 — 파이썬·TS/JS·Rust 파일을 tree-sitter로 읽어 graphify의 노드·선 모양으로. graphify의 이름 풀이를 다 옮기지 않으므로 **호출 선은 파이썬 판과 다를 수 있다**(보강이 잡는 선은 같다). 화면·대조의 모양은 같다

**파이썬 `ast` 대신 tree-sitter-python**(0.25.0 — graphify가 쓰는 판). 보강이 `ast`로 읽는 것(맨 위 정의·클래스 메서드·데코레이터 줄·끝 줄·docstring·인자 주석·대입·속성·호출·import)을 같은 뜻으로 읽는다 — 끝 줄은 주석을 뺀 마지막 문장의 끝, docstring은 `inspect.cleandoc`을 거친 첫 줄, 걷는 차례는 `ast.walk`처럼 너비 우선. `ast.parse`가 실패할 파일(문법 오류 — tree-sitter의 `ERROR`·`MISSING`)은 건너뛴다. TS/JS(tree-sitter-typescript 0.23.2)·Rust(tree-sitter-rust 0.24.2)는 파이썬 판과 같은 문법 판이라 같은 나무다.

**그래프 모양** — [[SYNC-MS-011]] 0장 그대로(`functions`·`calls`·`communities`). `Graph { functions: Vec<Function>, calls: Vec<Call>, communities: Vec<Community>, files: Vec<String> }` — `files`는 줄이기가 주고 보강이 쓰고 비운다(저장 모양에 없다). `Function { key, name, qual, file, line, end, item, ms, community }` · `Call = (from, to, via)`.

**표기** — `→` 반환·결과, `!` 예외(`Problem`), `DB:` 테이블 접근, `git:` [[SYNC-MS-019]], `·` 같은 단계 안 구분.

---

## 1. 함수 목록

| 함수 | 한 줄 |
|---|---|
| [[#codegraph.touches_code]] | 바뀐 경로에 코드 파일이 있나 |
| [[#codegraph.load]] | 저장소의 graph.json이 있으면 그것, 없으면 추출 |
| [[#codegraph.extract]] | graphify 대신 — tree-sitter로 원형을 만든다 |
| [[#codegraph.reduce]] | 함수·호출 선만 남긴다 |
| [[#codegraph.enrich]] | 파이썬·TS/JS·Rust 코드로 그래프를 보강한다 |
| [[#codegraph.spec_calls]] | 명세의 「호출하는 것」을 항목 ID 집합으로 |
| [[#codegraph.compare]] | 명세 호출과 코드 호출을 같음·코드만·명세만으로 |
| [[#codegraph.item_function]] | 항목 ID → 그 항목의 함수 |
| [[#codegraph.item_neighbors]] | 항목 있는 함수까지의 부르는 것·불리는 곳 |
| [[#codegraph.layer_table]] | 클래스 명세 「폴더 구조」 절의 층 표를 읽는다 |
| [[#codegraph.layers]] | 항목 없는 함수마다 층 |
| [[#CodeGraphService.get]] | 프로젝트의 그래프 행 |
| [[#CodeGraphService.save]] | 새 그래프로 바꿔 끼운다 |
| [[#CodeGraphService.fail]] | 실패 이유만 남긴다 — 옛 그래프는 그대로 |
| [[#CodeGraphService.read]] | 그래프 커밋의 파일을 줄 범위로 — 비밀 꼴 거부, 300줄 |

---

## 2. 함수

#### codegraph.touches_code 바뀐 경로에 코드 파일이 있나

**시그니처**
```rust
pub fn touches_code(paths: &[String]) -> bool
```

근거: [[SYNC-MS-011#codegraph.touches_code]]

**처리** [[SYNC-MS-011#codegraph.touches_code]]와 같다 — `docs/specs/`·`graphify-out/` 아래를 빼고 확장자(소문자)가 `CODE_EXTS`에 드는 경로가 하나라도 있으면 참

**테스트 관점** 명세 md만 → 거짓 · `.py` 하나 → 참 · `docs/specs/assets/x.js` → 거짓 · `graphify-out/graph.json` → 거짓 · `a/graphify-out/x.py` → 거짓 · `X.RS` → 참

---

#### codegraph.load 저장소의 graph.json 또는 추출

**시그니처**
```rust
pub fn load(src_dir: &Path) -> Result<(String, Value), CodeGraphFailed>
```

근거: [[SYNC-MS-011#codegraph.load]]

**처리** `src_dir/graphify-out/graph.json`이 파일이면 `("repo", 그 JSON)` — JSON이 아니면 `! CodeGraphFailed("graph.json 형식")` · 아니면 `("server", extract(src_dir))`

**다른 점** 추출은 graphify가 아니라 [[#codegraph.extract]]다 · `CodeGraphFailed`는 이 crate의 오류(문장 하나)다 — 부르는 쪽([[SYNC-MS-017#pipeline.build_code_graph]])이 그래프 행의 `error`로 남긴다

**호출하는 것** [[#codegraph.extract]]

**테스트 관점** graph.json이 있으면 `repo`와 그 원형 · 없으면 `server` · 깨진 graph.json → `graph.json 형식`

---

#### codegraph.extract graphify 대신 — tree-sitter로 원형을 만든다

**시그니처**
```rust
pub fn extract(src_dir: &Path) -> Result<Value, CodeGraphFailed>
```

근거: [[SYNC-INFRA-001]] 9.2 · [[SYNC-MS-009#graphify.extract]]

**처리** graphify `graph.json`(node-link)의 모양으로 — 줄이기·보강·커뮤니티가 읽는 것만
1. 파일 — `src_dir` 아래를 걸어(`.git`·`graphify-out`·`node_modules`·`target` 폴더는 빼고) 경로 순으로, 확장자가 `.py .ts .tsx .js .jsx .mjs .rs`인 파일마다 파일 노드 `{id: 경로, label: 이름, file_type: "code", source_file: 경로}`
2. 파이썬 파일 — tree-sitter-python으로 읽어(문법 오류면 파일 노드만) 맨 위 `def`(데코레이터를 벗겨)·`class`, 클래스 몸통의 `def`마다 노드 — 함수 `{id: "{경로}:{줄}", label: "{이름}()", file_type: "code", source_file, source_location: "L{def 줄}", _callable: true}` · 클래스 `{…, label: 이름, _callable_class: true}` · 선 `contains`(파일 → 맨 위 함수·클래스) · `method`(클래스 → 메서드)
3. 파이썬 호출 — 맨 위 함수·메서드 몸통의 `f(…)`(이름 호출)마다 같은 파일 맨 위 함수 `f`가 있으면 선 `{source, target, relation: "calls", confidence: "EXTRACTED"}` — 같은 쌍은 하나
4. TS/JS·Rust는 파일 노드만 — 정의·끝 줄·호출은 [[#codegraph.enrich]]가 다 채운다(파이썬 판도 graphify의 Rust 함수는 `_callable`이 없어 보강이 다 채운다)
5. `→ {"directed": false, "multigraph": false, "graph": {}, "nodes": […], "links": […]}`

**다른 점** graphify(파이썬 판)의 이름 풀이·중첩 함수·다른 언어 23종은 옮기지 않는다 — 파이썬은 같은 파일의 이름 호출만, 나머지 호출은 보강이 잇는다. 그래서 graph.json이 없는 저장소는 호출 선이 파이썬 판보다 적을 수 있다(0장)

**예외** `src_dir`이 폴더가 아니면 `! CodeGraphFailed("폴더 없음: {이름}")`

**테스트 관점** 파이썬 맨 위 함수·데코레이터 함수·클래스 메서드가 함수 노드, 줄은 `def` 줄 · 같은 파일 이름 호출이 `calls` · 문법 오류 파일은 파일 노드만 · `.ts`·`.rs`는 파일 노드만 · `node_modules`·`.git`은 안 걷는다 · 줄이기 → 보강을 거치면 맨 위 함수·메서드가 다 있다

---

#### codegraph.reduce 함수·호출 선만 남긴다

**시그니처**
```rust
pub fn reduce(raw: &Value) -> Graph
```

근거: [[SYNC-MS-011#codegraph.reduce]]

**처리** [[SYNC-MS-011#codegraph.reduce]]와 같다 — 노드는 `id`마다 마지막 것이 그 자리(파이썬 `dict`) · 선은 `links`(없으면 `edges`) · `method` 선으로 소속 클래스, `rationale_for` 선으로 docstring 항목 · `_callable`이고 `_callable_class`가 아닌 노드가 함수(테스트 파일 빼고, 같은 key는 하나) · `calls`·`indirect_call` 선 중 `confidence`가 `INFERRED`가 아니고 양 끝이 함수인 것 · `files` = `file_type == code`인 노드의 `source_file`(테스트 빼고 정렬)

**테스트 관점** [[SYNC-MS-011#codegraph.reduce]]의 것 · 파이썬 판이 같은 원형으로 낸 답과 바이트로 같다

---

#### codegraph.enrich 파이썬·TS/JS·Rust 코드로 그래프를 보강한다

**시그니처**
```rust
pub fn enrich(src_dir: &Path, graph: Graph) -> Graph
```

근거: [[SYNC-MS-011#codegraph.enrich]]

**처리** [[SYNC-MS-011#codegraph.enrich]] 1~6과 같은 차례·같은 규칙 — 파이썬(1·2·4·5) · TS/JS 2a~2d · 화면 ID 3 · Rust 2e~2h. 더하기만 하고, 깨진 파일은 건너뛰고, `files`를 쓰고 비운다

**다른 점** 파이썬 파일은 `ast` 대신 tree-sitter-python으로 읽는다(0장) — 정의는 모듈 맨 위와 클래스 몸통(데코레이터를 벗겨), 머리 줄은 `def` 줄과 데코레이터 줄들, 끝 줄은 주석을 뺀 마지막 문장의 끝, docstring은 몸통 첫 문장이 글자 상수(접두어 `r`·`u`, 이어 붙인 상수는 이어서, `b`·`f`는 아니다)일 때 `cleandoc`한 첫 줄. 대입·속성은 너비 우선으로 걷고, 속성은 대입·`del`·`for`의 과녁이 아닐 때만 읽기다

**테스트 관점** [[SYNC-MS-011#codegraph.enrich]]의 것 전부 · 파이썬 판이 같은 원형·같은 파일로 낸 답과 바이트로 같다(싱크독 저장소의 graph.json으로 — 정답 파일)

---

#### codegraph.spec_calls 명세의 「호출하는 것」

**시그니처**
```rust
pub fn spec_calls(items: &[(String, String)], impl_of: Option<&HashMap<String, String>>) -> BTreeMap<String, BTreeSet<String>>
```

근거: [[SYNC-MS-011#codegraph.spec_calls]]

**처리** [[SYNC-MS-011#codegraph.spec_calls]]와 같다

**테스트 관점** [[SYNC-MS-011#codegraph.spec_calls]]의 것

---

#### codegraph.compare 명세 호출과 코드 호출을 가른다

**시그니처**
```rust
pub fn compare(graph: &Graph, spec: &BTreeMap<String, BTreeSet<String>>) -> Vec<CallDiff>
```

근거: [[SYNC-MS-011#codegraph.compare]]

**처리** [[SYNC-MS-011#codegraph.compare]]와 같다 — `CallDiff { ms_id, function, same, code_only, spec_only }`

**테스트 관점** [[SYNC-MS-011#codegraph.compare]]의 것

---

#### codegraph.item_function 항목 ID로 그 항목의 함수

**시그니처**
```rust
pub fn item_function<'g>(graph: &'g Graph, item_id: &str) -> Option<&'g Function>
```

근거: [[SYNC-MS-011#codegraph.item_function]]

**처리** [[SYNC-MS-011#codegraph.item_function]]와 같다

**테스트 관점** [[SYNC-MS-011#codegraph.item_function]]의 것

---

#### codegraph.item_neighbors 항목 있는 함수까지의 부르는 것·불리는 곳

**시그니처**
```rust
pub fn item_neighbors(graph: &Graph, key: &str) -> (Vec<String>, Vec<String>)
```

근거: [[SYNC-MS-011#codegraph.item_neighbors]]

**처리** [[SYNC-MS-011#codegraph.item_neighbors]]와 같다 — 걷는 차례(더미의 꼭대기부터, 이웃은 선 차례)까지

**테스트 관점** [[SYNC-MS-011#codegraph.item_neighbors]]의 것

---

#### codegraph.layer_table 클래스 명세의 층 표를 읽는다

**시그니처**
```rust
pub fn layer_table(body: &str) -> Vec<LayerRow>
```

근거: [[SYNC-MS-011#codegraph.layer_table]]

**처리** [[SYNC-MS-011#codegraph.layer_table]]와 같다 — `LayerRow { patterns, name, specs: [LayerSpec { ref, note }], line }`

**테스트 관점** [[SYNC-MS-011#codegraph.layer_table]]의 것

---

#### codegraph.layers 항목 없는 함수마다 층

**시그니처**
```rust
pub fn layers(graph: &Graph, rows: &[LayerRow]) -> (HashMap<String, Layer>, Vec<LayerRow>)
```

근거: [[SYNC-MS-011#codegraph.layers]]

**처리** [[SYNC-MS-011#codegraph.layers]]와 같다 — `Layer { name, specs }`

**테스트 관점** [[SYNC-MS-011#codegraph.layers]]의 것

---

#### CodeGraphService.get 프로젝트의 그래프 행

**시그니처**
```rust
pub async fn get(&mut self, project_id: i32) -> Result<Option<CodeGraphRow>, Problem>
```

근거: [[SYNC-MS-011#CodeGraphService.get]]

**처리** `DB: code_graphs where project_id` → 행 또는 없음

**테스트 관점** 없으면 없음

---

#### CodeGraphService.save 새 그래프로 바꿔 끼운다

**시그니처**
```rust
pub async fn save(&mut self, project_id: i32, commit_hash: &str, source: &str, graph: &Graph) -> Result<CodeGraphRow, Problem>
```

근거: [[SYNC-MS-011#CodeGraphService.save]]

**처리** [[SYNC-MS-011#CodeGraphService.save]]와 같다 — 행이 없으면 만들고, 있으면 커밋·출처·그래프·함수 수·선 수·`built_at=now`를 한 번에, `error`는 비운다

**테스트 관점** 두 번 저장하면 행 하나, 뒤의 것 · 앞의 `error`가 지워진다 · 개수 열이 맞다

---

#### CodeGraphService.fail 실패 이유만 남긴다

**시그니처**
```rust
pub async fn fail(&mut self, project_id: i32, commit_hash: &str, reason: &str) -> Result<CodeGraphRow, Problem>
```

근거: [[SYNC-MS-011#CodeGraphService.fail]]

**처리** [[SYNC-MS-011#CodeGraphService.fail]]와 같다 — `error = "{커밋 앞 7자}: {reason}"`의 앞 300자. 행이 없으면 빈 그래프·커밋·출처 없이, `built_at=now`

**테스트 관점** 성공 뒤 실패 → 옛 그래프가 남고 `error`만 · 첫 빌드부터 실패 → 빈 그래프 + `error` · 300자에서 자른다

---

#### CodeGraphService.read 그래프 커밋의 파일을 줄 범위로

**시그니처**
```rust
pub async fn read(&mut self, git: &Git, project_id: i32, workdir: &Path, path: &str, start: i64, end: Option<i64>) -> Result<CodeText, Problem>
```

근거: [[SYNC-MS-011#CodeGraphService.read]]

**처리** [[SYNC-MS-011#CodeGraphService.read]]와 같다 — 그래프가 없거나 커밋이 없으면 `! NotFound(code_graph, 프로젝트 id)` · 경로는 `\`를 `/`로 바꿔 `PurePosixPath`처럼 다듬는다(빈 조각·`.`을 버린다) — 절대 경로·`..` 조각·빈 경로·비밀 꼴(이름 소문자로 `DENY`)은 `! NotFound(file, 받은 path)` · `git.read(workdir, 다듬은 경로, 그래프 커밋)` — 실패하면 같은 `not-found` · 줄은 파이썬 `splitlines` · `start = max(1, start)` · `end = min(줄 수, end가 0이 아니면 end, 아니면 줄 수)` · `end - start + 1`이 300을 넘으면 `end = start + 299`·`truncated` · `→ CodeText { path: 다듬은 경로, start, end, commit_hash, text: start..=end 줄을 \n로 이은 것, truncated }`

**다른 점** git 어댑터를 받는다(파이썬은 모듈 함수)

**호출하는 것** [[#CodeGraphService.get]] · [[SYNC-MS-019#Git.read]]

**테스트 관점** 그래프 커밋의 내용이다(뒤에 바뀐 것이 아니다) · 300줄에서 자르고 `truncated` · `.env`·`id_rsa`·`secrets.yaml`·`../x`·절대 경로 → `not-found` · 그래프 없음 → `not-found`

---

## 3. 미결사항

없음. 커뮤니티는 카드 L13이 더한다 — [[SYNC-CODE-002]].
