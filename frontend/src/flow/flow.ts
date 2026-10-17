// API 흐름 보기: 엔드포인트 하나에 관여하는 함수만 꺼내 레이어(또는 호출 깊이)별 열로 늘어놓는다.
// 왼쪽 → 오른쪽이 요청이 흐르는 방향: 화면 … API 호출 함수 | 엔드포인트 | 그 프로젝트의 레이어들 …
// 결과는 도시 보기와 같은 꼴(ViewNode 트리 + Layout)이라 CodeScene 을 그대로 쓴다.

import type { GraphNode } from './types'
import { type ArchLayer, type ArchMap, type Violation, CONCEPTS, violationOf } from './arch'
import { type Box, type Layout, PLATE_H } from './layout'
import { serverFor, worldFlow } from './world'
import { type Model, type Shape, type ViewNode, FUNCTION_KINDS, displayName } from './model'

/** 열 하나(레이어 하나)의 이름·색·모양. 백엔드는 레이어 지도(arch.ts), 프론트는 아래 FRONT. */
export type LayerStyle = { id: string; name: string; color: string; shape: Shape; shapeName: string; concept: string }
export type FlowColumn = { depth: number; title: string; ids: string[]; layer?: LayerStyle }
export type FlowEdge = { from: string; to: string; violation?: Violation }
export type ApiFlow = {
  routeId: string
  columns: FlowColumn[]
  size: number
  hidden: number
  layerOf: Map<string, LayerStyle> // 함수 → 레이어(열 기준과 상관없이 색·모양에 쓴다)
  edges: FlowEdge[] // 흐름 안 함수끼리의 호출. 레이어 규칙을 어기면 violation
}
export type FlowOptions = {
  maxDepth: number
  trivial: boolean // 생성자·예외도 보일지
  groupBy: 'depth' | 'layer' // 열 기준: 호출 깊이, 또는 프로젝트 레이어(라우터·서비스·저장소 … 프로젝트마다 다름)
}

export const DEFAULT_FLOW: FlowOptions = { maxDepth: 3, trivial: false, groupBy: 'layer' }

const OTHER: LayerStyle = { id: 'other', ...CONCEPTS.other, concept: 'other' }
const styleOf = (l: ArchLayer): LayerStyle => ({ id: l.id, name: l.name, color: l.color, shape: l.shape, shapeName: l.shapeName, concept: l.concept })

/** 함수 하나의 레이어(프론트·백엔드 모두 레이어 지도에서) */
export function layerOfNode(arch: ArchMap, n: GraphNode): LayerStyle {
  const l = arch.byId.get(arch.layerOf.get(n.id) ?? '')
  return l ? styleOf(l) : OTHER
}
const MAX_FRONT = 4 // 프론트 쪽으로 몇 단계까지 거슬러 갈지

/** 흐름을 읽는 데 방해만 되는 것: 생성자, 예외 클래스의 메서드. */
function isTrivial(n: GraphNode) {
  const qual = n.id.split('::')[1] ?? n.name
  if (n.name === '__init__' || n.name === 'constructor' || n.name === '__post_init__') return true
  const owner = qual.includes('.') ? qual.split('.').slice(-2, -1)[0] : ''
  return /(Error|Exception|Problem|NotFound|Forbidden|Conflict|Invalid|Denied|Blocked|Trashed|Unauthorized)$/.test(owner)
}

/** 엔드포인트 하나의 흐름: 백엔드는 호출을 따라 내려가고, 프론트는 요청 함수에서 부르는 쪽으로 거슬러 오른다. */
export function apiFlow(model: Model, arch: ArchMap, routeId: string, options: FlowOptions = DEFAULT_FLOW): ApiFlow {
  const MAX_BACK = options.maxDepth
  let hidden = 0
  const depthOf = new Map<string, number>([[routeId, 0]])
  const isFn = (id: string) => FUNCTION_KINDS.has(model.byId.get(id)?.kind ?? '')
  // 백엔드: 너비 우선으로 처음 닿은 깊이
  let frontier = [routeId]
  for (let d = 1; d <= MAX_BACK && frontier.length; d++) {
    const next: string[] = []
    for (const id of frontier)
      for (const e of model.out.get(id) ?? []) {
        if ((e.kind !== 'calls' && e.kind !== 'depends') || depthOf.has(e.to) || !isFn(e.to)) continue
        const target = model.byId.get(e.to)!
        if (target.layer === 'frontend') continue
        if (!options.trivial && isTrivial(target)) {
          hidden++
          continue
        }
        depthOf.set(e.to, d)
        next.push(e.to)
      }
    frontier = next
  }
  // 프론트: 이 라우트로 요청을 보내는 함수(-1)와 그 함수를 부르는 쪽(-2, -3 …). 컴포넌트에서 멈춘다
  frontier = (model.in.get(routeId) ?? []).filter((e) => e.kind === 'http').map((e) => e.from)
  for (const id of frontier) depthOf.set(id, -1)
  for (let d = 2; d <= MAX_FRONT && frontier.length; d++) {
    const next: string[] = []
    for (const id of frontier) {
      if (model.byId.get(id)?.kind === 'component') continue
      for (const e of model.in.get(id) ?? []) {
        if (e.kind !== 'calls' || depthOf.has(e.from) || !isFn(e.from)) continue
        depthOf.set(e.from, -d)
        next.push(e.from)
      }
    }
    frontier = next
  }
  const layerOf = new Map<string, LayerStyle>()
  for (const id of depthOf.keys()) layerOf.set(id, layerOfNode(arch, model.byId.get(id)!))
  // 흐름 안 호출과 레이어 위반(아래가 위를 부름 · 그 프로젝트 관례상 거쳐야 할 층을 건너뜀)
  const edges: FlowEdge[] = []
  const seen = new Set<string>()
  for (const id of depthOf.keys())
    for (const e of model.out.get(id) ?? []) {
      if ((e.kind !== 'calls' && e.kind !== 'depends') || !depthOf.has(e.to) || e.to === id) continue
      const key = `${id}|${e.to}`
      if (seen.has(key)) continue
      seen.add(key)
      edges.push({ from: id, to: e.to, violation: e.kind === 'calls' ? violationOf(arch, id, e.to) : undefined })
    }
  const base = { routeId, size: depthOf.size, hidden, layerOf, edges }

  if (options.groupBy === 'layer') {
    const byLayer = new Map<string, string[]>()
    // 같은 레이어 안에서는 얕은 깊이부터
    for (const [id] of [...depthOf.entries()].sort((a, b) => a[1] - b[1])) {
      const l = layerOf.get(id)!.id
      if (!byLayer.has(l)) byLayer.set(l, [])
      byLayer.get(l)!.push(id)
    }
    const order: LayerStyle[] = [...arch.front, ...arch.layers].map(styleOf)
    if (!order.some((l) => l.id === 'other')) order.push(OTHER)
    const columns = order
      .map((l, k) => ({ depth: k, title: l.name, ids: byLayer.get(l.id) ?? [], layer: l }))
      .filter((c) => c.ids.length)
    return { ...base, columns }
  }
  const byDepth = new Map<number, string[]>()
  for (const [id, d] of depthOf) {
    if (!byDepth.has(d)) byDepth.set(d, [])
    byDepth.get(d)!.push(id)
  }
  const columns = [...byDepth.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([depth, ids]) => ({ depth, title: columnTitle(model, depth, ids), ids }))
  return { ...base, columns }
}

/** 열 이름: 깊이와, 그 열에 많이 있는 역할(서비스·리포지토리·컴포넌트 …). */
function columnTitle(model: Model, depth: number, ids: string[]): string {
  const nodes = ids.map((id) => model.byId.get(id)!).filter(Boolean)
  const share = (test: (n: GraphNode) => boolean) => nodes.filter(test).length / Math.max(1, nodes.length)
  const qual = (n: GraphNode) => n.id.split('::')[1] ?? n.name
  if (depth === 0) return '엔드포인트'
  if (depth === -1) return 'API 호출 함수'
  if (depth < 0) {
    if (share((n) => n.kind === 'component') >= 0.5) return '화면 · 컴포넌트'
    if (share((n) => n.kind === 'hook') >= 0.5) return '훅'
    return `프론트 호출자 ${-depth - 1}`
  }
  const role =
    share((n) => /service/i.test(qual(n))) >= 0.5
      ? ' · 서비스'
      : share((n) => /repo|repository|dao|crud|store/i.test(qual(n)) || /repositor|crud/i.test(n.path)) >= 0.5
        ? ' · 저장소'
        : ''
  return `depth ${depth}${role}`
}

/**
 * 흐름 → 장면용 모델·배치. 열마다 판 하나, 함수마다 블록 하나(층 하나짜리 건물).
 * 열 안에서는 처음 닿은 순서로 앞에서 뒤로, 많으면 여러 줄로 나눈다.
 */
export function layoutFlow(model: Model, flow: ApiFlow, infra = model.graph.infra): { model: Model; layout: Layout } {
  const route = model.byId.get(flow.routeId)!
  const rootNode: GraphNode = {
    id: 'flow',
    kind: 'project',
    name: route.route ? `${route.route.method} ${route.route.path}` : displayName(route),
    parent: null,
    path: '',
  }
  const root: ViewNode = { id: 'flow', ids: ['flow'], node: rootNode, label: rootNode.name, children: [], parent: null, depth: 0, weight: 0, floors: [], aux: false }
  const viewOf = new Map<string, ViewNode>([['flow', root]])
  const layout: Layout = { plates: new Map(), buildings: new Map(), floors: new Map(), floorOwner: new Map(), bounds: { x: 0, z: 0, w: 0, d: 0, y: 0, h: 0 } }

  const BLOCK = 1.4 // 블록 한 변
  const GAP = 2.6 // 앞뒤 블록 사이: 블록 아래 두 줄 이름표 자리(비스듬히 보면 앞뒤가 좁아 보여 넉넉히)
  const LANE_GAP = 3.4 // 옆 줄 사이: 가운데 맞춘 이름표가 옆 줄과 겹치지 않게
  const COL_GAP = 4.0 // 열 사이(호가 지나갈 자리)
  const PER_LANE = 9 // 한 줄에 앞뒤로 놓는 블록 수, 넘으면 옆 줄(옆으로 넓어지면 화면에 작게 들어가 이름표가 가린다)
  const style = new Map<string, { color: string; shape: Shape }>()
  const plateTint = new Map<string, string>()
  let x = 0
  let maxD = 0
  const colBoxes: Array<{ view: ViewNode; x0: number; w: number; d: number }> = []
  for (const col of flow.columns) {
    const lanes = Math.ceil(col.ids.length / PER_LANE)
    const rows = Math.min(PER_LANE, col.ids.length)
    const w = lanes * BLOCK + (lanes - 1) * LANE_GAP + 1.2
    const d = rows * BLOCK + (rows - 1) * GAP + 1.2
    const colNode: GraphNode = {
      id: `col:${col.depth}`,
      kind: 'dir',
      name: col.title,
      parent: 'flow',
      path: '',
      layer: col.ids.some((id) => model.byId.get(id)?.layer === 'frontend') ? 'frontend' : 'backend',
    }
    const view: ViewNode = { id: colNode.id, ids: [colNode.id], node: colNode, label: col.title, children: [], parent: root, depth: 1, weight: 0, floors: [], aux: false }
    root.children.push(view)
    viewOf.set(view.id, view)
    if (col.layer) plateTint.set(colNode.id, col.layer.color)
    col.ids.forEach((id, k) => {
      const fn = model.byId.get(id)!
      const lane = Math.floor(k / PER_LANE)
      const row = k % PER_LANE
      const layer = flow.layerOf.get(id) ?? OTHER
      style.set(id, { color: layer.color, shape: layer.shape })
      // 스키마는 납작한 판, 나머지는 줄 수에 따라 높이
      // 줄 수가 많은 함수일수록 높은 건물(스키마는 납작한 판)
      const h = layer.concept === 'schema' ? 0.25 : Math.min(6, 0.8 + 0.3 * Math.sqrt(fn.loc ?? 4))
      const box: Box = {
        x: x + 0.6 + lane * (BLOCK + LANE_GAP) + BLOCK / 2,
        z: 0.6 + row * (BLOCK + GAP) + BLOCK / 2,
        w: BLOCK,
        d: BLOCK,
        y: PLATE_H * 2,
        h,
      }
      const leaf: ViewNode = { id, ids: [id], node: fn, label: displayName(fn), children: [], parent: view, depth: 2, weight: 0, floors: [fn], aux: false }
      view.children.push(leaf)
      viewOf.set(id, leaf)
      layout.floors.set(id, box)
      layout.floorOwner.set(id, fn)
      layout.buildings.set(id, box)
    })
    colBoxes.push({ view, x0: x, w, d })
    maxD = Math.max(maxD, d)
    x += w + COL_GAP
  }
  const totalW = x - COL_GAP
  // 가운데 정렬: x는 -totalW/2 만큼, z는 -maxD/2 만큼 옮긴다
  const dx = -totalW / 2
  const dz = -maxD / 2
  for (const b of layout.floors.values()) {
    b.x += dx
    b.z += dz
  }
  for (const c of colBoxes)
    layout.plates.set(c.view.id, { x: c.x0 + c.w / 2 + dx, z: c.d / 2 + dz, w: c.w, d: c.d, y: PLATE_H, h: PLATE_H })
  layout.plates.set('flow', { x: 0, z: 0, w: totalW + 1.6, d: maxD + 1.6, y: 0, h: PLATE_H })
  let top = 0
  for (const b of layout.floors.values()) top = Math.max(top, b.y + b.h)
  layout.bounds = { x: 0, z: 0, w: totalW + 1.6, d: maxD + 1.6, y: 0, h: top }
  // 인프라: 프론트 열은 브라우저, 백엔드 열은 서버 받침대 위. 이 API의 함수가 쓰는 장비(DB·외부 API …)를 옆에
  const used = new Set<string>()
  for (const c of flow.columns)
    for (const id of c.ids) for (const st of model.byId.get(id)?.steps ?? []) if (st.kind === 'call' && st.infra) used.add(st.infra)
  const world = worldFlow(
    layout,
    flow.columns.map((c) => ({ plateId: `col:${c.depth}`, front: c.ids.some((id) => model.byId.get(id)?.layer === 'frontend'), ids: c.ids })),
    infra,
    used,
    serverFor(infra, route.path)?.id
  )
  return { model: { ...model, root, viewOf, flow: true, style, plateTint, world }, layout }
}
