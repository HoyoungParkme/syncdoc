// 인프라 세계: 코드를 장비(브라우저·백엔드 서버) 받침대 위에 올리고, 둘레에 DB·저장소·외부 API 장비를 놓는다.
// 멀리서 보면 장비와 네트워크 선(인프라), 다가가면 받침대 위 코드(폴더·파일·함수). 하나의 장면을 확대·축소한다.
// 위치: 이 PC 구역(개발 서버·도커 컨테이너)과 외부 구역(다른 컴퓨터·클라우드)을 떼어 놓아 요청이 "멀리" 가는 게 보이게.

import type { InfraLink, InfraMap, InfraNode } from './types'
import { type Box, type Layout, PLATE_H, unionBox } from './layout'
import { type Model, type ViewNode, deviceFor } from './model'

export type Device = { id: string; node: InfraNode; box: Box; carries: boolean } // carries: 위에 코드가 얹힌 장비
export type Zone = { id: string; name: string; sub: string; box: Box }
export type World = { devices: Device[]; zones: Zone[]; links: InfraLink[]; fit: Box } // fit: 인프라 단계 카메라가 담을 상자

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** 코드를 얹는 서버 장비들(백엔드가 여럿이면 여럿) */
export const serversOf = (infra: InfraMap | undefined) => (infra?.nodes ?? []).filter((n) => n.kind === 'backend')

/**
 * 파일·폴더 경로가 속한 서버 장비: 코드 폴더(dir)가 가장 길게 겹치는 것. 서버가 하나면 늘 그 서버.
 * strict: 서버가 여럿일 때 어느 서버 폴더에도 들지 않으면(testbed·shared …) 없음. 아니면 그 폴더가 품은 서버 · 첫 서버
 */
export function serverFor(infra: InfraMap | undefined, p: string, strict = false): InfraNode | undefined {
  const servers = serversOf(infra)
  if (servers.length <= 1) return servers[0]
  let best: InfraNode | undefined
  for (const s of servers) {
    const dir = s.dir ?? ''
    if (dir && p !== dir && !p.startsWith(dir + '/')) continue
    if (!best || dir.length > (best.dir ?? '').length) best = s
  }
  if (best || strict) return best ?? servers.find((s) => s.dir && s.dir.startsWith(p + '/'))
  return servers.find((s) => s.dir && s.dir.startsWith(p + '/')) ?? servers[0]
}

/** 실행 기록에서 실제로 접속한 대상(app/api/traces/[slug]/infra) */
export type InfraSeen = { kind: string; target: string; count: number; last: string }
const LOOPBACK = /^(localhost|127\.\d+\.\d+\.\d+|::1|0\.0\.0\.0|host\.docker\.internal)$/

/**
 * 실행 기록이 설정보다 정확하다: 서버가 실제로 접속한 호스트로 장비 위치를 고친다.
 * 루프백이 아닌 주소(172.x, db.example.com …)에 붙었다면 그 장비는 이 PC 밖(외부)이다.
 */
export function withRuntime(model: Model, infra: InfraMap | undefined, seen: InfraSeen[]): InfraMap | undefined {
  if (!infra || !seen.length) return infra
  const nodes = infra.nodes.map((n) => ({ ...n, evidence: [...n.evidence] }))
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const best = new Map<string, InfraSeen>() // 장비마다 가장 많이 접속한 대상
  for (const s of seen) {
    const id = deviceFor(model, s)
    if (!id) continue
    const cur = best.get(id)
    if (!cur || s.count > cur.count) best.set(id, s)
  }
  for (const [id, s] of best) {
    const n = byId.get(id)
    if (!n) continue
    const hostPort = s.target.replace(/^[\w+.-]+:\/\//, '').split('/')[0]
    const host = hostPort.replace(/:\d+$/, '')
    n.evidence.push(`실행 기록: 실제 접속 ${hostPort} (${s.count}번)`)
    n.host = hostPort
    n.where = LOOPBACK.test(host) ? (n.where === 'external' ? 'local' : n.where) : 'external'
  }
  return { ...infra, nodes }
}

/** 장비 모양 크기(한 변 U 기준): DB는 높게, 캐시는 낮게 … */
const SIZE: Record<string, [number, number, number]> = {
  db: [0.8, 0.8, 1.15],
  cache: [0.7, 0.7, 0.6],
  storage: [0.95, 0.7, 0.75],
  queue: [1.05, 0.5, 0.5],
  search: [0.8, 0.8, 0.9],
  api: [0.8, 0.8, 0.95],
}

/** 상자들을 한 번씩만 옮긴다(흐름 배치는 층과 건물이 같은 상자를 나눠 쓴다) */
function mover(dy: number) {
  const done = new Set<Box>()
  return (b: Box | undefined, dx = 0) => {
    if (!b || done.has(b)) return
    done.add(b)
    b.x += dx
    b.y += dy
  }
}

function moveSubtree(layout: Layout, view: ViewNode, move: (b: Box | undefined, dx?: number) => void, dx: number) {
  const walk = (v: ViewNode) => {
    move(layout.plates.get(v.id), dx)
    move(layout.buildings.get(v.id), dx)
    for (const f of v.floors) move(layout.floors.get(f.id), dx)
    v.children.forEach(walk)
  }
  walk(view)
}

/** 받침대·장비·구역 크기의 기준 */
function units(layout: Layout) {
  const size = Math.max(layout.bounds.w, layout.bounds.d, 8)
  const U = clamp(size * 0.11, 3, 12) // 장비 한 변
  return { H: clamp(size * 0.045, 1.1, 4), U, G: U * 0.9 }
}

/** 코드가 얹힌 받침대 + 나머지 장비 배치 + 구역. carriers: 받침대 상자(코드 아래), others: DB·API … */
function place(carriers: Device[], others: InfraNode[], links: InfraLink[], extra: Box[], U: number, G: number): World {
  const anchor = unionBox(carriers.map((d) => d.box)) ?? { x: 0, z: 0, w: U, d: U, y: 0, h: 0 }
  const devices = [...carriers]
  const column = (nodes: InfraNode[], x0: number): Box[] => {
    // 받침대 오른쪽에 세로(z)로 줄 세운다. 많으면 두 줄
    const per = Math.max(2, Math.ceil(nodes.length / Math.ceil(nodes.length / 4)))
    const boxes: Box[] = []
    nodes.forEach((n, i) => {
      const [sw, sd, sh] = SIZE[n.kind] ?? [0.8, 0.8, 0.8]
      const col = Math.floor(i / per)
      const row = i % per
      const rows = Math.min(per, nodes.length - col * per)
      const pitch = U + G * 0.55
      const box = {
        x: x0 + col * (U + G * 0.6) + U / 2,
        z: anchor.z + (row - (rows - 1) / 2) * pitch,
        w: U * sw,
        d: U * sd,
        y: PLATE_H,
        h: U * sh,
      }
      devices.push({ id: n.id, node: n, box, carries: false })
      boxes.push(box)
    })
    return boxes
  }
  const local = others.filter((n) => n.where !== 'external')
  const external = others.filter((n) => n.where === 'external')
  const right = anchor.x + anchor.w / 2
  const localBoxes = column(local, right + G)
  const localZone = pad(unionBox([...carriers.map((d) => d.box), ...localBoxes, ...extra])!, U * 0.45)
  const zones: Zone[] = [
    {
      id: 'zone:local',
      name: '이 PC',
      sub: local.some((n) => n.where === 'container') ? '개발 서버 · 도커 컨테이너' : '개발 서버',
      box: { ...localZone, y: 0, h: PLATE_H },
    },
  ]
  if (external.length) {
    const extBoxes = column(external, localZone.x + localZone.w / 2 + U * 1.8)
    const z = pad(unionBox(extBoxes)!, U * 0.45)
    zones.push({ id: 'zone:external', name: '외부 · 클라우드', sub: '다른 컴퓨터 · 인터넷 너머', box: { ...z, y: 0, h: PLATE_H } })
  }
  const ids = new Set(devices.map((d) => d.id))
  // 카메라는 구역과 장비만 담는다(보조 폴더의 높은 건물에 끌려 너무 멀어지지 않게)
  const fit = unionBox([...zones.map((z) => z.box), ...devices.map((d) => d.box)])!
  fit.h = Math.max(fit.h, U * 1.6)
  return { devices, zones, links: links.filter((l) => ids.has(l.from) && ids.has(l.to)), fit }
}

const pad = (b: Box, m: number): Box => ({ ...b, w: b.w + m * 2, d: b.d + m * 2 })

function setBounds(layout: Layout, world: World) {
  const all = unionBox([...world.zones.map((z) => z.box), ...world.devices.map((d) => d.box), layout.bounds])!
  let top = all.y + all.h
  for (const b of layout.floors.values()) top = Math.max(top, b.y + b.h)
  layout.bounds = { ...all, y: 0, h: top }
}

/**
 * 도시 보기: 맨 위 구역 중 프론트는 브라우저, 백엔드는 그 코드의 서버 받침대 위로 올린다(보조 폴더는 바닥에 그대로).
 * 서버가 여럿(FastAPI + Spring …)이면 받침대도 여럿. 루트 판은 「이 PC」 구역이 된다.
 */
export function worldCity(root: ViewNode, layout: Layout, infra: InfraMap | undefined): World | undefined {
  if (!infra?.nodes.length) return undefined
  const { H, U, G } = units(layout)
  const front = root.children.filter((v) => !v.aux && v.node.layer === 'frontend')
  const back = root.children.filter((v) => !v.aux && v.node.layer !== 'frontend')
  const aux = root.children.filter((v) => v.aux)
  const groupBox = (vs: ViewNode[]) => unionBox(vs.map((v) => layout.plates.get(v.id) ?? layout.buildings.get(v.id)).filter((b): b is Box => !!b))
  // 서버마다 그 코드 폴더. 서버가 여럿일 때 어느 서버에도 들지 않는 폴더(testbed …)는 받침대 없이 바닥에
  const byServer = new Map<string, ViewNode[]>()
  const floor: ViewNode[] = []
  for (const v of back) {
    const s = serverFor(infra, v.node.path, true)
    if (s) byServer.set(s.id, [...(byServer.get(s.id) ?? []), v])
    else floor.push(v)
  }
  const carried = [...byServer.values()].flat()
  const fb0 = groupBox(front)
  const bb0 = groupBox(carried)
  // 브라우저와 서버 사이를 띄운다(앞쪽 줄이 붙어 있으면 받침대가 맞닿아 한 덩이로 보인다)
  const dx = fb0 && bb0 ? Math.min(0, bb0.x - bb0.w / 2 - G - (fb0.x + fb0.w / 2)) : 0
  const move = mover(H)
  for (const v of front) moveSubtree(layout, v, move, dx)
  // 서버 받침대끼리도 띄운다: 왼쪽부터, 앞 받침대 오른쪽 끝 + 간격보다 왼쪽에 있으면 그 오른쪽 전부를 민다
  const groups = [...byServer.entries()].map(([id, vs]) => ({ id, vs, box: groupBox(vs)! })).filter((g) => g.box).sort((a, b) => a.box.x - b.box.x)
  const slide = mover(0)
  const pad = U * 0.15
  for (let i = 1; i < groups.length; i++) {
    const prev = groups[i - 1].box
    const need = prev.x + prev.w / 2 + pad * 2 + G * 0.6 - (groups[i].box.x - groups[i].box.w / 2)
    if (need <= 0) continue
    const edge = groups[i].box.x - groups[i].box.w / 2 - 0.01
    for (const g of groups.slice(i)) for (const v of g.vs) moveSubtree(layout, v, slide, need)
    for (const v of floor) if ((layout.plates.get(v.id) ?? layout.buildings.get(v.id))!.x > edge) moveSubtree(layout, v, slide, need)
    for (const g of groups.slice(i)) g.box = groupBox(g.vs)!
  }
  for (const v of carried) moveSubtree(layout, v, move, 0)
  const carriers: Device[] = []
  const pedestal = (b: Box | undefined, id: string) => {
    const node = infra.nodes.find((n) => n.id === id)
    if (!b || !node) return
    carriers.push({ id, node, box: { x: b.x, z: b.z, w: b.w + U * 0.3, d: b.d + U * 0.3, y: PLATE_H, h: H }, carries: true })
  }
  pedestal(groupBox(front), 'infra:browser')
  for (const [id, vs] of byServer) pedestal(groupBox(vs), id)
  // 코드가 얹히지 않은 서버(같은 폴더의 두 번째 서버 …)는 다른 장비처럼 옆에
  const onPedestal = new Set(carriers.map((c) => c.id))
  const others = infra.nodes.filter((n) => n.kind !== 'browser' && !onPedestal.has(n.id))
  const ground = [...aux, ...floor].map((v) => layout.plates.get(v.id) ?? layout.buildings.get(v.id)).filter((b): b is Box => !!b)
  const world = place(carriers, others, infra.links, ground, U, G)
  // 루트 판 = 이 PC 구역
  const zone = world.zones[0].box
  const rootPlate = layout.plates.get(root.id)
  if (rootPlate) Object.assign(rootPlate, { x: zone.x, z: zone.z, w: zone.w, d: zone.d })
  setBounds(layout, world)
  return world
}

/**
 * API 흐름 보기: 프론트 열은 브라우저, 백엔드 열은 이 API 서버의 받침대 위. 이 API의 함수가 쓰는 장비만 오른쪽에 놓는다.
 * used: 흐름 안 함수의 호출 단계가 가리키는 장비 id, server: 라우트가 든 서버 장비 id
 */
export function worldFlow(
  layout: Layout,
  columns: Array<{ plateId: string; front: boolean; ids: string[] }>,
  infra: InfraMap | undefined,
  used: Set<string>,
  server = 'infra:backend'
): World | undefined {
  if (!infra?.nodes.length) return undefined
  const { H, U, G } = units(layout)
  const move = mover(H)
  for (const c of columns) {
    move(layout.plates.get(c.plateId))
    for (const id of c.ids) {
      move(layout.floors.get(id))
      move(layout.buildings.get(id))
    }
  }
  const carriers: Device[] = []
  const pedestal = (cols: typeof columns, id: string) => {
    const node = infra.nodes.find((n) => n.id === id)
    const b = unionBox(cols.map((c) => layout.plates.get(c.plateId)).filter((x): x is Box => !!x))
    if (!b || !node) return
    carriers.push({ id, node, box: { x: b.x, z: b.z, w: b.w + U * 0.25, d: b.d + U * 0.25, y: PLATE_H, h: H }, carries: true })
  }
  pedestal(columns.filter((c) => c.front), 'infra:browser')
  pedestal(columns.filter((c) => !c.front), server)
  const others = infra.nodes.filter((n) => used.has(n.id) && n.kind !== 'browser' && n.kind !== 'backend')
  const world = place(carriers, others, infra.links, [], U, G * 0.8)
  const rootPlate = layout.plates.get('flow')
  if (rootPlate) {
    const zone = world.zones[0].box
    Object.assign(rootPlate, { x: zone.x, z: zone.z, w: zone.w, d: zone.d })
  }
  setBounds(layout, world)
  return world
}
