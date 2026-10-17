/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 7.1 기록 머리 · 7.2 재생 조작 · 7.3 사건 목록 — view_arc trace-panel을 옮겼다(카드 CG).
 *  코드에서 읽은 흐름(5.5·6.5)과 실행 기록(5.3)이 같은 패널이다. 3D 재생과 맞춰 지금 단계를 밝힌다. */
import { useEffect, useRef } from 'react'
import type { TraceBrief } from '../api/client'
import type { GraphNode } from './types'
import { type Model, type TraceEvent, type TraceOptions, displayName } from './model'

export type Branch = { n: number; of: number; color: string }
export type TraceState = {
  rootId: string
  events: TraceEvent[]
  index: number
  playing: boolean
  runtime?: TraceBrief // 있으면 실제 실행 기록, 없으면 코드에서 읽은 흐름
  result?: string
  via?: string
  branch?: Branch
}

const SPEEDS = [0.5, 1, 2, 4]

type Props = {
  model: Model
  trace: TraceState
  options: TraceOptions
  speed: number
  follow: boolean
  onPlay: () => void
  onPause: () => void
  onSeek: (index: number) => void
  onSpeed: (speed: number) => void
  onFollow: (follow: boolean) => void
  onOptions: (options: TraceOptions) => void
  onClose: () => void
}

export function TracePanel(props: Props) {
  const { model, trace, options, speed, follow } = props
  const root = model.byId.get(trace.rootId)
  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${trace.index}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [trace.index])
  const calls = trace.events.filter((e) => e.type === 'call').length
  const skipped = trace.events.filter((e) => e.type === 'skipped').length
  const rt = trace.runtime
  return (
    <div className="fvtrace">
      <div className="k">
        {rt ? '실행 기록' : '호출 흐름 · 코드에서 읽음'}
        <span className="btn sm" onClick={props.onClose}>
          닫기
        </span>
      </div>
      <div data-el="7.1">
        <div className="nm">
          {rt ? `${rt.method ?? '작업'} ${rt.path}` : root ? displayName(root) : trace.rootId}
          {rt && <span className={`st ${rt.status && rt.status < 400 ? 'same' : 'code_only'}`}> {rt.status ?? 'ERR'}</span>}
        </div>
        <div className="meta">
          {rt ? (
            <>
              {trace.branch && <span style={{ color: trace.branch.color }}>갈래 {trace.branch.n}{trace.branch.of > 1 ? `/${trace.branch.of}` : ''} · </span>}
              {rt.ms}ms · 호출 {calls}
              {skipped > 0 && ` · 안 탄 호출 ${skipped}`}
              {rt.commit_hash && ` · ${rt.commit_hash.slice(0, 7)}`}
              {rt.truncated && ' · 잘림'}
              {rt.kind === 'job' && ' · 작업'}
              {rt.kind === 'front' && ' · 화면'}
              {trace.via && ` · ${trace.via}`}
            </>
          ) : (
            <>
              호출 {calls} · 단계 {trace.events.length}
            </>
          )}
        </div>
        {trace.result && <div className={`meta ${trace.result.startsWith('✕') ? 'bad' : ''}`}>응답 ← {trace.result}</div>}
      </div>
      <div className="fvctl" data-el="7.2">
        <span className="btn sm" onClick={() => props.onSeek(-1)} title="처음으로">
          처음
        </span>
        <span className="btn sm" onClick={() => props.onSeek(Math.max(-1, trace.index - 1))} title="이전 단계">
          ◀
        </span>
        <span className="btn sm solid" onClick={trace.playing ? props.onPause : props.onPlay}>
          {trace.playing ? '멈춤' : '▶ 재생'}
        </span>
        <span className="btn sm" onClick={() => props.onSeek(Math.min(trace.events.length - 1, trace.index + 1))} title="다음 단계">
          ▶
        </span>
        <span className="seg">
          {SPEEDS.map((s) => (
            <span key={s} className={speed === s ? 'on' : ''} onClick={() => props.onSpeed(s)}>
              {s}×
            </span>
          ))}
        </span>
      </div>
      <div className="fvopts">
        <label>
          <input type="checkbox" checked={follow} onChange={(e) => props.onFollow(e.target.checked)} /> 카메라 따라가기
        </label>
        {!rt && (
          <>
            <label>
              <input type="checkbox" checked={options.includeDeferred} onChange={(e) => props.onOptions({ ...options, includeDeferred: e.target.checked })} /> 콜백 안 호출
            </label>
            <label>
              <input type="checkbox" checked={options.includeExternal} onChange={(e) => props.onOptions({ ...options, includeExternal: e.target.checked })} /> 장비 호출
            </label>
          </>
        )}
      </div>
      <div className="fvev" data-el="7.3" ref={listRef}>
        {trace.events.length === 0 && <div className="meta">따라갈 호출을 찾지 못했습니다.</div>}
        {trace.events.map((e, i) => (
          <EventRow key={i} model={model} event={e} index={i} current={trace.index === i} past={i < trace.index} onClick={() => props.onSeek(i)} />
        ))}
      </div>
    </div>
  )
}

function EventRow({ model, event, index, current, past, onClick }: { model: Model; event: TraceEvent; index: number; current: boolean; past: boolean; onClick: () => void }) {
  const node = (id: string) => model.byId.get(id) as GraphNode | undefined
  const name = (id: string) => {
    const n = node(id)
    return n ? displayName(n) : id
  }
  let mark = '·'
  let body: React.ReactNode = null
  let tone = ''
  if (event.type === 'call') {
    const http = event.step.edge === 'http'
    mark = http ? '⇢' : '→'
    body = (
      <>
        {http ? event.step.label : name(event.to)}
        {event.via && <span className="sub"> · {event.via}</span>}
        {event.step.deferred && <span className="chip">나중에</span>}
        {event.step.confidence === 'inferred' && <span className="chip warn">추정</span>}
        {event.args && Object.keys(event.args).length > 0 && (
          <span className="sub">
            ({Object.entries(event.args)
              .map(([k, v]) => `${k}=${v}`)
              .join(', ')})
          </span>
        )}
      </>
    )
  } else if (event.type === 'return') {
    mark = '←'
    tone = event.failed ? 'bad' : 'ret'
    body = (
      <>
        {name(event.from)} <span className="sub">{event.label}</span>
      </>
    )
  } else if (event.type === 'external') {
    tone = 'dim'
    body = event.step.label
  } else if (event.type === 'skipped') {
    mark = '┄'
    tone = 'dim'
    body = (
      <>
        <s>{event.raise ?? name(event.to)}</s> <span className="sub">이번엔 안 {event.raise ? '던짐' : '부름'} · {event.step.line}줄</span>
      </>
    )
  } else if (event.type === 'raise') {
    mark = '!'
    tone = 'bad'
    body = event.label
  } else {
    mark = '↻'
    tone = 'dim'
    body = <>{name(event.to)} 다시 부름</>
  }
  const ms = event.type === 'call' && event.ms !== undefined ? `${event.ms}ms` : ''
  return (
    <div data-index={index} className={`e ${tone}${current ? ' on' : ''}${past ? ' past' : ''}`} style={{ paddingLeft: 8 + event.depth * 12 }} onClick={onClick}>
      <span className="mk">{mark}</span>
      <span className="lb">{body}</span>
      {ms && <span className="t">{ms}</span>}
    </div>
  )
}
