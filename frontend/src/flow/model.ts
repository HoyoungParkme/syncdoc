// 그래프 JSON을 뷰어가 쓰기 좋은 모양으로 바꾼다: 색인, 보이는 트리(합친 폴더), 호출 흐름.

import type { CodeGraph, GraphEdge, GraphNode, RuntimeEvent, RuntimeRecord, Step } from './types'
import type { World } from './world'

export const FUNCTION_KINDS = new Set(['function', 'method', 'component', 'hook'])

/** 화면에 보이는 트리의 노드. 하위 폴더가 하나뿐인 폴더 체인은 하나로 합친다(backend/app). */
export type ViewNode = {
  id: string // 체인의 가장 안쪽 노드 id
  ids: string[] // 합쳐진 모든 노드 id
  node: GraphNode
  label: string
  children: ViewNode[]
  parent: ViewNode | null
  depth: number
  weight: number // 배치 넓이(layout.ts가 채움)
  floors: GraphNode[] // 파일일 때: 층으로 쌓을 클래스·함수(파일 위쪽 코드가 위층)
  aux: boolean // 맨 위 폴더 중 앱 본체가 아닌 것(tests, scripts, data …): 뒷줄에 흐리게
}

export type Model = {
  graph: CodeGraph
  byId: Map<string, GraphNode>
  childrenOf: Map<string, GraphNode[]>
  out: Map<string, GraphEdge[]>
  in: Map<string, GraphEdge[]>
  root: ViewNode
  viewOf: Map<string, ViewNode> // 그래프 id(합쳐진 것 포함) → 보이는 노드
  flow?: boolean // API 흐름 보기용으로 다시 짠 트리(flow.ts)
  style?: Map<string, { color: string; shape: Shape }> // 층(함수)마다 색·모양을 따로 줄 때(역할별)
  plateTint?: Map<string, string> // 판마다 물들일 색(역할 열)
  world?: World // 인프라 장비·구역(코드가 장비 위에 얹힌 세계)
}

/** 층(함수 블록) 모양. 상자 하나로 맞춘 단위 크기. */
export type Shape = 'box' | 'rounded' | 'hex' | 'oct' | 'cylinder' | 'cone' | 'sphere'

export function buildModel(graph: CodeGraph): Model {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  // 인프라 장비도 이름으로 찾을 수 있게(흐름 재생이 장비로 가는 호출을 그린다). 트리에는 넣지 않는다
  for (const d of graph.infra?.nodes ?? [])
    byId.set(d.id, { id: d.id, kind: 'infra', name: d.name, parent: null, path: d.host ?? '', layer: d.kind === 'browser' ? 'frontend' : 'backend' })
  const childrenOf = new Map<string, GraphNode[]>()
  for (const n of graph.nodes) {
    if (!n.parent) continue
    if (!childrenOf.has(n.parent)) childrenOf.set(n.parent, [])
    childrenOf.get(n.parent)!.push(n)
  }
  const rank = (n: GraphNode) => (n.kind === 'dir' ? 0 : n.kind === 'file' ? 1 : 2)
  for (const list of childrenOf.values())
    list.sort((a, b) => rank(a) - rank(b) || (a.line ?? 0) - (b.line ?? 0) || a.name.localeCompare(b.name))

  const out = new Map<string, GraphEdge[]>()
  const inn = new Map<string, GraphEdge[]>()
  for (const e of graph.edges) {
    if (!out.has(e.from)) out.set(e.from, [])
    out.get(e.from)!.push(e)
    if (!inn.has(e.to)) inn.set(e.to, [])
    inn.get(e.to)!.push(e)
  }

  const viewOf = new Map<string, ViewNode>()
  const build = (start: GraphNode, parent: ViewNode | null, depth: number): ViewNode => {
    const ids = [start.id]
    let node = start
    const names = [start.name]
    while (node.kind === 'dir') {
      const kids = childrenOf.get(node.id) ?? []
      if (kids.length !== 1 || kids[0].kind !== 'dir') break
      node = kids[0]
      ids.push(node.id)
      names.push(node.name)
    }
    const view: ViewNode = {
      id: node.id,
      ids,
      node,
      label: node.kind === 'project' ? node.name : names.join('/'),
      children: [],
      parent,
      depth,
      weight: 0,
      floors: [],
      aux: false,
    }
    for (const id of ids) viewOf.set(id, view)
    if (node.kind === 'file') {
      for (const item of childrenOf.get(node.id) ?? []) {
        view.floors.push(item)
        if (item.kind === 'class') view.floors.push(...(childrenOf.get(item.id) ?? []))
      }
      for (const f of view.floors) viewOf.set(f.id, view)
    } else {
      for (const child of childrenOf.get(node.id) ?? []) {
        if (child.kind !== 'dir' && child.kind !== 'file') continue
        view.children.push(build(child, view, depth + 1))
      }
    }
    return view
  }
  const project = graph.nodes.find((n) => n.kind === 'project')!
  const root = build(project, null, 0)
  markAux(root, childrenOf)

  return { graph, byId, childrenOf, out, in: inn, root, viewOf }
}

/**
 * 맨 위 폴더 가운데 앱 본체(프론트이거나 API 라우트가 있는 곳)가 아닌 것을 보조로 표시한다.
 * 본체를 하나도 못 찾으면(라우트 없는 프로젝트) 모두 본체로 둔다.
 */
function markAux(root: ViewNode, childrenOf: Map<string, GraphNode[]>) {
  const hasRoute = (id: string): boolean =>
    (childrenOf.get(id) ?? []).some((c) => !!c.route || hasRoute(c.id))
  const main = root.children.filter((v) => v.node.layer === 'frontend' || v.ids.some(hasRoute))
  if (!main.length) return
  for (const v of root.children) v.aux = !main.includes(v)
}

/** 노드가 들어 있는 파일. */
export function fileOf(model: Model, id: string): GraphNode | undefined {
  for (let n = model.byId.get(id); n; n = n.parent ? model.byId.get(n.parent) : undefined)
    if (n.kind === 'file') return n
  return undefined
}

/** 루트부터 이 노드까지 보이는 경로(빵부스러기). */
export function viewPath(model: Model, id: string): ViewNode[] {
  const path: ViewNode[] = []
  for (let v = model.viewOf.get(id) ?? null; v; v = v.parent) path.unshift(v)
  return path
}

// ---------------------------------------------------------------------------- 호출 흐름

// 실행 기록에서 온 흐름은 args(실제 인자)·ms(걸린 시간)·failed(예외로 빠져나감)를 더 갖는다.
export type TraceEvent =
  | {
      type: 'call'
      from: string
      to: string
      depth: number
      step: Step & { kind: 'call' }
      args?: Record<string, string>
      ms?: number
      via?: string // 브라우저 기록: 컴포넌트·훅 안의 콜백 이름
    }
  | { type: 'return'; from: string; to: string; depth: number; label: string; failed?: boolean; ms?: number }
  | { type: 'external'; from: string; depth: number; step: Step & { kind: 'call' } }
  | { type: 'raise'; from: string; depth: number; label: string }
  | { type: 'cycle'; from: string; to: string; depth: number; step: Step & { kind: 'call' } }
  // 실행 기록에서만: 코드상 부를 수 있지만 이번 실행에서는 부르지 않은 호출(안 탄 갈래).
  // raise 가 있으면 "이번엔 던지지 않은 예외"(to는 그 함수 자신).
  | { type: 'skipped'; from: string; to: string; depth: number; step: Step; raise?: string }

export type TraceOptions = {
  maxDepth: number
  includeRenders: boolean
  includeDeferred: boolean
  includeExternal: boolean
  maxEvents: number
  only?: Set<string> // 있으면 이 함수들 사이의 호출만(API 흐름 보기: 화면에 보이는 함수만)
}

export const DEFAULT_TRACE: TraceOptions = {
  maxDepth: 8,
  includeRenders: false,
  includeDeferred: true,
  includeExternal: true,
  maxEvents: 600,
}

/**
 * 함수 하나에서 시작해 정적으로 알 수 있는 호출을 실행 순서대로 펼친다.
 * 각 호출은 call(들어감) … return(돌아옴) 쌍이 되고, 그 사이에 안쪽 호출이 끼어든다.
 */
export function buildTrace(model: Model, rootId: string, options: TraceOptions = DEFAULT_TRACE): TraceEvent[] {
  const events: TraceEvent[] = []
  const walk = (id: string, depth: number, stack: Set<string>) => {
    const node = model.byId.get(id)
    for (const step of node?.steps ?? []) {
      if (events.length >= options.maxEvents) return
      if (step.kind === 'raise') {
        events.push({ type: 'raise', from: id, depth, label: step.label })
        continue
      }
      if (step.kind !== 'call') continue
      if (step.deferred && !options.includeDeferred) continue
      if (step.edge === 'renders' && !options.includeRenders) continue
      // 인프라 장비로 나가는 호출(session.execute, s3.put_object …): 장비까지 갔다가 돌아온다
      if (step.infra && !step.target && model.byId.has(step.infra)) {
        if (options.only && !options.only.has(step.infra)) continue
        events.push({ type: 'call', from: id, to: step.infra, depth, step })
        events.push({ type: 'return', from: step.infra, to: id, depth, label: '↩ 결과' })
        continue
      }
      const target = step.target ? model.byId.get(step.target) : undefined
      if (options.only && (!target || !options.only.has(target.id))) continue
      if (!target || !FUNCTION_KINDS.has(target.kind)) {
        if (options.includeExternal && !step.target) events.push({ type: 'external', from: id, depth, step })
        continue
      }
      if (stack.has(target.id) || depth >= options.maxDepth) {
        events.push({ type: 'cycle', from: id, to: target.id, depth, step })
        continue
      }
      events.push({ type: 'call', from: id, to: target.id, depth, step })
      stack.add(target.id)
      walk(target.id, depth + 1, stack)
      stack.delete(target.id)
      events.push({ type: 'return', from: target.id, to: id, depth, label: returnLabel(target) })
    }
  }
  walk(rootId, 0, new Set([rootId]))
  return events
}

function returnLabel(node: GraphNode): string {
  const returns = (node.steps ?? []).filter((s) => s.kind === 'return')
  if (returns.length) return returns[returns.length - 1].label
  return node.returns ? `→ ${node.returns}` : 'return'
}

/**
 * 실행 기록 → 재생할 흐름. 그래프에 없는 함수(안쪽 함수, lambda)는 투명하게 건너뛰고 그 안의 호출을 바깥에 붙인다.
 * FastAPI가 먼저 부른 Depends 함수들은 엔드포인트가 부른 것처럼 엔드포인트에서 나가는 호출로 보여 준다.
 */
/** 실행 기록의 경계 호출 → 그래프의 장비 id. 장비 지도에 없으면 undefined(그리지 않는다) */
export function deviceFor(model: Model, infra: { kind: string; target: string }): string | undefined {
  const has = (id: string) => (model.byId.get(id)?.kind === 'infra' ? id : undefined)
  const host = infra.target.replace(/^\w[\w+.-]*:\/\//, '').split(/[:/]/)[0]
  if (infra.kind === 'db') return /^mongodb/.test(infra.target) ? has('infra:mongo') : /^(bolt|neo4j)/.test(infra.target) ? has('infra:neo4j') : has('infra:db')
  if (infra.kind === 'redis') return has('infra:redis')
  if (infra.kind === 's3') return has('infra:storage')
  if (/openai\.com$/.test(host)) return has('infra:openai')
  if (/anthropic\.com$/.test(host)) return has('infra:anthropic')
  // 저장소 엔드포인트(MinIO)로 가는 HTTP 는 저장소, 나머지 외부 HTTP
  const storage = model.graph.infra?.nodes.find((n) => n.id === 'infra:storage')
  if (storage?.host && storage.host.split(':')[0] === host) return 'infra:storage'
  return has('infra:http')
}

export function runtimeTrace(
  model: Model,
  record: RuntimeRecord
): { rootId: string; events: TraceEvent[]; result: string } | null {
  const kids = new Map<number, RuntimeEvent[]>()
  for (const e of record.events) {
    if (!kids.has(e.parent)) kids.set(e.parent, [])
    kids.get(e.parent)!.push(e)
  }
  const known = (fn: string) => FUNCTION_KINDS.has(model.byId.get(fn)?.kind ?? '')
  const tops = kids.get(-1) ?? []
  // 핸들러: 맨 위 호출 중 라우트인 것 → 마지막 맨 위 호출. yield 의존성이 응답 뒤 다시 깨어난 것(resume)은 빼고
  const awake = tops.filter((e) => e.kind !== 'resume')
  const handler =
    awake.find((e) => model.byId.get(e.fn)?.route) ?? [...awake].reverse().find((e) => known(e.fn)) ?? record.events.find((e) => known(e.fn))
  if (!handler) return null
  const rootId = handler.fn
  const events: TraceEvent[] = []
  // FastAPI는 Depends를 함수 안이 아니라 맨 위에서 먼저 푼다: 맨 위에 불린 함수는 Depends로 부른 것으로 친다
  const topFns = new Set(tops.map((t) => t.fn))
  /**
   * 코드상 이 함수가 부를 수 있는 프로젝트 함수 중 이번에 부르지 않은 것, 정상으로 끝났다면 던지지 않은 raise 를
   * events 에 덧붙인다.
   */
  const addSkipped = (fn: string, depth: number, since: number, failed: boolean) => {
    const called = new Set<string>()
    for (let k = since; k < events.length; k++) {
      const ev = events[k]
      if (ev.type === 'call' && ev.from === fn) called.add(ev.to)
    }
    const seen = new Set<string>()
    for (const step of model.byId.get(fn)?.steps ?? []) {
      if (step.kind === 'raise') {
        if (!failed) events.push({ type: 'skipped', from: fn, to: fn, depth, step, raise: step.label })
        continue
      }
      if (step.kind !== 'call' || !step.target || step.edge === 'renders') continue
      if (step.edge === 'depends' && topFns.has(step.target)) continue
      if (called.has(step.target) || seen.has(step.target) || !known(step.target)) continue
      seen.add(step.target)
      events.push({ type: 'skipped', from: fn, to: step.target, depth, step })
    }
  }
  const walk = (e: RuntimeEvent, from: string, depth: number) => {
    // DB·외부로 나간 호출: 그 장비까지 갔다가 돌아온다(SQL 앞부분·걸린 시간·결과)
    if (e.fn === '@infra' && e.infra) {
      const device = deviceFor(model, e.infra)
      const ms = e.t1 !== undefined ? +(e.t1 - e.t0).toFixed(2) : undefined
      if (!device) return
      events.push({
        type: 'call',
        from,
        to: device,
        depth,
        step: { kind: 'call', line: e.callLine ?? 0, label: e.infra.op, target: device, edge: 'calls', confidence: 'exact', infra: device },
        ms,
      })
      events.push({ type: 'return', from: device, to: from, depth, label: e.exc ? `✕ ${e.exc}` : (e.ret ?? '응답'), failed: !!e.exc, ms })
      return
    }
    if (!known(e.fn)) {
      for (const c of kids.get(e.i) ?? []) walk(c, from, depth)
      return
    }
    const ms = e.t1 !== undefined ? +(e.t1 - e.t0).toFixed(2) : undefined
    events.push({
      type: 'call',
      from,
      to: e.fn,
      depth,
      step: {
        kind: 'call',
        line: e.callLine ?? e.line ?? 0,
        label: e.name ?? e.fn.split('::')[1] ?? e.fn,
        target: e.fn,
        edge: 'calls',
        confidence: 'exact',
      },
      args: e.args ?? undefined,
      ms,
    })
    const since = events.length
    const children = kids.get(e.i) ?? []
    for (const c of children) walk(c, e.fn, depth + 1)
    if (!e.yield) addSkipped(e.fn, depth + 1, since, !!e.exc) // 제너레이터의 yield는 아직 끝난 게 아니라서 빼고
    // 예외가 처음 생긴 곳에서만 raise를 보여 준다(위로 전파된 곳은 실패한 반환으로)
    if (e.exc && !children.some((c) => c.exc === e.exc)) events.push({ type: 'raise', from: e.fn, depth: depth + 1, label: e.exc })
    events.push({
      type: 'return',
      from: e.fn,
      to: from,
      depth,
      label: e.exc ? `✕ ${e.exc}` : e.yield ? `yield ${e.ret ?? ''}` : `return ${e.ret ?? ''}`,
      failed: !!e.exc,
      ms,
    })
  }
  for (const top of tops) {
    if (top === handler) {
      const since = events.length
      for (const c of kids.get(top.i) ?? []) walk(c, rootId, 0)
      addSkipped(rootId, 0, since, !!top.exc)
      if (top.exc && !(kids.get(top.i) ?? []).some((c) => c.exc === top.exc))
        events.push({ type: 'raise', from: rootId, depth: 0, label: top.exc })
    } else walk(top, rootId, 0)
  }
  const result = handler.exc ? `✕ ${handler.exc}` : (handler.ret ?? '')
  return { rootId, events, result }
}

/**
 * 브라우저 실행 기록(클릭 → 핸들러 → API 함수 → fetch …) → 재생할 흐름.
 * fetch 마다 backendOf 가 짝지은 백엔드 기록이 있으면 그 실행 흐름을 그 자리에 끼워 넣어 한 줄로 잇는다.
 */
export function frontRuntimeTrace(
  model: Model,
  record: RuntimeRecord,
  backendOf: (fetchEvent: RuntimeEvent) => RuntimeRecord | undefined
): { rootId: string; events: TraceEvent[]; result: string; via?: string } | null {
  const kids = new Map<number, RuntimeEvent[]>()
  for (const e of record.events) {
    if (!kids.has(e.parent)) kids.set(e.parent, [])
    kids.get(e.parent)!.push(e)
  }
  const known = (fn: string) => FUNCTION_KINDS.has(model.byId.get(fn)?.kind ?? '')
  const tops = kids.get(-1) ?? []
  // 시작점: 첫 요청을 일으킨 맨 위 호출(직전 타이핑 onChange 같은 것보다 handleSubmit), 없으면 첫 맨 위 호출
  const firstFetch = record.events.find((e) => e.fetch)
  let top = firstFetch
  while (top && top.parent !== -1) top = record.events[top.parent]
  const root = (top && known(top.fn) ? top : undefined) ?? tops.find((e) => known(e.fn)) ?? record.events.find((e) => known(e.fn))
  if (!root) return null
  const rootId = root.fn
  const events: TraceEvent[] = []
  let result = ''
  const walk = (e: RuntimeEvent, from: string, depth: number) => {
    const ms = e.t1 !== undefined ? +(e.t1 - e.t0).toFixed(2) : undefined
    if (e.fetch) {
      const label = `${e.fetch.method} ${e.fetch.path}`
      const back = backendOf(e)
      const built = back && runtimeTrace(model, back)
      if (!built) {
        events.push({ type: 'external', from, depth, step: { kind: 'call', line: 0, label: `${label} → ${e.fetch.status ?? '…'}`, edge: 'http' } })
        return
      }
      events.push({
        type: 'call',
        from,
        to: built.rootId,
        depth,
        step: { kind: 'call', line: 0, label, target: built.rootId, edge: 'http', confidence: 'exact' },
        ms,
      })
      events.push(...built.events.map((x) => ({ ...x, depth: x.depth + depth + 1 })))
      const status = e.fetch.status ?? back.status
      result ||= `${status} ${built.result}`
      events.push({ type: 'return', from: built.rootId, to: from, depth, label: `응답 ${status} ${built.result}`, failed: !!status && status >= 400, ms })
      return
    }
    // 그래프에 없는 함수, 또는 같은 컴포넌트의 콜백(핸들러 → 같은 컴포넌트)은 건너뛰고 안쪽만
    if (!known(e.fn) || e.fn === from) {
      for (const c of kids.get(e.i) ?? []) walk(c, from, depth)
      return
    }
    const name = displayName(model.byId.get(e.fn)!)
    events.push({
      type: 'call',
      from,
      to: e.fn,
      depth,
      step: { kind: 'call', line: 0, label: e.via ? `${name} · ${e.via}` : name, target: e.fn, edge: 'calls', confidence: 'exact' },
      args: e.args ?? undefined,
      ms,
      via: e.via,
    })
    const children = kids.get(e.i) ?? []
    for (const c of children) walk(c, e.fn, depth + 1)
    if (e.exc && !children.some((c) => c.exc === e.exc)) events.push({ type: 'raise', from: e.fn, depth: depth + 1, label: e.exc })
    events.push({ type: 'return', from: e.fn, to: from, depth, label: e.exc ? `✕ ${e.exc}` : `return ${e.ret ?? ''}`, failed: !!e.exc, ms })
  }
  for (const top of tops) {
    if (top === root) for (const c of kids.get(top.i) ?? []) walk(c, rootId, 0)
    else walk(top, rootId, 0)
  }
  return { rootId, events, result, via: root.via }
}

/**
 * 이 백엔드 라우트로 요청을 보내는 프론트 코드 사슬(코드 분석으로 찾은 것): [컴포넌트, …, 요청 함수].
 * 요청 함수에서 부르는 쪽으로 거슬러 올라가 가장 가까운 컴포넌트까지. 없으면 요청 함수 하나.
 */
export function frontChain(model: Model, routeId: string): { chain: string[]; senders: number } | null {
  const senders = (model.in.get(routeId) ?? []).filter((e) => e.kind === 'http').map((e) => e.from)
  if (!senders.length) return null
  let best: string[] | null = null
  for (const sender of senders) {
    // 너비 우선: 가장 짧게 컴포넌트에 닿는 길
    const queue: string[][] = [[sender]]
    const seen = new Set([sender])
    let found: string[] | null = null
    while (queue.length && !found) {
      const path = queue.shift()!
      const head = path[0]
      if (model.byId.get(head)?.kind === 'component') found = path
      else if (path.length < 5)
        for (const e of model.in.get(head) ?? []) {
          if (e.kind !== 'calls' || seen.has(e.from)) continue
          seen.add(e.from)
          queue.push([e.from, ...path])
        }
    }
    const chain = found ?? [sender]
    if (!best || (found && (best.length === 1 || chain.length < best.length))) best = chain
  }
  return best && { chain: best, senders: senders.length }
}

/** 실행 기록 흐름 앞뒤에 프론트 사슬(추정)을 붙인다: 컴포넌트 → … → 요청 함수 ⇢ 엔드포인트 … 응답 ← … */
export function withFrontChain(model: Model, rootId: string, events: TraceEvent[], result: string): TraceEvent[] {
  const found = frontChain(model, rootId)
  if (!found) return events
  const chain = found.chain
  const n = chain.length
  const route = model.byId.get(rootId)?.route
  const before: TraceEvent[] = []
  const after: TraceEvent[] = []
  for (let k = 0; k < n; k++) {
    const from = chain[k]
    const to = k + 1 < n ? chain[k + 1] : rootId
    const http = k + 1 === n
    const line = (model.byId.get(from)?.steps ?? []).find((s) => s.kind === 'call' && s.target === to)?.line ?? 0
    before.push({
      type: 'call',
      from,
      to,
      depth: k,
      step: {
        kind: 'call',
        line,
        label: http && route ? `${route.method} ${route.path}` : (model.byId.get(to)?.name ?? to),
        target: to,
        edge: http ? 'http' : 'calls',
        confidence: 'inferred',
      },
    })
    after.unshift({ type: 'return', from: to, to: from, depth: k, label: http ? `응답 ${result}` : 'return' })
  }
  return [...before, ...events.map((e) => ({ ...e, depth: e.depth + n })), ...after]
}

/** 흐름에 나온 함수들(시작 함수 포함). */
export function traceParticipants(rootId: string, events: TraceEvent[]): Set<string> {
  const ids = new Set([rootId])
  for (const e of events) if (e.type === 'call') ids.add(e.to)
  return ids
}

// ---------------------------------------------------------------------------- 표시용

export const KIND_LABEL: Record<string, string> = {
  project: '프로젝트',
  dir: '폴더',
  file: '파일',
  class: '클래스',
  function: '함수',
  method: '메서드',
  component: '컴포넌트',
  hook: '훅',
  infra: '장비',
}

export function displayName(node: GraphNode): string {
  if (node.kind === 'method') {
    const owner = node.id.split('::')[1]?.split('.')
    if (owner && owner.length > 1) return owner.slice(-2).join('.')
  }
  return node.name
}
