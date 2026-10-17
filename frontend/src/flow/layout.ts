// 보이는 트리 → 3D 상자 배치.
// 폴더는 한 단씩 올라가는 판(squarified treemap으로 나눔), 파일은 그 위의 건물,
// 클래스·함수는 건물의 층(파일 위쪽 코드가 위층, 클래스 메서드는 한 뼘 안쪽으로).

import type { GraphNode } from './types'
import type { ViewNode } from './model'

/** x, z는 가운데, y는 바닥. */
export type Box = { x: number; z: number; w: number; d: number; y: number; h: number }

export type Layout = {
  plates: Map<string, Box> // 폴더·프로젝트 보이는 노드 id → 판
  buildings: Map<string, Box> // 파일 id → 층 전체를 감싸는 상자
  floors: Map<string, Box> // 클래스·함수 id(층이 없는 파일은 파일 id) → 층
  floorOwner: Map<string, GraphNode> // 층 id → 그 층이 나타내는 노드
  bounds: Box
}

type Rect = { x0: number; z0: number; w: number; d: number }

export const PLATE_H = 0.16
const SCALE = 0.62
const FLOOR_GAP = 0.03

export function layoutCity(root: ViewNode): Layout {
  const out: Layout = {
    plates: new Map(),
    buildings: new Map(),
    floors: new Map(),
    floorOwner: new Map(),
    bounds: { x: 0, z: 0, w: 0, d: 0, y: 0, h: 0 },
  }
  assignWeights(root)
  const side = Math.sqrt(root.weight) * SCALE
  const rect: Rect = { x0: -side * 0.65, z0: -side * 0.5, w: side * 1.3, d: side }
  place(root, rect, 0, out)
  let maxY = 0
  for (const b of out.buildings.values()) maxY = Math.max(maxY, b.y + b.h)
  out.bounds = { x: 0, z: 0, w: rect.w, d: rect.d, y: 0, h: maxY }
  return out
}

/** 칸 넓이 = 건물 바닥 + 둘레 여유. 폴더는 자식 합 + 판 가장자리 몫. */
function assignWeights(view: ViewNode): number {
  if (view.node.kind === 'file') view.weight = (footprint(view.node) + 0.45) ** 2
  else view.weight = view.children.reduce((s, c) => s + assignWeights(c), 0) * 1.22 + 1.5
  return view.weight
}

/** 건물 바닥 한 변: 줄 수가 늘면 천천히 넓어진다(높이는 층으로 커지므로). */
function footprint(file: GraphNode) {
  return 0.75 + 0.075 * Math.sqrt(file.loc ?? 20)
}

function place(view: ViewNode, rect: Rect, y: number, out: Layout) {
  if (view.node.kind === 'file') return placeBuilding(view, rect, y, out)
  const gap = view.depth === 0 ? 0 : 0.1
  const r = inset(rect, gap)
  out.plates.set(view.id, { x: r.x0 + r.w / 2, z: r.z0 + r.d / 2, w: r.w, d: r.d, y, h: PLATE_H })
  if (!view.children.length) return
  const pad = view.depth === 0 ? 0.5 : view.depth === 1 ? 0.32 : 0.2
  const inner = inset(r, pad)
  let rects: Rect[]
  if (view.depth === 0) {
    // 맨 위 앞줄: 프론트 → 그 밖 → 백엔드 순으로 왼쪽부터 세로 띠(요청이 왼쪽에서 오른쪽으로 흐르게).
    // 뒷줄: tests·scripts 같은 보조 폴더를 treemap으로.
    const order = (v: ViewNode) => (v.aux ? 3 : v.node.layer === 'frontend' ? 0 : v.node.layer === 'backend' ? 2 : 1)
    view.children.sort((a, b) => order(a) - order(b))
    const main = view.children.filter((c) => !c.aux)
    const aux = view.children.filter((c) => c.aux)
    const sum = (list: ViewNode[]) => list.reduce((s, c) => s + c.weight, 0)
    if (!aux.length) rects = slice(main.map((c) => c.weight), inner, 0.6)
    else {
      const gap = 0.8
      const share = Math.min(0.85, Math.max(0.55, sum(main) / (sum(main) + sum(aux))))
      const frontD = (inner.d - gap) * share
      const front = { ...inner, z0: inner.z0 + inner.d - frontD, d: frontD }
      const back = { ...inner, d: inner.d - frontD - gap }
      rects = [...slice(main.map((c) => c.weight), front, 0.6), ...squarify(aux.map((c) => c.weight), back)]
    }
  } else {
    rects = squarify(view.children.map((c) => c.weight), inner)
  }
  view.children.forEach((child, i) => place(child, rects[i], y + PLATE_H, out))
}

function placeBuilding(view: ViewNode, rect: Rect, y: number, out: Layout) {
  const cell = inset(rect, 0.12)
  // 칸 가운데에 정사각 바닥(칸이 작으면 칸에 맞춤)
  const side = footprint(view.node)
  const r = { w: Math.min(side, cell.w), d: Math.min(side, cell.d) }
  const cx = cell.x0 + cell.w / 2
  const cz = cell.z0 + cell.d / 2
  const floors = view.floors.length ? view.floors : [view.node]
  let cursor = y
  // 아래층부터 쌓으므로 뒤에서부터(파일 아래쪽 코드부터)
  for (let i = floors.length - 1; i >= 0; i--) {
    const node = floors[i]
    const inClass = node.kind === 'method'
    const h = floorHeight(node)
    const k = inClass ? 0.84 : 1
    out.floors.set(node.id, { x: cx, z: cz, w: r.w * k, d: r.d * k, y: cursor, h })
    out.floorOwner.set(node.id, node)
    cursor += h + FLOOR_GAP
  }
  out.buildings.set(view.id, { x: cx, z: cz, w: r.w, d: r.d, y, h: cursor - y - FLOOR_GAP })
}

function floorHeight(node: GraphNode): number {
  if (node.kind === 'class') return 0.08
  if (node.kind === 'file') return 0.14 + 0.04 * Math.sqrt(node.loc ?? 10)
  return 0.1 + 0.06 * Math.sqrt(node.loc ?? 4)
}

function inset(r: Rect, by: number): Rect {
  const bx = Math.min(by, r.w * 0.25)
  const bz = Math.min(by, r.d * 0.25)
  return { x0: r.x0 + bx, z0: r.z0 + bz, w: r.w - bx * 2, d: r.d - bz * 2 }
}

/** 무게대로 가로로 나란히 자른다(사이 간격 gap). */
function slice(weights: number[], r: Rect, gap: number): Rect[] {
  const total = weights.reduce((s, w) => s + w, 0) || 1
  const usable = r.w - gap * (weights.length - 1)
  let x = r.x0
  return weights.map((w) => {
    const width = (usable * w) / total
    const rect = { x0: x, z0: r.z0, w: width, d: r.d }
    x += width + gap
    return rect
  })
}

/** Squarified treemap(Bruls, Huizing, van Wijk). 결과는 입력 순서와 같다. */
export function squarify(weights: number[], rect: Rect): Rect[] {
  const total = weights.reduce((s, w) => s + w, 0)
  const result: Rect[] = new Array(weights.length)
  if (!weights.length || total <= 0) return weights.map(() => ({ ...rect, w: 0, d: 0 }))
  const area = rect.w * rect.d
  const items = weights
    .map((w, i) => ({ i, a: (w / total) * area }))
    .sort((p, q) => q.a - p.a)
  let free = { ...rect }
  let row: typeof items = []
  const worst = (list: typeof items, side: number) => {
    const s = list.reduce((acc, it) => acc + it.a, 0)
    let max = 0
    for (const it of list) max = Math.max(max, (side * side * it.a) / (s * s), (s * s) / (side * side * it.a))
    return max
  }
  const flush = () => {
    const s = row.reduce((acc, it) => acc + it.a, 0)
    if (free.w >= free.d) {
      const colW = s / free.d
      let z = free.z0
      for (const it of row) {
        const h = it.a / colW
        result[it.i] = { x0: free.x0, z0: z, w: colW, d: h }
        z += h
      }
      free = { x0: free.x0 + colW, z0: free.z0, w: free.w - colW, d: free.d }
    } else {
      const rowH = s / free.w
      let x = free.x0
      for (const it of row) {
        const w = it.a / rowH
        result[it.i] = { x0: x, z0: free.z0, w, d: rowH }
        x += w
      }
      free = { x0: free.x0, z0: free.z0 + rowH, w: free.w, d: free.d - rowH }
    }
    row = []
  }
  for (const it of items) {
    const side = Math.min(free.w, free.d)
    if (!row.length || worst([...row, it], side) <= worst(row, side)) row.push(it)
    else {
      flush()
      row.push(it)
    }
  }
  if (row.length) flush()
  return result
}

/** 상자 여러 개를 감싸는 상자. */
export function unionBox(boxes: Box[]): Box | undefined {
  if (!boxes.length) return undefined
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity, y0 = Infinity, y1 = -Infinity
  for (const b of boxes) {
    x0 = Math.min(x0, b.x - b.w / 2)
    x1 = Math.max(x1, b.x + b.w / 2)
    z0 = Math.min(z0, b.z - b.d / 2)
    z1 = Math.max(z1, b.z + b.d / 2)
    y0 = Math.min(y0, b.y)
    y1 = Math.max(y1, b.y + b.h)
  }
  return { x: (x0 + x1) / 2, z: (z0 + z1) / 2, w: x1 - x0, d: z1 - z0, y: y0, h: y1 - y0 }
}
