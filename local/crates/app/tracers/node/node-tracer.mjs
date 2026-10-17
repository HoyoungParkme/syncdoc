// 싱크독 Node 실행 기록기 (SYNC-INFRA-001 9.9, 카드 L29) — view_arc에서 옮겼다. `syncdoc-local trace`가
// NODE_OPTIONS=--import 로 서버 프로세스(와 그 자식 node)에 넣는다. 프로젝트 코드는 고치지 않는다.
//
// - 계측: 로더 훅(node-hooks.mjs)이 서버 파일의 함수 몸통을 __va.run 으로 감싼다(그래프 줄 범위로 고름 — 사건의 fn은
//   그래프 함수 열쇠 `파일:줄`). CommonJS 로 그대로 도는 .js 는 Module._compile 에서 같은 방식으로 감싼다.
// - 요청 구분: http.Server 의 'request' 를 AsyncLocalStorage 문맥으로 감싼다. 함수의 부모는 그 문맥의 함수.
// - 경계 호출: 밖으로 나가는 소켓에 쓰는 순간을 fn="@infra" 사건으로 남긴다(상대 호스트:포트와 짧은 동작 이름만 —
//   헤더·값·비밀번호는 남기지 않는다).
// - 기록: 요청마다 SYNCDOC_TRACE_OUT/<id>.json — 기록 도구가 서버로 올린다.
// - 작업(SYNCDOC_TRACE_JOB=1): 요청 문맥 밖에서 불린 프로젝트 함수 하나가 작업 기록 하나.
//
// 환경변수: SYNCDOC_TRACE_OUT · SYNCDOC_TRACE_SPANS(계측할 함수 범위·라우트·이름·장비 주소, 기록 도구가 만든다) · SYNCDOC_TRACE_JOB

import { AsyncLocalStorage } from 'node:async_hooks'
import fs from 'node:fs'
import http from 'node:http'
import Module, { register, SourceMap } from 'node:module'
import net from 'node:net'
import path from 'node:path'
import { instrumentBundle, instrumentNode } from './node-instrument.mjs'

const TRACE_DIR = process.env.SYNCDOC_TRACE_OUT
const SPANS = process.env.SYNCDOC_TRACE_SPANS
const MAX_EVENTS = 20000
const MAX_FILES = 300
const JOBS = process.env.SYNCDOC_TRACE_JOB === '1'
const SPLIT_MS = 2000 // 작업의 맨 위 함수가 이보다 오래 열려 있으면 직접 부른 한 단위씩 끊는다

// setup 이 채운다: 파일별 감쌀 함수 범위, 라우트 핸들러 id, 기록 번호
let FILES = {}
let ROUTE_IDS = new Set()
let NAMES = {}
let seq = 0
const als = new AsyncLocalStorage()
const SECRET = /pass|secret|token|api_?key|apikey|authoriz|credential|private/i // 이런 이름의 값은 기록하지 않는다
const ASSET = /^\/(@vite|@fs|@id|@react-refresh|node_modules|src)\/|\.(js|mjs|ts|tsx|css|map|png|jpe?g|svg|ico|woff2?|html)(\?|$)/

if (TRACE_DIR && SPANS && !globalThis.__va) {
  try {
    setup(JSON.parse(fs.readFileSync(SPANS, 'utf-8')))
  } catch (error) {
    process.stderr.write(`[syncdoc] Node 실행 기록을 켜지 못했습니다: ${error?.message ?? error}\n`)
  }
}

function setup({ files, routes, hosts, names }) {
  FILES = files
  ROUTE_IDS = new Set(routes)
  NAMES = names ?? {}

  // ------------------------------------------------------------ 함수 진입·끝
  globalThis.__va = {
    /** 진입: 요청 문맥 밖(서버 시작 때 등)이면 기록하지 않는다. 작업 기록을 켜면 그런 호출이 작업 하나를 연다 */
    e(fn, args) {
      let store = als.getStore()
      let rec = store?.rec
      if (!rec || rec.done) {
        // 끝난 요청이 남긴 타이머·콜백도 새 작업(끝난 기록에 붙이지 않는다)
        if (!JOBS) return null
        rec = openJob(fn)
        store = null
      }
      if (rec.events.length >= MAX_EVENTS) {
        rec.truncated = true
        return null
      }
      // 라우트 핸들러는 맨 위: 미들웨어의 next() 안에서 불려도 미들웨어의 자식이 아니다(FastAPI 의 Depends 처럼 나란히)
      const ev = { i: rec.events.length, parent: store?.tok && !ROUTE_IDS.has(fn) ? store.tok.i : -1, fn, t0: now(rec) }
      if (args) {
        ev.args = {}
        for (const k of Object.keys(args)) ev.args[k] = SECRET.test(k) ? '***' : repr(args[k])
      }
      rec.events.push(ev)
      return { rec, i: ev.i }
    },
    /** 몸통을 이 호출의 문맥에서 돌리고 끝(반환값·예외)을 남긴다. 비동기면 끝날 때 */
    run(tok, body) {
      if (!tok) return body()
      return als.run({ rec: tok.rec, tok }, () => {
        try {
          const r = body()
          if (r && typeof r.then === 'function')
            return r.then(
              (v) => (end(tok, v), v),
              (e) => {
                end(tok, undefined, e)
                throw e
              }
            )
          end(tok, r)
          return r
        } catch (e) {
          end(tok, undefined, e)
          throw e
        }
      })
    },
  }

  // ------------------------------------------------------------ 계측 등록
  register('./node-hooks.mjs', import.meta.url, { data: { files } })
  const compile = Module.prototype._compile
  Module.prototype._compile = function (content, filename) {
    return compile.call(this, compileHook(content, filename), filename)
  }

  // ------------------------------------------------------------ 요청
  const emit = http.Server.prototype.emit
  http.Server.prototype.emit = function (event, req, res) {
    if (event !== 'request' || !req || !res) return emit.apply(this, arguments)
    const url = new URL(req.url ?? '/', 'http://x')
    const rec = {
      id: `${Date.now()}-${process.pid}-${++seq}`,
      method: req.method ?? 'GET',
      path: url.pathname,
      query: url.search.slice(1),
      startedAt: new Date().toISOString(),
      start: performance.now(),
      events: [],
      truncated: false,
      done: false,
    }
    const done = () => finish(rec, res.statusCode)
    res.once('finish', done)
    res.once('close', done)
    return als.run({ rec, tok: null }, () => emit.apply(this, arguments))
  }

  // ------------------------------------------------------------ 경계 호출(밖으로 나가는 소켓)
  const connect = net.Socket.prototype.connect
  net.Socket.prototype.connect = function (...args) {
    try {
      let opts = args[0]
      if (Array.isArray(opts)) opts = opts[0] // 내부에서 정리된 인자
      let host
      let port
      if (opts && typeof opts === 'object') {
        host = opts.servername || opts.host || 'localhost'
        port = opts.port
        if (opts.path) host = opts.path
      } else if (typeof opts === 'number' || /^\d+$/.test(String(opts))) {
        port = Number(opts)
        host = typeof args[1] === 'string' ? args[1] : 'localhost'
      }
      if (host) this.__vaRemote = { host: String(host), port: port ? Number(port) : undefined, tls: !!(opts && typeof opts === 'object' && (opts.servername || opts.ALPNProtocols)) }
    } catch {
      // 모르면 기록하지 않는다
    }
    return connect.apply(this, args)
  }
  const write = net.Socket.prototype.write
  net.Socket.prototype.write = function (chunk) {
    if (this.__vaRemote) io(this, chunk)
    return write.apply(this, arguments)
  }

  function io(socket, chunk) {
    const store = als.getStore()
    const rec = store?.rec
    if (!rec || rec.done) return
    // 한 왕복(쓰기 여러 번 → 응답) 은 사건 하나: 응답이 오기 전 같은 소켓의 쓰기는 합친다
    if (socket.__vaPending && socket.__vaPending.rec === rec) return
    if (rec.events.length >= MAX_EVENTS) return
    const said = describe(chunk)
    const { kind, target, sure } = classify(socket.__vaRemote, said.kind)
    // 무엇인지 모르는 쓰기(DB 접속 인사·인증 같은 이진 메시지)는 남기지 않는다
    if (!said.op && !sure) return
    const op = said.op || kind
    const ev = { i: rec.events.length, parent: store.tok ? store.tok.i : -1, fn: '@infra', name: op.slice(0, 60), infra: { kind, target, op }, t0: now(rec) }
    rec.events.push(ev)
    socket.__vaPending = { rec, ev }
    socket.once('data', () => {
      if (ev.t1 === undefined) ev.t1 = now(rec)
      socket.__vaPending = null
    })
  }

  /**
   * 상대 주소 → 장비 종류: 보낸 내용(SQL·Redis 명령·HTTP 요청 줄) > 분석에서 찾은 장비 주소 > 잘 알려진 포트.
   * sure: 내용 없이도 장비로 가는 것이 확실(알려진 장비 주소·포트)
   */
  function classify({ host, port, tls }, sniffed) {
    const hostPort = port ? `${host}:${port}` : host
    const local = ['localhost', '127.0.0.1', '::1'].includes(host)
    const known = hosts[hostPort] ?? (local ? hosts[`localhost:${port}`] ?? hosts[`127.0.0.1:${port}`] : undefined)
    const byPort = port === 5432 || port === 3306 || port === 27017 || port === 1433 || port === 26257 ? 'db' : port === 6379 || port === 6380 ? 'redis' : undefined
    // HTTP 로 말하는 상대는 분석이 저장소(MinIO)라고 했으면 저장소
    const kind = sniffed === 'http' ? (known === 's3' ? 's3' : 'http') : sniffed ?? known ?? byPort ?? 'http'
    const scheme = port === 27017 ? 'mongodb' : port === 7687 ? 'bolt' : kind === 'http' || kind === 's3' ? (tls || port === 443 ? 'https' : 'http') : kind === 'redis' ? 'redis' : 'postgresql'
    return { kind, target: `${scheme}://${hostPort}`, sure: !!(known || byPort) }
  }

  /** 보낸 내용에서 동작 이름만: SQL 첫 부분, HTTP 요청 줄(쿼리 빼고), Redis 명령 이름. 값·헤더는 남기지 않는다 */
  function describe(chunk) {
    let text = ''
    try {
      text = typeof chunk === 'string' ? chunk : Buffer.from(chunk.buffer ?? chunk, chunk.byteOffset ?? 0, chunk.byteLength ?? chunk.length).toString('latin1')
    } catch {
      return { op: '' }
    }
    const http = /^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) (\S+) HTTP\/1/.exec(text)
    if (http) return { kind: 'http', op: `${http[1]} ${http[2].split('?')[0]}` }
    const sql = /\b(SELECT|INSERT|UPDATE|DELETE|WITH|BEGIN|COMMIT|ROLLBACK|CREATE|ALTER)\b[\x20-\x7e\n\t]*/i.exec(text)
    if (sql) return { kind: 'db', op: sql[0].replace(/\s+/g, ' ').slice(0, 100) }
    const redis = /^\*\d+\r\n\$\d+\r\n(\w+)/.exec(text)
    if (redis) return { kind: 'redis', op: redis[1].toUpperCase() }
    return { op: '' }
  }
}

function end(tok, ret, err) {
  const ev = tok.rec.events[tok.i]
  if (!ev || ev.t1 !== undefined) return
  ev.t1 = now(tok.rec)
  if (err !== undefined) ev.exc = err instanceof Error ? `${err.name}: ${String(err.message).slice(0, 120)}` : repr(err)
  else ev.ret = repr(ret)
  if (tok.rec.kind !== 'job') return
  if (tok.i === 0) finish(tok.rec, err !== undefined ? 500 : 200)
  else if (ev.parent === 0) splitJob(tok.rec, tok.i)
}

/** 작업 기록 하나(요청 문맥 밖에서 불린 프로젝트 함수) */
function openJob(fn) {
  return {
    id: `${Date.now()}-${process.pid}-${++seq}`,
    kind: 'job',
    method: 'JOB',
    path: NAMES[fn] ?? fn,
    query: '',
    startedAt: new Date().toISOString(),
    start: performance.now(),
    events: [],
    truncated: false,
    done: false,
  }
}

/** 오래 도는 작업에서 맨 위 함수가 직접 부른 한 단위(i 부터)를 따로 기록하고 이 기록에서 뗀다 */
function splitJob(rec, i) {
  if (now(rec) <= SPLIT_MS) return
  for (let k = i + 1; k < rec.events.length; k++) if (rec.events[k].t1 === undefined) return // 뒤에 열린 호출(동시 작업)이 있으면 번호가 꼬인다
  const part = rec.events.slice(i)
  rec.events.length = i
  const first = part[0]
  if (part.length < 2 && first.t1 - first.t0 < 50) return // 아주 짧은 한 번(대기·확인)은 남기지 않는다
  const base = first.t0
  const child = openJob(first.fn)
  child.start = rec.start + base
  child.startedAt = new Date(Date.now() - (performance.now() - child.start)).toISOString()
  for (const e of part) {
    e.i -= i
    e.parent = e.parent < i ? -1 : e.parent - i
    e.t0 = +(e.t0 - base).toFixed(2)
    if (e.t1 !== undefined) e.t1 = +(e.t1 - base).toFixed(2)
  }
  child.events = part
  finish(child, first.exc ? 500 : 200)
}

/** CommonJS 컴파일 직전: 그래프에 있는 .js(줄이 같은 원본) · Next 서버 묶음(소스맵으로 원본 줄). 실패하면 원본 */
function compileHook(content, filename) {
  try {
    const spans = FILES[filename]
    if (spans && /\.c?js$/.test(filename)) return instrumentNode(content, filename, spans) ?? content
    if (filename.includes(`${path.sep}.next${path.sep}`) && content.includes('"[project]/')) {
      const map = bundleMap(content, filename)
      if (map) return instrumentBundle(content, filename, FILES, map) ?? content
    }
  } catch {
    // 원본으로
  }
  return content
}

function finish(rec, status) {
  if (rec.done) return
  rec.done = true
  if (!rec.events.length) return
  const ms = now(rec)
  for (const e of rec.events) if (e.t1 === undefined) e.t1 = ms
  const job = rec.kind === 'job'
  if (job && rec.events.length < 2 && ms < 50) return // 시작 때 잠깐 불린 함수 같은 아주 작은 작업
  const tops = rec.events.filter((e) => e.parent === -1 && e.fn !== '@infra')
  const root = job ? (tops[0]?.fn ?? null) : (tops.find((e) => ROUTE_IDS.has(e.fn))?.fn ?? null)
  if (!root && ASSET.test(rec.path)) return // 화면 파일 요청(Vite 미들웨어 …)
  const top = tops.find((e) => e.fn === root)
  const record = {
    version: 1,
    ...(job ? { kind: 'job' } : {}),
    id: rec.id,
    method: rec.method,
    path: rec.path,
    query: rec.query,
    status: status ?? null,
    error: top?.exc ?? null,
    startedAt: rec.startedAt,
    ms,
    truncated: rec.truncated,
    events: rec.events,
  }
  const summary = { id: rec.id, ...(job ? { kind: 'job' } : {}), method: rec.method, path: rec.path, status: record.status, error: record.error, startedAt: rec.startedAt, ms, calls: rec.events.length, root: root ?? tops.at(-1)?.fn ?? null }
  try {
    fs.mkdirSync(TRACE_DIR, { recursive: true })
    const tmp = path.join(TRACE_DIR, `.${rec.id}.tmp`)
    fs.writeFileSync(tmp, JSON.stringify(record))
    fs.renameSync(tmp, path.join(TRACE_DIR, `${rec.id}.json`))
    fs.appendFileSync(path.join(TRACE_DIR, 'index.jsonl'), JSON.stringify(summary) + '\n')
    prune()
  } catch (error) {
    process.stderr.write(`[syncdoc] 기록을 쓰지 못했습니다: ${error?.message ?? error}\n`)
  }
}

/** 묶음의 소스맵: sourceMappingURL(이름이 % 로 감싸여 있다) 또는 옆의 .map */
function bundleMap(content, filename) {
  const url = /\/\/# sourceMappingURL=(\S+)\s*$/.exec(content)?.[1]
  const file = url && !url.startsWith('data:') ? path.resolve(path.dirname(filename), decodeURIComponent(url)) : `${filename}.map`
  try {
    return new SourceMap(JSON.parse(fs.readFileSync(file, 'utf-8')))
  } catch {
    return null
  }
}

function now(rec) {
  return +(performance.now() - rec.start).toFixed(2)
}

/** 문자열 안의 비밀 칸(password=…, "token": "…")도 가린다 */
const SECRET_FIELD = /((?:\w*(?:pass|secret|token|api_?key|apikey|authoriz|credential|private)\w*)['"]?\s*[:=]\s*)('[^']*'|"[^"]*"|[^,)}\s]+)/gi

function repr(value, depth = 0) {
  const text = reprRaw(value, depth)
  return depth ? text : text.replace(SECRET_FIELD, '$1***')
}

function reprRaw(value, depth) {
  try {
    if (value === undefined) return 'undefined'
    if (value === null) return 'null'
    const t = typeof value
    if (t === 'string') return JSON.stringify(value.length > 60 ? value.slice(0, 59) + '…' : value)
    if (t === 'number' || t === 'boolean' || t === 'bigint') return String(value)
    if (t === 'function') return `ƒ ${value.name || 'anonymous'}`
    if (value instanceof Error) return `${value.name}: ${String(value.message).slice(0, 80)}`
    if (typeof value.then === 'function') return 'Promise'
    const ctor = value.constructor?.name
    if (ctor === 'IncomingMessage') return `Request(${value.method} ${String(value.originalUrl ?? value.url).split('?')[0]})`
    if (ctor === 'ServerResponse') return 'Response'
    if (Buffer.isBuffer(value)) return `Buffer(${value.length})`
    if (depth > 1) return Array.isArray(value) ? `Array(${value.length})` : '{…}'
    if (Array.isArray(value)) return `[${value.slice(0, 4).map((v) => reprRaw(v, depth + 1)).join(', ')}${value.length > 4 ? `, …(${value.length})` : ''}]`
    const keys = Object.keys(value)
    const name = ctor && ctor !== 'Object' ? ctor + ' ' : ''
    const body = keys.slice(0, 4).map((k) => `${k}: ${SECRET.test(k) ? '***' : reprRaw(value[k], depth + 1)}`)
    return `${name}{${body.join(', ')}${keys.length > 4 ? ', …' : ''}}`.slice(0, 160)
  } catch {
    return '?'
  }
}

function prune() {
  const files = fs.readdirSync(TRACE_DIR).filter((f) => f.endsWith('.json')).sort()
  for (const f of files.slice(0, -MAX_FILES)) {
    try {
      fs.unlinkSync(path.join(TRACE_DIR, f))
    } catch {
      // 이미 지워짐
    }
  }
}
