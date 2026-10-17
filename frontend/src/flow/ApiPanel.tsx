/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 6.1 API 목록 · 6.2 실행 · 6.3 API 상세 · 6.4 열·깊이 · 6.5 이 API 흐름 재생 ·
 *  6.6 요청 보내기 · 6.7 층 위반 · 6.8 층 지도 — view_arc api-panel·request-panel을 옮겼다(카드 CG).
 *  층은 명세 층 표가 정한다 — view_arc의 「끌어 놓아 옮기기」(view_arc.json 쓰기)는 가져오지 않는다(UI-001 7장 18).
 *  요청 보내기는 싱크독_로컬만(POST /api/local/request, INFRA C14) — 싱크독_깃허브는 curl 명령 복사. */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { GraphNode } from './types'
import type { ArchMap } from './arch'
import type { ApiFlow, FlowOptions } from './flow'
import { type Model, displayName } from './model'

const WRITE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/** 6.1 — API 목록. 경로 앞부분(api·v1을 건너뛴 첫 칸)으로 묶는다 */
export function ApiList({ model, selected, local, runs, onSelect, onRun }: { model: Model; selected: string | null; local: boolean; runs: (id: string) => number; onSelect: (id: string) => void; onRun: (id: string) => void }) {
  const [q, setQ] = useState('')
  const groups = useMemo(() => {
    const t = q.trim().toLowerCase()
    const routes = model.graph.nodes.filter((n) => n.route && (!t || `${n.route.method} ${n.route.path} ${n.name}`.toLowerCase().includes(t)))
    const by = new Map<string, GraphNode[]>()
    for (const r of routes) {
      const segs = r.route!.path.split('/').filter((s) => s && !/^(api|v\d+)$/i.test(s) && !s.includes('{'))
      const key = segs[0] ?? '/'
      by.set(key, [...(by.get(key) ?? []), r])
    }
    return [...by.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [model, q])
  const senders = (id: string) => (model.in.get(id) ?? []).filter((e) => e.kind === 'http').length
  const firstId = groups[0]?.[1][0]?.id
  return (
    <aside className="cgtree fvlist" data-el="6.1">
      <div className="th">
        <input className="inp" placeholder="API 찾기 — 경로·방법·함수" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {groups.length === 0 && <div className="meta pad">API가 없습니다</div>}
      {groups.map(([group, routes]) => (
        <div key={group}>
          <div className="g">{group}</div>
          {routes.map((r) => {
            const front = senders(r.id)
            const n = runs(r.id)
            return (
              <div key={r.id} className={`api${selected === r.id ? ' on' : ''}`} onClick={() => onSelect(r.id)} title={`${displayName(r)} · ${r.path}:${r.line}`}>
                <span className={`m m-${r.route!.method}`}>{r.route!.method}</span>
                <span className="p">
                  {r.route!.path}
                  <span className="sub">
                    {r.name}
                    {front ? ` · 화면 ${front}곳` : ''}
                  </span>
                </span>
                {n > 0 && <span className="cnt">{n}</span>}
                <span
                  className="run"
                  data-el={r.id === firstId ? '6.2' : undefined}
                  title={local ? '실행 — 이 PC의 개발 서버로 요청을 보낸다' : '명령 복사 — 같은 요청의 curl'}
                  onClick={(e) => {
                    e.stopPropagation()
                    onRun(r.id)
                  }}
                >
                  {local ? '▶' : '복사'}
                </span>
              </div>
            )
          })}
        </div>
      ))}
    </aside>
  )
}

/** 6.3~6.8 — 고른 API의 상세 */
export function ApiDetail({
  code,
  model,
  arch,
  flow,
  options,
  local,
  requestOpen,
  classDoc,
  onOptions,
  onSelect,
  onTrace,
  children,
}: {
  code: string
  model: Model
  arch: ArchMap
  flow: ApiFlow
  options: FlowOptions
  local: boolean
  requestOpen: boolean
  classDoc: string | null
  onOptions: (o: FlowOptions) => void
  onSelect: (id: string) => void
  onTrace: () => void
  children?: React.ReactNode
}) {
  const route = model.byId.get(flow.routeId)!
  const front = (model.in.get(route.id) ?? []).filter((e) => e.kind === 'http').length
  return (
    <>
      <div className="k">API 흐름</div>
      <div data-el="6.3">
        <div className="nm">
          <span className={`m-${route.route!.method}`}>{route.route!.method}</span> {route.route!.path}
        </div>
        <div className="meta">
          {displayName(route)} · {route.path}:{route.line} · 함수 {flow.size}
          {front ? ` · 화면 호출 ${front}` : ''}
        </div>
      </div>
      <div className="fvopts" data-el="6.4">
        열
        <span className="seg">
          {(
            [
              ['layer', '층'],
              ['depth', '호출 깊이'],
            ] as const
          ).map(([v, label]) => (
            <span key={v} className={options.groupBy === v ? 'on' : ''} onClick={() => onOptions({ ...options, groupBy: v })}>
              {label}
            </span>
          ))}
        </span>
        깊이
        <span className="seg">
          {[1, 2, 3, 4, 5, 6].map((d) => (
            <span key={d} className={options.maxDepth === d ? 'on' : ''} onClick={() => onOptions({ ...options, maxDepth: d })}>
              {d}
            </span>
          ))}
        </span>
        <label>
          <input type="checkbox" checked={options.trivial} onChange={(e) => onOptions({ ...options, trivial: e.target.checked })} /> 생성자·예외
          {flow.hidden > 0 && !options.trivial ? ` (숨김 ${flow.hidden})` : ''}
        </label>
      </div>
      <span className="btn sm fvplay" data-el="6.5" onClick={onTrace}>
        ▶ 이 API 흐름 재생
      </span>
      <RequestPanel key={`${route.id}:${requestOpen ? 1 : 0}`} route={route} local={local} open={requestOpen} />
      {children}
      <Violations model={model} flow={flow} onSelect={onSelect} />
      <div className="k">열</div>
      {flow.columns.map((col) => (
        <div key={col.depth}>
          <div className="row head">
            {col.layer && <i className="dot" style={{ background: col.layer.color }} />}
            {col.title}
            <span className="st">{col.ids.length}</span>
          </div>
          {col.ids.map((id) => {
            const n = model.byId.get(id)!
            return (
              <div className="row" key={id} title={arch.reason.get(id)} onClick={() => onSelect(id)}>
                {displayName(n)}
                <span className="st">{n.path.split('/').slice(-2).join('/')}</span>
              </div>
            )
          })}
        </div>
      ))}
      <LayerMap code={code} arch={arch} classDoc={classDoc} />
    </>
  )
}

/** 6.6 — 요청 보내기. 싱크독_로컬은 서버가 대신 보내고(localhost만), 싱크독_깃허브는 curl 명령을 복사한다 */
function RequestPanel({ route, local, open }: { route: GraphNode; local: boolean; open: boolean }) {
  const method = route.route!.method === 'ANY' ? 'GET' : route.route!.method
  const vars = useMemo(() => [...route.route!.path.matchAll(/\{(\w+)(?::[^}]*)?\}/g)].map((m) => m[1]), [route])
  const [port, setPort] = useState(() => readPort())
  const [values, setValues] = useState<Record<string, string>>({})
  const [query, setQuery] = useState('')
  const [body, setBody] = useState('{}')
  const [sure, setSure] = useState(false)
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ status?: number; ms?: number; body?: string; truncated?: boolean; error?: string } | null>(null)
  const write = WRITE.has(method)
  const path = route.route!.path.replace(/\{(\w+)(?::[^}]*)?\}/g, (_, n: string) => encodeURIComponent(values[n] ?? '')) + (query.trim() ? `?${query.trim().replace(/^\?/, '')}` : '')
  const url = `http://localhost:${port}${path}`
  const ready = /^\d+$/.test(port) && vars.every((v) => values[v]?.trim()) && (!write || sure)
  const curl = `curl -X ${method} '${url}'${write && method !== 'DELETE' ? ` -H 'Content-Type: application/json' -d '${body.replace(/'/g, "'\\''")}'` : ''}`
  const send = async () => {
    setSending(true)
    setResult(null)
    writePort(port)
    try {
      setResult(await api.post('/api/local/request', { method, url, body: write && method !== 'DELETE' ? body : null }))
    } catch (e) {
      setResult({ error: e instanceof ApiError ? (e.problem.detail ?? e.problem.title) : String(e) })
    } finally {
      setSending(false)
    }
  }
  return (
    <details className="fvreq" data-el="6.6" open={open}>
      <summary>요청 보내기 — {local ? '이 PC의 개발 서버로' : '명령 복사(싱크독_로컬에서는 바로 보낸다)'}</summary>
      <div className="meta">
        http://localhost:
        <input className="inp port" value={port} onChange={(e) => setPort(e.target.value.trim())} />
        {path}
      </div>
      {vars.map((v) => (
        <label key={v} className="fld">
          <span>{`{${v}}`}</span>
          <input className="inp" value={values[v] ?? ''} onChange={(e) => setValues({ ...values, [v]: e.target.value })} />
        </label>
      ))}
      <label className="fld">
        <span>쿼리</span>
        <input className="inp" value={query} placeholder="limit=10" onChange={(e) => setQuery(e.target.value)} />
      </label>
      {write && method !== 'DELETE' && <textarea className="inp body" rows={4} spellCheck={false} value={body} onChange={(e) => setBody(e.target.value)} />}
      {write && (
        <label className="sure">
          <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} /> 쓰기 요청({method})을 보냅니다 — 그 서버의 DB·파일이 바뀔 수 있다
        </label>
      )}
      {local ? (
        <span className={`btn sm solid${!ready || sending ? ' disabled' : ''}`} onClick={() => ready && !sending && send()}>
          {sending ? '보내는 중…' : '보내기'}
        </span>
      ) : (
        <span className="btn sm" onClick={() => navigator.clipboard?.writeText(curl)}>
          명령 복사
        </span>
      )}
      {!local && <pre className="cmd">{curl}</pre>}
      {result &&
        (result.error ? (
          <div className="meta bad">{result.error}</div>
        ) : (
          <>
            <div className="meta">
              {result.status} · {result.ms}ms{result.truncated ? ' · 1MB에서 잘림' : ''} — 기록을 켠 서버면 곧 기록 목록에 들어온다
            </div>
            <pre className="cmd">{result.body}</pre>
          </>
        ))}
    </details>
  )
}

const PORT_KEY = 'syncdoc.flow.port'
function readPort(): string {
  try {
    return localStorage.getItem(PORT_KEY) ?? '8000'
  } catch {
    return '8000'
  }
}
function writePort(p: string) {
  try {
    localStorage.setItem(PORT_KEY, p)
  } catch {
    // 저장이 막힌 브라우저 — 다음에 다시 적으면 된다
  }
}

/** 6.7 — 층 위반: 아래 층이 위를 부르거나(거꾸로) 관례상 거칠 층을 건너뛴 호출 */
function Violations({ model, flow, onSelect }: { model: Model; flow: ApiFlow; onSelect: (id: string) => void }) {
  const bad = flow.edges.filter((e) => e.violation)
  return (
    <>
      <div className="k">층 위반 {bad.length}</div>
      <div data-el="6.7">
        {bad.length === 0 && <div className="meta">없음 — 이 흐름의 호출이 층 순서를 지킨다</div>}
        {bad.map((e) => {
          const a = model.byId.get(e.from)!
          const b = model.byId.get(e.to)!
          const v = e.violation!
          const label = v.startsWith('rule:') ? `규칙 「${v.slice(5)}」` : v === 'back' ? '거꾸로' : a.layer === 'frontend' ? '훅·상태 건너뜀' : '서비스 건너뜀'
          return (
            <div className="row bad" key={e.from + e.to} onClick={() => onSelect(e.from)}>
              {displayName(a)} → {displayName(b)}
              <span className="st">{label}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

/** 6.8 — 층 지도: 층의 출처(명세 층 표 또는 짐작)와 나눈 비율 */
function LayerMap({ code, arch, classDoc }: { code: string; arch: ArchMap; classDoc: string | null }) {
  const { classified, total } = arch.coverage
  const pct = total ? Math.round((classified / total) * 100) : 0
  const fromSpec = arch.source?.kind === 'spec'
  const rows = Object.keys(arch.source?.config.assign ?? {}).length
  return (
    <>
      <div className="k">층 지도</div>
      <div className="meta" data-el="6.8">
        {fromSpec ? (
          <>
            {classDoc ? <Link to={`/p/${code}/d/${classDoc}`}>클래스 명세 「폴더 구조」 층 표</Link> : '클래스 명세 「폴더 구조」 층 표'} · 꼴 {rows}개 · 나머지는 짐작
          </>
        ) : (
          '짐작 — 층 표가 없어 이름과 호출 방향으로 나눴다'
        )}{' '}
        · 서버 함수 {classified}/{total}({pct}%)
        <div className="layers">
          {arch.layers.map((l) => (
            <span key={l.id} title={l.tier === null ? '위반 판정 안 함' : `층 ${l.tier}`}>
              <i className="dot" style={{ background: l.color }} />
              {l.name} {l.count}
            </span>
          ))}
        </div>
      </div>
    </>
  )
}
