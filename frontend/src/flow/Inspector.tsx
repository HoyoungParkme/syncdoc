/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 5.4 함수 상세 · 5.5 호출 흐름 재생 · 5.6 호출하는 것 · 5.7 명세 — view_arc inspector를 옮겼다(카드 CG).
 *  층 이름은 명세 층 표(또는 짐작) — ArchMap. 명세 대조는 코드 그래프(UI-17)와 같은 값이다. */
import { Link } from 'react-router-dom'
import type { FlowFunction } from '../api/client'
import type { GraphNode, Step } from './types'
import type { ArchMap } from './arch'
import { type Model, FUNCTION_KINDS, KIND_LABEL, displayName } from './model'
import { floorColor } from './scene'

const STATUS: Record<string, [string, string]> = {
  same: ['✓', '명세와 같음'],
  code_only: ['▲', '코드만 부르는 것이 있다'],
  spec_only: ['◌', '명세에만 있는 호출이 있다'],
}

type Props = {
  code: string
  model: Model
  arch: ArchMap
  node: GraphNode
  fn: FlowFunction | undefined
  onSelect: (id: string) => void
  onTrace: (id: string) => void
  children?: React.ReactNode
}

export function Inspector({ code, model, arch, node, fn, onSelect, onTrace, children }: Props) {
  const isFunction = FUNCTION_KINDS.has(node.kind)
  const layer = arch.byId.get(arch.layerOf.get(node.id) ?? '')
  const callers = (model.in.get(node.id) ?? []).filter((e) => e.from !== node.id)
  const members = node.kind === 'file' || node.kind === 'class' ? collectMembers(model, node) : []
  return (
    <>
      <div className="k">{isFunction ? '함수' : KIND_LABEL[node.kind]}</div>
      <div data-el="5.4">
        <div className="nm">{displayName(node)}</div>
        <div className="meta">
          {node.path}
          {node.line ? `:${node.line}` : ''}
          {layer && (
            <>
              {' · '}
              <span title={arch.reason.get(node.id)}>{layer.name} 층</span>
            </>
          )}
          {node.route && (
            <>
              {' · '}
              <span className="chip">
                {node.route.method} {node.route.path}
              </span>
            </>
          )}
        </div>
      </div>
      {isFunction && (
        <span className="btn sm fvplay" data-el="5.5" onClick={() => onTrace(node.id)}>
          ▶ 호출 흐름 재생
        </span>
      )}
      {children}
      {isFunction && (
        <>
          <div className="k">호출하는 것{node.steps?.length ? ` ${node.steps.length}` : ''}</div>
          <div data-el="5.6">
            {!node.steps?.length && <div className="meta">코드에서 읽은 호출이 없습니다{fn && !fn.steps.length ? ' — 다음 코드 push에 호출 순서가 생깁니다' : ''}</div>}
            {node.steps?.map((s, i) => <StepRow key={i} model={model} step={s} onSelect={onSelect} />)}
          </div>
        </>
      )}
      {members.length > 0 && (
        <>
          <div className="k">{node.kind === 'file' ? '안에 든 것' : '메서드'}</div>
          {members.map((m) => (
            <div className="row" key={m.id} onClick={() => onSelect(m.id)}>
              <i className="dot" style={{ background: floorColor(m) }} />
              {m.name}
              {m.route && <span className="st">{m.route.method}</span>}
              <span className="st">{m.line}</span>
            </div>
          ))}
        </>
      )}
      {isFunction && (
        <>
          <div className="k">불리는 곳 {callers.length}</div>
          {callers.length === 0 && <div className="meta">찾은 호출이 없습니다 (진입점이거나 동적으로 불림)</div>}
          {callers.map((e) => {
            const from = model.byId.get(e.from)
            if (!from) return null
            return (
              <div className="row" key={e.from + e.kind} onClick={() => onSelect(from.id)}>
                <i className="dot" style={{ background: floorColor(from) }} />
                {displayName(from)}
                <span className="st">{e.kind === 'http' ? 'HTTP' : '호출'}{e.confidence === 'inferred' ? ' · 추정' : ''}</span>
              </div>
            )
          })}
        </>
      )}
      {isFunction && fn && (
        <>
          <div className="k">명세</div>
          <div data-el="5.7">
            {fn.item ? (
              <div className="row">
                {fn.item.replace(/^[A-Z]+-/, '')}
                {fn.status && (
                  <span className={`st ${fn.status}`} title={STATUS[fn.status][1]}>
                    {STATUS[fn.status][0]}
                  </span>
                )}
              </div>
            ) : (
              <div className="meta">{fn.layer ? `항목 없음 — ${fn.layer.name} 층` : '항목 없음'}</div>
            )}
            <Link className="lnk" to={`/p/${code}/code-graph?focus=${encodeURIComponent(fn.key)}`}>
              코드 그래프에서 보기
            </Link>
          </div>
        </>
      )}
    </>
  )
}

/** 호출 순서 한 줄 — 부르는 함수·「→ 장비」·추정·나중에 불림, 반환·예외 */
export function StepRow({ model, step, onSelect }: { model: Model; step: Step; onSelect: (id: string) => void }) {
  if (step.kind !== 'call')
    return (
      <div className={`row step ${step.kind}`}>
        <span className="mk">{step.kind === 'return' ? '↩' : '!'}</span>
        <span className="lb">{step.label}</span>
        <span className="st">{step.line}</span>
      </div>
    )
  const target = step.target ? model.byId.get(step.target) : undefined
  const device = step.infra ? model.byId.get(step.infra) : undefined
  return (
    <div className={`row step${target ? '' : ' dim'}`} onClick={() => target && onSelect(target.id)}>
      <span className="mk">{step.edge === 'http' ? '⇢' : '→'}</span>
      <span className="lb">
        {step.label}
        {target && target.name !== step.label && <span className="sub">→ {displayName(target)}</span>}
        {device && <span className="chip">→ {device.name}</span>}
        {step.awaited && <span className="chip">await</span>}
        {step.deferred && <span className="chip">나중에 불림</span>}
        {step.confidence === 'inferred' && <span className="chip warn">추정</span>}
      </span>
      <span className="st">{step.line}</span>
    </div>
  )
}

function collectMembers(model: Model, node: GraphNode): GraphNode[] {
  const out: GraphNode[] = []
  for (const child of model.childrenOf.get(node.id) ?? []) {
    out.push(child)
    if (child.kind === 'class' && node.kind === 'file') out.push(...(model.childrenOf.get(child.id) ?? []))
  }
  return out
}
