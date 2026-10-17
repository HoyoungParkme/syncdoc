/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. view_arc lib/viewer/scene.ts를 옮겼다(카드 CG) — 구역·받침대·장비·고른 것 이름표가 4.1~4.4 */
// 코드 도시 3D 씬. React와는 메서드(focus, select, setTrace …)와 콜백으로만 주고받는다.
// 판·층은 InstancedMesh 두 개로 그려서 파일·함수가 수천 개여도 그릴 물체 수가 늘지 않는다.

import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import type { GraphEdge, GraphNode } from './types'
import { type Box, type Layout, unionBox } from './layout'
import { type Model, type Shape, type TraceEvent, type ViewNode, FUNCTION_KINDS, displayName } from './model'
import type { Device, World } from './world'

export type SceneCallbacks = {
  onHover: (id: string | null, x: number, y: number) => void
  onClick: (id: string) => void
  // API 흐름에서 블록을 다른 열로 끌어 옮김: 끄는 동안(column = 아래 열 판 id), 놓았을 때
  onDrag?: (drag: { id: string; column: string | null; x: number; y: number } | null) => void
  onDrop?: (id: string, column: string | null) => void
  onTraceStep: (index: number) => void
  onTraceEnd: () => void
}

export const COLORS = {
  plate: ['#191d23', '#20252c', '#272d35', '#2e353e', '#353d47', '#3c4550'],
  backend: { function: '#dcd8cc', method: '#cbc6b8', class: '#c57e45', route: '#ff7a1a', file: '#6b6862' },
  frontend: { function: '#9fb6c8', method: '#8ea4b6', class: '#5e7d92', component: '#62b6c8', hook: '#a99be0', file: '#5d6670' },
  call: '#ff8a3a',
  incoming: '#79a6dc',
  http: '#ffb347',
  depends: '#c57e45',
  renders: '#62b6c8',
  ret: '#6fd3c4',
  raise: '#ff4d5e',
  external: '#8a919b',
  dim: '#15191e',
  select: '#ff7a1a',
  covered: '#3ddc84',
  specOk: '#5b9cff',
  specDiff: '#ff9a3c',
}

const EVENT_SECONDS = { call: 0.8, return: 0.65, external: 0.32, raise: 0.6, cycle: 0.4, skipped: 0.25 }
const MAX_LABELS = 90
const TRAIL = 7

type LabelSpec = {
  key: string
  text: string
  sub?: string
  anchor: THREE.Vector3
  tone: string
  size: 'lg' | 'md' | 'sm'
  center?: boolean // 블록 아래 가운데에 붙인다(API 흐름)
  color?: string // 왼쪽 띠 색(역할 색)
  alts?: THREE.Vector3[] // 앞선 이름표와 겹치면 차례로 옮겨 볼 자리
  mark?: 'zone' | 'plinth' | 'device' | 'pick' // UI-19 요소 번호 — 구역 4.1 · 받침대 4.2 · 장비 4.3 · 고른 것 4.4
}

const LABEL_MAX = 34 // 이보다 긴 이름은 줄임표

/** 모양별 단위 도형(1×1×1 상자에 맞춤). */
function shapeGeometry(shape: Shape): THREE.BufferGeometry {
  switch (shape) {
    case 'rounded':
      return new RoundedBoxGeometry(1, 1, 1, 3, 0.16)
    case 'hex':
      return new THREE.CylinderGeometry(0.56, 0.56, 1, 6)
    case 'oct':
      return new THREE.CylinderGeometry(0.54, 0.54, 1, 8)
    case 'cylinder':
      return new THREE.CylinderGeometry(0.5, 0.5, 1, 28)
    case 'cone':
      return new THREE.ConeGeometry(0.58, 1, 28)
    case 'sphere':
      return new THREE.SphereGeometry(0.55, 24, 16)
    default:
      return new THREE.BoxGeometry(1, 1, 1)
  }
}

export function floorColor(node: GraphNode): string {
  if (node.layer === 'frontend') {
    const c = COLORS.frontend
    if (node.kind === 'component') return c.component
    if (node.kind === 'hook') return c.hook
    if (node.kind === 'class') return c.class
    if (node.kind === 'method') return c.method
    if (node.kind === 'file') return c.file
    return c.function
  }
  const c = COLORS.backend
  if (node.route) return c.route
  if (node.kind === 'class') return c.class
  if (node.kind === 'method') return c.method
  if (node.kind === 'file') return c.file
  return c.function
}

export class CodeScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private plateMesh: THREE.InstancedMesh
  private floorMeshes: THREE.InstancedMesh[] = [] // 모양마다 하나
  private floorSlot: Array<{ mesh: THREE.InstancedMesh; i: number }> = [] // 층 번호 → 어느 메시의 몇 번째
  private meshFloors = new Map<THREE.InstancedMesh, number[]>() // 메시의 몇 번째 → 층 번호(클릭 판정)
  private flowGroup = new THREE.Group() // API 흐름: 함수 사이 호출(계층 위반은 빨강)
  private plateIds: string[] = []
  private floorIds: string[] = []
  private floorIndex = new Map<string, number>()
  private plateIndex = new Map<string, number>()
  private baseFloorColor: THREE.Color[] = []
  private basePlateColor: THREE.Color[] = []
  private floorAncestors: string[][] = [] // 층마다 그 위로 이어지는 보이는 노드 id
  private plateAncestors: string[][] = []
  private selectBox: THREE.LineSegments
  private hoverBox: THREE.LineSegments
  private activeBox: THREE.LineSegments
  private arcGroup = new THREE.Group()
  private httpGroup = new THREE.Group()
  private traceGroup = new THREE.Group()
  private packet: THREE.Mesh
  private trail: THREE.Mesh[] = []
  private pulse: THREE.Mesh
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2()
  private pointerDirty = false
  private pointerClient = { x: 0, y: 0 }
  private downAt: { x: number; y: number } | null = null
  private drag: { id: string; column: string | null; active: boolean } | null = null
  private badges: Array<{ el: HTMLElement; curve: THREE.Curve<THREE.Vector3> }> = [] // API 흐름: 호출 순서 번호
  private traceColor: string | null = null // 실행 기록 재생: 이 갈래의 색
  // 인프라 세계: 장비(브라우저·서버 받침대, DB·외부 API …)와 구역·연결선
  private devices = new Map<string, Device>()
  private deviceMeshes: THREE.Mesh[] = []
  private worldGroup = new THREE.Group()
  private codeBox: Box | undefined // 흐름 재생: 코드 쪽 참여 함수를 감싼 상자(장비로 갔다 돌아올 때 돌아갈 자리)
  private farView = false // 흐름 재생: 지금 카메라가 인프라 크기로 빠져 있는지
  private dropBox: THREE.LineSegments
  private hoverId: string | null = null
  private labelEls: HTMLDivElement[] = []
  private labelSpecs: LabelSpec[] = []
  private labelBoxes: Array<[number, number, number, number] | undefined> = [] // 여백 x, y, 너비, 높이
  private desiredTarget = new THREE.Vector3()
  private desiredPos = new THREE.Vector3()
  private flying = false
  private insets = { left: 0, right: 0 }
  private insetsSet = false
  private focusView: ViewNode
  private selectedId: string | null = null
  // 흐름 재생
  private trace: TraceEvent[] = []
  private traceRoot: string | null = null
  private traceParticipants = new Set<string>()
  private traceIdx = -1
  private traceT = 0
  private playing = false
  private speed = 1
  private follow = false
  private traversed = new Set<string>()
  private curves = new Map<string, THREE.QuadraticBezierCurve3>()
  private raf = 0
  private last = performance.now()
  private cleanups: Array<() => void> = []
  private disposables: Array<{ dispose: () => void }> = []
  private k = 1 // 도시 크기 배율: 큰 도시에서도 호·패킷이 보이게
  private dirty = true // 다음 프레임에 다시 그려야 하는지(변화가 없으면 그리지 않는다)
  private plateMatrix: THREE.Matrix4[] = [] // 원래 자리(숨길 때 0으로 줄였다가 되돌린다)
  private floorMatrix: THREE.Matrix4[] = []
  private exploded = new Map<string, Box>() // 파일 단계에서 벌려 놓은 층의 원래 상자
  private explodedBuildings = new Map<string, Box>()
  private strips: THREE.Mesh[] = [] // 구역 앞 가장자리 빛 띠
  private overlay: Record<string, string> | null = null // 덧칠 보기(커버리지·명세): 층 id → 색. 없는 층은 어둡게

  private container: HTMLElement
  private labelLayer: HTMLElement
  private model: Model
  private layout: Layout
  private cb: SceneCallbacks

  constructor(container: HTMLElement, labelLayer: HTMLElement, model: Model, layout: Layout, cb: SceneCallbacks) {
    this.container = container
    this.labelLayer = labelLayer
    this.model = model
    this.layout = layout
    this.cb = cb
    const width = Math.max(1, container.clientWidth)
    const height = Math.max(1, container.clientHeight)
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    this.renderer.setSize(width, height)
    this.renderer.setClearColor(0x000000, 0)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    container.appendChild(this.renderer.domElement)
    this.renderer.domElement.style.display = 'block'

    const b = layout.bounds
    const size = Math.max(b.w, b.d, 4)
    this.k = Math.max(1, size / 14)
    // API 흐름도 도시처럼 원근을 둔다(조금 좁은 화각): 받침대·장비·건물 높이가 입체로 보이게
    this.camera = new THREE.PerspectiveCamera(model.flow ? 30 : 35, width / height, 0.05, size * 20)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.screenSpacePanning = false
    this.controls.maxPolarAngle = Math.PI * 0.47
    this.controls.minDistance = 1.2
    this.controls.maxDistance = size * 6
    this.controls.rotateSpeed = 0.55
    this.controls.zoomSpeed = 0.9

    this.setupLights(size)
    this.setupGround(size)

    // 판
    const box = new THREE.BoxGeometry(1, 1, 1)
    this.disposables.push(box)
    const plateMat = new THREE.MeshStandardMaterial({ metalness: 0.55, roughness: 0.42 })
    this.plateMesh = new THREE.InstancedMesh(box, plateMat, Math.max(1, layout.plates.size))
    this.plateMesh.receiveShadow = true
    this.plateMesh.castShadow = true
    const m = new THREE.Object3D()
    let i = 0
    for (const [id, p] of layout.plates) {
      m.position.set(p.x, p.y + p.h / 2, p.z)
      m.scale.set(p.w, p.h, p.d)
      m.updateMatrix()
      this.plateMesh.setMatrixAt(i, m.matrix)
      this.plateMatrix.push(m.matrix.clone())
      const view = model.viewOf.get(id)!
      const tone = new THREE.Color(COLORS.plate[Math.min(view.depth, COLORS.plate.length - 1)])
      const aux = ancestorsAux(view)
      if (view.node.layer === 'frontend' && !aux) tone.lerp(new THREE.Color('#3d6b85'), 0.12)
      if (view.node.layer === 'backend' && !aux) tone.lerp(new THREE.Color('#8a5a32'), 0.1)
      if (aux) tone.lerp(new THREE.Color('#111418'), 0.35)
      const tint = model.plateTint?.get(id)
      if (tint) tone.lerp(new THREE.Color(tint), 0.07) // 아주 옅게: 같은 색 블록이 판에 묻히지 않게
      this.basePlateColor.push(tone)
      this.plateMesh.setColorAt(i, tone)
      this.plateIds.push(id)
      this.plateIndex.set(id, i)
      this.plateAncestors.push(ancestorsOf(view))
      i++
    }
    this.plateMesh.count = layout.plates.size
    this.scene.add(this.plateMesh)
    this.addDistrictStrips()

    // 층: 모양마다 InstancedMesh 하나(역할별 모양이 없으면 상자 하나)
    // API 흐름은 반사를 줄여 역할 색이 그대로 보이게(반사광에 색이 하얗게 바래지 않게)
    const floorMat = new THREE.MeshStandardMaterial(
      model.flow ? { metalness: 0.1, roughness: 0.62, envMapIntensity: 0.55 } : { metalness: 0.18, roughness: 0.48 }
    )
    // API 흐름의 블록은 한 덩어리라, 옆면에 층 줄을 그어 도시의 건물처럼(세계 좌표 높이마다 어두운 띠)
    if (model.flow) floorMat.onBeforeCompile = floorLines
    const shapeOf = (id: string): Shape => model.style?.get(id)?.shape ?? 'box'
    const byShape = new Map<Shape, string[]>()
    for (const id of layout.floors.keys()) {
      const shape = shapeOf(id)
      if (!byShape.has(shape)) byShape.set(shape, [])
      byShape.get(shape)!.push(id)
    }
    const meshOf = new Map<Shape, THREE.InstancedMesh>()
    for (const [shape, ids] of byShape) {
      const geo = shape === 'box' ? box : shapeGeometry(shape)
      if (geo !== box) this.disposables.push(geo)
      const mesh = new THREE.InstancedMesh(geo, floorMat, ids.length)
      mesh.castShadow = true
      mesh.receiveShadow = true
      meshOf.set(shape, mesh)
      this.meshFloors.set(mesh, [])
      this.floorMeshes.push(mesh)
    }
    i = 0
    for (const [id, f] of layout.floors) {
      const mesh = meshOf.get(shapeOf(id))!
      const local = this.meshFloors.get(mesh)!
      this.floorSlot.push({ mesh, i: local.length })
      local.push(i)
      m.position.set(f.x, f.y + f.h / 2, f.z)
      m.scale.set(f.w, f.h, f.d)
      m.updateMatrix()
      this.setFloorMatrix(i, m.matrix)
      this.floorMatrix.push(m.matrix.clone())
      const color = new THREE.Color(model.style?.get(id)?.color ?? floorColor(layout.floorOwner.get(id)!))
      if (ancestorsAux(model.viewOf.get(id)!)) color.lerp(new THREE.Color('#4a4f57'), 0.75) // 보조 폴더는 무채색에 가깝게
      this.baseFloorColor.push(color)
      this.setFloorColor(i, color)
      this.floorIds.push(id)
      this.floorIndex.set(id, i)
      this.floorAncestors.push(ancestorsOf(model.viewOf.get(id)!))
      i++
    }
    for (const mesh of this.floorMeshes) this.scene.add(mesh)
    this.disposables.push(plateMat, floorMat)

    // 선택·호버·현재 단계 테두리
    this.selectBox = outlineBox(COLORS.select, 1)
    this.hoverBox = outlineBox('#ffffff', 0.45)
    this.activeBox = outlineBox(COLORS.ret, 1)
    this.dropBox = outlineBox('#facc15', 1)
    this.scene.add(this.selectBox, this.hoverBox, this.activeBox, this.dropBox)

    this.scene.add(this.arcGroup, this.httpGroup, this.traceGroup, this.flowGroup)
    if (model.world) this.buildWorld(model.world)
    this.drawHttpLinks()

    // 흐름 패킷과 꼬리, 바깥 호출 표시용 고리
    const sphere = new THREE.SphereGeometry(0.11, 20, 14)
    this.disposables.push(sphere)
    this.packet = new THREE.Mesh(sphere, glow(COLORS.call))
    this.packet.scale.setScalar(this.k)
    this.packet.visible = false
    this.scene.add(this.packet)
    for (let k = 0; k < TRAIL; k++) {
      const dot = new THREE.Mesh(sphere, glow(COLORS.call, 0.55 - k * 0.07))
      dot.scale.setScalar((0.75 - k * 0.08) * this.k)
      dot.visible = false
      this.trail.push(dot)
      this.scene.add(dot)
    }
    const ring = new THREE.RingGeometry(0.2, 0.26, 40)
    this.disposables.push(ring)
    this.pulse = new THREE.Mesh(ring, glow(COLORS.external, 0.9))
    this.pulse.rotation.x = -Math.PI / 2
    this.pulse.visible = false
    this.scene.add(this.pulse)

    this.focusView = model.root
    if (import.meta.env.DEV) (window as unknown as { __codeScene?: CodeScene }).__codeScene = this
    this.bindEvents()
    this.focus(model.root.id, false)
    this.raf = requestAnimationFrame(this.loop)
  }

  // ------------------------------------------------------------------ 층 도우미(모양별 메시에 나뉘어 있다)

  private setFloorMatrix(g: number, matrix: THREE.Matrix4) {
    const slot = this.floorSlot[g]
    slot.mesh.setMatrixAt(slot.i, matrix)
  }

  private setFloorColor(g: number, color: THREE.Color) {
    const slot = this.floorSlot[g]
    slot.mesh.setColorAt(slot.i, color)
  }

  private touchFloors(what: 'matrix' | 'color') {
    for (const mesh of this.floorMeshes) {
      if (what === 'matrix') mesh.instanceMatrix.needsUpdate = true
      else if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    }
  }

  // ------------------------------------------------------------------ 바깥에서 부르는 것

  /** 3D 위를 덮는 양옆 패널 폭. 바뀌면 보이는 가운데에 다시 맞춘다. */
  setInsets(left: number, right: number) {
    const first = !this.insetsSet
    this.insetsSet = true
    this.insets = { left, right }
    this.resize()
    const box = this.focusView === this.model.root && this.model.world ? this.model.world.fit : this.boxOfView(this.focusView)
    const isFile = this.focusView.node.kind === 'file'
    if (box && !this.traceRoot) this.flyTo(box, !first, isFile ? 1.9 : this.model.flow ? 0.8 : 1, isFile)
  }

  /** 보이는 노드(프로젝트·폴더·파일)에 초점을 맞춘다: 카메라 이동 + 라벨 단위 + 바깥 흐리게. */
  focus(viewId: string, animate = true) {
    const view = this.model.viewOf.get(viewId) ?? this.model.root
    this.focusView = view
    this.explode(view.node.kind === 'file' ? view : null)
    this.applyVisibility()
    const box = view === this.model.root && this.model.world ? this.model.world.fit : this.boxOfView(view)
    if (box) this.flyTo(box, animate, view.node.kind === 'file' ? 1.9 : this.model.flow ? 0.8 : 1, view.node.kind === 'file')
    this.refreshLabels()
    this.applyColors()
  }

  /**
   * 파일 단계: 그 건물의 층 사이를 벌려 함수 이름표가 겹치지 않게 한다(다른 파일로 가면 되돌린다).
   * 층 상자를 바꾸므로 호(곡선) 캐시도 비운다.
   */
  private explode(view: ViewNode | null) {
    const m = new THREE.Object3D()
    const setFloor = (id: string, b: Box) => {
      this.layout.floors.set(id, b)
      const i = this.floorIndex.get(id)
      if (i === undefined) return
      m.position.set(b.x, b.y + b.h / 2, b.z)
      m.scale.set(b.w, b.h, b.d)
      m.updateMatrix()
      this.floorMatrix[i].copy(m.matrix)
      this.setFloorMatrix(i, m.matrix)
    }
    for (const [id, b] of this.exploded) setFloor(id, b)
    for (const [fileId, b] of this.explodedBuildings) this.layout.buildings.set(fileId, b)
    this.exploded.clear()
    this.explodedBuildings.clear()
    if (view && !this.model.flow) {
      // 함수를 바닥에 블록으로 펼친다: 파일 앞쪽 함수부터 열마다 ROWS 개, 열은 왼쪽에서 오른쪽으로
      const ids = view.floors.map((f) => f.id).filter((id) => this.layout.floors.has(id))
      const building = this.layout.buildings.get(view.id)
      if (building && ids.length) {
        const ROWS = Math.min(8, ids.length)
        const cols = Math.ceil(ids.length / ROWS)
        const size = 0.9 * this.k
        const dx = 3.6 * this.k // 열 사이: 오른쪽에 붙는 이름표 자리
        const dz = 1.5 * this.k
        let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity, top = building.y
        ids.forEach((id, i) => {
          const b = this.layout.floors.get(id)!
          this.exploded.set(id, b)
          const col = Math.floor(i / ROWS)
          const row = i % ROWS
          const h = Math.max(0.25, b.h * 1.6)
          const box = {
            x: building.x + (col - (cols - 1) / 2) * dx - dx * 0.25,
            z: building.z + (row - (ROWS - 1) / 2) * dz,
            w: size * (b.w < building.w ? 0.85 : 1), // 클래스 메서드는 조금 작게
            d: size * (b.w < building.w ? 0.85 : 1),
            y: building.y,
            h,
          }
          setFloor(id, box)
          x0 = Math.min(x0, box.x - box.w / 2)
          x1 = Math.max(x1, box.x + box.w / 2 + dx * 0.6)
          z0 = Math.min(z0, box.z - box.d / 2)
          z1 = Math.max(z1, box.z + box.d / 2)
          top = Math.max(top, box.y + box.h)
        })
        this.explodedBuildings.set(view.id, building)
        this.layout.buildings.set(view.id, { x: (x0 + x1) / 2, z: (z0 + z1) / 2, w: x1 - x0, d: z1 - z0, y: building.y, h: top - building.y })
      }
    }
    this.curves.clear()
    this.touchFloors('matrix')
    this.dirty = true
  }

  /** 도시 보기에서 폴더·파일에 들어가면 그 밖(판·층)은 숨긴다. 흐름 재생 중에는 모두 보인다. */
  private applyVisibility() {
    const zero = new THREE.Matrix4().makeScale(0, 0, 0)
    const focusId = this.focusView.id
    const hide = !this.traceRoot && !this.model.flow && focusId !== this.model.root.id
    for (let i = 0; i < this.floorIds.length; i++)
      this.setFloorMatrix(i, !hide || this.floorAncestors[i].includes(focusId) ? this.floorMatrix[i] : zero)
    for (let i = 0; i < this.plateIds.length; i++)
      this.plateMesh.setMatrixAt(i, !hide || this.plateAncestors[i].includes(focusId) ? this.plateMatrix[i] : zero)
    this.touchFloors('matrix')
    this.plateMesh.instanceMatrix.needsUpdate = true
    for (const strip of this.strips) strip.visible = !hide
    this.httpGroup.visible = !hide && !this.traceRoot
    // 재생 중에도 흐름의 다른 호는 흐리게 남긴다: 이번에 간 길만 진하게, 안 간 길은 배경으로
    this.flowGroup.visible = true
    this.flowGroup.traverse((o) => {
      const mat = (o as THREE.Mesh).material as THREE.MeshBasicMaterial | undefined
      if (mat?.userData.base !== undefined) {
        mat.opacity = this.traceRoot ? mat.userData.base * 0.3 : mat.userData.base
        mat.transparent = mat.opacity < 1
      }
    })
    for (const b of this.badges) b.el.dataset.dim = this.traceRoot ? '1' : ''
    this.dirty = true
  }

  /** 선택: 테두리 + 들어오고 나가는 호출 호. */
  select(id: string | null) {
    this.selectedId = id
    this.placeOutline(this.selectBox, id ? this.boxOf(id) : undefined, 0.05)
    this.drawSelectionArcs()
    this.refreshLabels()
    this.applyColors()
  }

  setTrace(rootId: string | null, events: TraceEvent[], color: string | null = null) {
    this.traceColor = color
    this.trace = events
    this.traceRoot = rootId
    this.traceIdx = -1
    this.traceT = 0
    this.playing = false
    this.traversed.clear()
    this.curves.clear()
    clearGroup(this.traceGroup)
    this.traceParticipants = new Set(rootId ? [rootId] : [])
    for (const e of events)
      if (e.type === 'call') {
        this.traceParticipants.add(e.from)
        this.traceParticipants.add(e.to)
      }
    this.packet.visible = false
    this.trail.forEach((t) => (t.visible = false))
    this.pulse.visible = false
    this.activeBox.visible = false
    for (const e of events) if (e.type === 'call' && this.devices.has(e.to)) this.traceParticipants.add(e.to)
    this.farView = false
    // 코드 쪽 참여 함수만 감싼 상자: 장비(DB·외부 API)로 갔다가 이 자리로 돌아온다
    this.codeBox = unionBox([...this.traceParticipants].filter((id) => !this.devices.has(id)).map((id) => this.boxOf(id)).filter((b): b is Box => !!b))
    if (rootId) {
      const box = this.model.flow ? unionBox([...this.traceParticipants].map((id) => this.boxOf(id)).filter((b): b is Box => !!b)) : this.codeBox
      if (box) this.flyTo(box, true, this.model.flow ? 1.05 : 1.3) // 라벨이 옆으로 나오므로 여유를 더 둔다
    }
    this.drawSelectionArcs()
    this.applyVisibility()
    this.refreshLabels()
    this.applyColors()
  }

  /** API 흐름: 함수 사이 호출을 늘 보이게. 보통 호출은 흐리게, 계층 위반은 굵은 빨강 + 화살촉. */
  setFlowEdges(edges: Array<{ from: string; to: string; violation?: string }>) {
    clearGroup(this.flowGroup)
    for (const e of edges) {
      const curve = this.curveBetween(e.from, e.to)
      if (!curve) continue
      const bad = !!e.violation
      const radius = (bad ? 0.03 : 0.012) * this.k
      const color = bad ? COLORS.raise : '#8b95a1'
      const tube = glow(color, bad ? 0.95 : 0.3)
      tube.userData.base = tube.opacity
      this.flowGroup.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 36, radius, 6, false), tube))
      if (bad) {
        const headMat = glow(color, 1)
        headMat.userData.base = 1
        const head = new THREE.Mesh(new THREE.ConeGeometry(radius * 3.2, radius * 9, 10), headMat)
        head.position.copy(curve.getPoint(0.96))
        head.lookAt(curve.getPoint(1))
        head.rotateX(Math.PI / 2)
        this.flowGroup.add(head)
      }
    }
    this.applyVisibility()
  }

  /**
   * API 흐름: 호출 순서 번호를 호 가운데에 단다(재생하지 않아도 1 → 2 → 3 순서가 읽히게).
   * bad: 레이어 위반 호출(빨간 번호).
   */
  setFlowOrder(items: Array<{ from: string; to: string; n: number; bad?: boolean }>) {
    for (const b of this.badges) b.el.remove()
    this.badges = []
    for (const it of items) {
      const curve = this.curveBetween(it.from, it.to)
      if (!curve) continue
      const el = document.createElement('div')
      el.className = 'cv-badge'
      el.textContent = String(it.n)
      if (it.bad) el.dataset.bad = '1'
      this.labelLayer.appendChild(el)
      this.badges.push({ el, curve })
    }
    this.applyVisibility()
  }

  play() {
    if (!this.trace.length) return
    if (this.traceIdx >= this.trace.length - 1 && this.traceT >= 1) this.seek(-1)
    this.playing = true
  }

  pause() {
    this.playing = false
    this.dirty = true
  }

  /** i번째 단계로 바로 간다(-1은 처음). */
  seek(index: number) {
    this.dirty = true
    this.traceIdx = Math.max(-1, Math.min(index, this.trace.length - 1))
    this.traceT = index < 0 ? 1 : 0
    this.traversed.clear()
    clearGroup(this.traceGroup)
    for (let k = 0; k < this.traceIdx; k++) this.markTraversed(this.trace[k])
    if (this.traceIdx >= 0) this.enterEvent(this.traceIdx)
    else {
      this.packet.visible = false
      this.trail.forEach((t) => (t.visible = false))
      this.activeBox.visible = false
    }
    this.cb.onTraceStep(this.traceIdx)
  }

  /** 덧칠 보기: 색을 준 층은 그 색으로, 나머지는 어둡게(커버리지·명세 대조). null이면 끈다. */
  setOverlay(colors: Record<string, string> | null) {
    this.overlay = colors
    this.applyColors()
  }

  setSpeed(speed: number) {
    this.speed = speed
  }

  setFollow(follow: boolean) {
    this.follow = follow
  }

  dispose() {
    cancelAnimationFrame(this.raf)
    for (const fn of this.cleanups.reverse()) fn()
    this.controls.dispose()
    clearGroup(this.arcGroup)
    clearGroup(this.httpGroup)
    clearGroup(this.traceGroup)
    clearGroup(this.flowGroup)
    clearGroup(this.worldGroup)
    for (const b of this.badges) b.el.remove()
    this.scene.traverse((o) => {
      const mesh = o as THREE.Mesh
      mesh.geometry?.dispose()
      const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
      mats.forEach((mat) => mat.dispose())
    })
    this.disposables.forEach((d) => d.dispose())
    this.scene.environment?.dispose()
    this.renderer.dispose()
    this.renderer.domElement.remove()
    this.labelEls.forEach((el) => el.remove())
  }

  // ------------------------------------------------------------------ 만들기

  private setupLights(size: number) {
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    const room = new RoomEnvironment()
    this.scene.environment = pmrem.fromScene(room, 0.04).texture
    this.scene.environmentIntensity = 0.55
    room.dispose()
    pmrem.dispose()
    // API 흐름은 빛을 줄인다: 윗면이 너무 밝으면 톤 매핑이 역할 색을 하얗게 바랜다
    const k = this.model.flow ? 0.72 : 1
    this.scene.add(new THREE.HemisphereLight(0xdbe5f4, 0x29211a, 1.6 * k))
    const key = new THREE.DirectionalLight(0xfff1d8, 3.4 * k)
    key.position.set(-size * 0.4, size * 1.1, size * 0.6)
    key.castShadow = true
    key.shadow.mapSize.set(2048, 2048)
    const half = size * 0.75
    Object.assign(key.shadow.camera, { left: -half, right: half, top: half, bottom: -half, near: 0.5, far: size * 4 })
    key.shadow.bias = -0.0004
    key.shadow.normalBias = 0.02
    this.scene.add(key)
    const rim = new THREE.DirectionalLight(0xc4d4ed, 2.2 * k)
    rim.position.set(size * 0.3, size * 0.6, -size)
    this.scene.add(rim)
    const front = new THREE.DirectionalLight(0xffffff, 0.8 * k)
    front.position.set(size * 0.5, size * 0.3, size)
    this.scene.add(front)
  }

  private setupGround(size: number) {
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(size * 8, size * 8), new THREE.ShadowMaterial({ opacity: 0.28 }))
    ground.rotation.x = -Math.PI / 2
    ground.position.y = -0.002
    ground.receiveShadow = true
    this.scene.add(ground)
    const grid = new THREE.GridHelper(size * 4, Math.round(size * 2), 0x3a4048, 0x22272d)
    const gridMat = grid.material as THREE.Material
    gridMat.transparent = true
    gridMat.opacity = 0.35
    grid.position.y = -0.004
    this.scene.add(grid)
  }

  /** 맨 위 구역(프론트·백엔드) 앞 가장자리에 빛 띠. */
  private addDistrictStrips() {
    for (const view of this.model.root.children) {
      const p = this.layout.plates.get(view.id)
      if (!p) continue
      const color =
        this.model.plateTint?.get(view.id) ??
        (view.node.layer === 'frontend' ? COLORS.frontend.component : view.node.layer === 'backend' ? COLORS.select : '#9aa3ad')
      const strip = new THREE.Mesh(new THREE.BoxGeometry(p.w * 0.94, 0.025, 0.035), glow(color, 0.95))
      strip.position.set(p.x, p.y + 0.04, p.z + p.d / 2 + 0.02)
      this.scene.add(strip)
      this.strips.push(strip)
    }
  }

  // ------------------------------------------------------------------ 인프라 세계

  /** 장비(받침대·DB·캐시·저장소·외부 API)와 외부 구역 판, 장비 사이 연결선 */
  private buildWorld(world: World) {
    this.scene.add(this.worldGroup)
    for (const z of world.zones) {
      if (z.id === 'zone:local') continue // 이 PC 구역은 루트 판이 맡는다
      const b = z.box
      const plate = new THREE.Mesh(new THREE.BoxGeometry(b.w, b.h, b.d), new THREE.MeshStandardMaterial({ color: '#1b2030', metalness: 0.55, roughness: 0.42 }))
      plate.position.set(b.x, b.y + b.h / 2, b.z)
      plate.receiveShadow = true
      this.worldGroup.add(plate)
      const strip = new THREE.Mesh(new THREE.BoxGeometry(b.w * 0.94, 0.03, 0.04), glow('#a78bfa', 0.9))
      strip.position.set(b.x, b.y + b.h + 0.02, b.z + b.d / 2 + 0.02)
      this.worldGroup.add(strip)
    }
    for (const d of world.devices) {
      this.devices.set(d.id, d)
      const model = deviceModel(d)
      model.traverse((o) => {
        if ((o as THREE.Mesh).isMesh && o.userData.pick) {
          o.userData.deviceId = d.id
          this.deviceMeshes.push(o as THREE.Mesh)
        }
      })
      this.worldGroup.add(model)
    }
    // 장비 사이 연결: 프로토콜 색. 외부로 가는 선은 구역 사이를 길게 건넌다
    for (const l of world.links) {
      const curve = this.curveBetween(l.from, l.to)
      if (!curve) continue
      this.worldGroup.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.03 * this.k, 8, false), glow(LINK_COLORS[l.protocol] ?? '#8b95a1', 0.5)))
    }
  }

  // ------------------------------------------------------------------ 위치

  private boxOfView(view: ViewNode): Box | undefined {
    if (view.node.kind === 'file') return this.layout.buildings.get(view.id)
    const plate = this.layout.plates.get(view.id)
    if (!plate) return undefined
    let top = plate.y + plate.h
    const walk = (v: ViewNode) => {
      const b = this.layout.buildings.get(v.id)
      if (b) top = Math.max(top, b.y + b.h)
      v.children.forEach(walk)
    }
    walk(view)
    return { ...plate, h: top - plate.y }
  }

  /** 그래프 노드 하나의 상자: 층 → 건물 → 판 순으로. */
  private boxOf(id: string): Box | undefined {
    const device = this.devices.get(id)
    if (device) return device.box
    const floor = this.layout.floors.get(id)
    if (floor) return floor
    const building = this.layout.buildings.get(id)
    if (building) return building
    const view = this.model.viewOf.get(id)
    return view && this.boxOfView(view)
  }

  private center(id: string): THREE.Vector3 | undefined {
    const b = this.boxOf(id)
    return b && new THREE.Vector3(b.x, b.y + b.h / 2, b.z)
  }

  /** 다른 쪽을 바라보는 층의 옆면 가운데. 호가 건물 속을 지나지 않게. */
  private portToward(id: string, other: THREE.Vector3): THREE.Vector3 | undefined {
    const b = this.boxOf(id)
    if (!b) return undefined
    const c = new THREE.Vector3(b.x, b.y + b.h / 2, b.z)
    const dir = new THREE.Vector3(other.x - c.x, 0, other.z - c.z)
    if (dir.lengthSq() < 1e-4) dir.set(1, 0, 0)
    dir.normalize()
    const tx = Math.abs(dir.x) > 1e-6 ? b.w / 2 / Math.abs(dir.x) : Infinity
    const tz = Math.abs(dir.z) > 1e-6 ? b.d / 2 / Math.abs(dir.z) : Infinity
    return c.addScaledVector(dir, Math.min(tx, tz))
  }

  private curveBetween(from: string, to: string): THREE.QuadraticBezierCurve3 | undefined {
    const key = `${from}→${to}`
    const cached = this.curves.get(key)
    if (cached) return cached
    const cFrom = this.center(from)
    const cTo = this.center(to)
    if (!cFrom || !cTo) return undefined
    const horizontal = Math.hypot(cFrom.x - cTo.x, cFrom.z - cTo.z)
    let a: THREE.Vector3, b: THREE.Vector3, ctrl: THREE.Vector3
    if (horizontal < 0.2) {
      // 같은 건물 안: 옆으로 불룩한 고리
      const box = this.boxOf(from)!
      const side = new THREE.Vector3(1, 0, 0.35).normalize()
      a = this.portToward(from, cFrom.clone().add(side))!
      b = this.portToward(to, cTo.clone().add(side))!
      ctrl = a.clone().add(b).multiplyScalar(0.5).addScaledVector(side, Math.max(box.w, box.d) * 0.6 + 0.5 + Math.abs(a.y - b.y) * 0.3)
    } else {
      a = this.portToward(from, cTo)!
      b = this.portToward(to, cFrom)!
      ctrl = a.clone().add(b).multiplyScalar(0.5)
      // API 흐름은 열이 옆으로 길어 호를 낮게(높이 솟으면 위가 어지럽다)
      ctrl.y = Math.max(a.y, b.y) + 0.5 + horizontal * (this.model.flow ? 0.2 : 0.32)
    }
    const curve = new THREE.QuadraticBezierCurve3(a, ctrl, b)
    this.curves.set(key, curve)
    return curve
  }

  // ------------------------------------------------------------------ 그리기

  /** 프론트 → 백엔드 HTTP 연결은 늘 흐리게 보여 준다(아키텍처 단계의 핵심 선). */
  private drawHttpLinks() {
    clearGroup(this.httpGroup)
    const seen = new Set<string>()
    for (const e of this.model.graph.edges) {
      if (e.kind !== 'http') continue
      const curve = this.curveFor(e)
      if (!curve || seen.has(e.from + e.to)) continue
      seen.add(e.from + e.to)
      const geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(48))
      const line = new THREE.Line(
        geo,
        new THREE.LineDashedMaterial({ color: COLORS.http, dashSize: 0.18, gapSize: 0.12, transparent: true, opacity: 0.5 })
      )
      line.computeLineDistances()
      this.httpGroup.add(line)
    }
  }

  private curveFor(e: GraphEdge) {
    return this.curveBetween(e.from, e.to)
  }

  private drawSelectionArcs() {
    this.dirty = true
    clearGroup(this.arcGroup)
    const id = this.selectedId
    if (!id || this.traceRoot) return
    const node = this.model.byId.get(id)
    if (!node) return
    // 함수면 그 함수, 클래스·파일이면 안에 든 함수 전부
    const members = new Set<string>()
    if (FUNCTION_KINDS.has(node.kind)) members.add(id)
    else
      for (const fid of this.floorIds) {
        const owner = this.layout.floorOwner.get(fid)!
        if (fid === id || owner.parent === id || this.model.byId.get(owner.parent ?? '')?.parent === id) members.add(fid)
      }
    const drawn = new Set<string>()
    // 폴더·파일에 들어가 바깥을 숨겼으면 숨긴 함수로 가는 호는 그리지 않는다
    const focusId = this.focusView.id
    const hiding = !this.model.flow && focusId !== this.model.root.id
    const shown = (id: string) => {
      if (!hiding) return true
      const i = this.floorIndex.get(id)
      return i !== undefined && this.floorAncestors[i].includes(focusId)
    }
    const add = (e: GraphEdge, color: string, radius: number) => {
      const key = `${e.from}|${e.to}`
      if (drawn.has(key) || drawn.size > 120 || !shown(e.from) || !shown(e.to)) return
      drawn.add(key)
      const curve = this.curveBetween(e.from, e.to)
      if (!curve) return
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 40, radius, 6, false), glow(color, 0.85))
      this.arcGroup.add(tube)
      const head = new THREE.Mesh(new THREE.ConeGeometry(radius * 3.2, radius * 9, 10), glow(color, 0.95))
      const end = curve.getPoint(1)
      head.position.copy(curve.getPoint(0.96))
      head.lookAt(end)
      head.rotateX(Math.PI / 2)
      this.arcGroup.add(head)
    }
    for (const m of members) {
      for (const e of this.model.out.get(m) ?? []) add(e, edgeColor(e.kind), 0.022 * this.k)
      for (const e of this.model.in.get(m) ?? []) if (!members.has(e.from)) add(e, COLORS.incoming, 0.018 * this.k)
    }
  }

  private placeOutline(box: THREE.LineSegments, b: Box | undefined, pad: number) {
    this.dirty = true
    if (!b) {
      box.visible = false
      return
    }
    box.visible = true
    box.position.set(b.x, b.y + b.h / 2, b.z)
    box.scale.set(b.w + pad, b.h + pad, b.d + pad)
  }

  /** 초점·선택·흐름 상태에 맞춰 판과 층 색을 다시 칠한다. */
  private applyColors() {
    this.dirty = true
    const dim = new THREE.Color(COLORS.dim)
    const tmp = new THREE.Color()
    const focusId = this.focusView.id
    const focused = (ancestors: string[]) => focusId === this.model.root.id || ancestors.includes(focusId)
    const tracing = !!this.traceRoot
    const overlay = this.overlay
    const paint = new THREE.Color()
    for (let i = 0; i < this.floorIds.length; i++) {
      const id = this.floorIds[i]
      tmp.copy(this.baseFloorColor[i])
      if (tracing) {
        if (!this.traceParticipants.has(id)) tmp.lerp(dim, 0.93)
      } else if (overlay) {
        if (overlay[id]) tmp.lerp(paint.set(overlay[id]), 0.7)
        else tmp.lerp(dim, 0.94)
      } else if (!focused(this.floorAncestors[i])) tmp.lerp(dim, 0.8)
      this.setFloorColor(i, tmp)
    }
    for (let i = 0; i < this.plateIds.length; i++) {
      tmp.copy(this.basePlateColor[i])
      if (!tracing && !focused(this.plateAncestors[i])) tmp.lerp(dim, 0.45)
      this.plateMesh.setColorAt(i, tmp)
    }
    this.touchFloors('color')
    if (this.plateMesh.instanceColor) this.plateMesh.instanceColor.needsUpdate = true
  }

  // ------------------------------------------------------------------ 라벨

  /** 초점 단위에 맞는 라벨 목록을 만든다. 위치는 매 프레임 투영한다. */
  private refreshLabels() {
    this.dirty = true
    const specs: LabelSpec[] = []
    const seen = new Set<string>()
    const push = (s: LabelSpec) => {
      if (seen.has(s.key) || specs.length >= MAX_LABELS) return
      seen.add(s.key)
      specs.push(s)
    }
    const plateLabel = (v: ViewNode, size: LabelSpec['size'], color?: string) => {
      const p = this.layout.plates.get(v.id)
      if (!p) return
      const tone = ancestorsAux(v) ? 'neutral' : v.node.layer === 'frontend' ? 'front' : v.node.layer === 'backend' ? 'back' : 'neutral'
      push({
        key: v.id,
        text: v.label,
        sub: size === 'lg' ? layerName(v.node.layer) : undefined,
        // 큰 구역 라벨은 판 앞 가장자리 아래(안쪽 모듈 라벨과 겹치지 않게), 나머지는 판 앞 왼쪽 모서리 위
        anchor:
          size === 'lg'
            ? new THREE.Vector3(p.x - p.w / 2 + 0.15, p.y, p.z + p.d / 2 + 0.15)
            : new THREE.Vector3(p.x - p.w / 2 + 0.1, p.y + p.h, p.z + p.d / 2),
        tone,
        size,
        color,
      })
    }
    const buildingLabel = (v: ViewNode) => {
      const b = this.layout.buildings.get(v.id)
      if (!b) return
      push({ key: v.id, text: v.label, anchor: new THREE.Vector3(b.x, b.y + b.h, b.z), tone: 'file', size: 'sm' })
    }
    /**
     * 함수 이름표. 짧게 쓴다:
     * - short: 메서드는 이름만(파일 단계 — 같은 클래스라 앞이 다 같다)
     * - center: 블록 아래 가운데, 둘째 줄에 클래스·파일(API 흐름)
     */
    const floorLabel = (id: string, tone: string, mode: 'full' | 'short' | 'center' = 'full') => {
      const f = this.layout.floors.get(id)
      const node = this.layout.floorOwner.get(id)
      if (!f || !node || node.kind === 'file') return
      const qual = node.id.split('::')[1] ?? node.name
      const owner = qual.includes('.') ? qual.split('.').slice(-2, -1)[0] : node.path.split('/').pop()
      const route = node.route ? `${node.route.method} ${node.route.path}` : undefined
      const color = this.model.style?.get(id)?.color
      if (mode === 'center')
        push({
          key: id,
          text: node.name,
          sub: route ?? owner,
          anchor: new THREE.Vector3(f.x, f.y, f.z + f.d / 2),
          tone,
          size: 'sm',
          center: true,
          color,
          mark: tone === 'select' ? 'pick' : undefined,
        })
      else
        push({
          key: id,
          text: mode === 'short' ? node.name : displayName(node),
          sub: route,
          anchor: new THREE.Vector3(f.x + f.w / 2, f.y + f.h / 2, f.z + f.d / 2),
          tone,
          size: 'sm',
          color,
          mark: tone === 'select' ? 'pick' : undefined,
        })
    }

    const childLabel = (v: ViewNode) => (v.node.kind === 'file' ? buildingLabel(v) : plateLabel(v, 'md'))

    const deviceLabel = (d: Device) => {
      const b = d.box
      const where = d.node.where === 'external' ? '외부' : d.node.where === 'container' ? '이 PC · 컨테이너' : '이 PC'
      push({
        key: d.id,
        text: d.node.name,
        sub: d.node.host ? `${where} · ${d.node.host}` : where,
        // 장비는 바로 아래 가운데. 받침대(서버가 여럿이면 나란히)도 앞면 가운데: 왼쪽 모서리는 구역 이름표 자리.
        // 겹치면 앞면 양 끝 → 앞으로 조금 나온 자리
        anchor: new THREE.Vector3(b.x, b.y, b.z + b.d / 2),
        alts: d.carries
          ? [new THREE.Vector3(b.x + b.w / 2, b.y, b.z + b.d / 2), new THREE.Vector3(b.x - b.w / 2, b.y, b.z + b.d / 2), new THREE.Vector3(b.x, b.y, b.z + b.d / 2 + b.h * 1.5)]
          : undefined,
        tone: 'neutral',
        size: 'md',
        mark: d.carries ? 'plinth' : 'device',
        center: true,
        color: DEVICE_COLORS[d.node.kind],
      })
    }
    const worldLabels = () => {
      const world = this.model.world
      if (!world) return
      for (const d of world.devices) deviceLabel(d)
      for (const z of world.zones)
        push({
          key: z.id,
          text: z.name,
          sub: z.sub,
          anchor: new THREE.Vector3(z.box.x - z.box.w / 2 + 0.3, z.box.y, z.box.z + z.box.d / 2 + 0.2),
          tone: 'neutral',
          size: 'lg',
          color: z.id === 'zone:external' ? '#a78bfa' : '#94a3b8',
          mark: 'zone',
        })
    }

    if (this.traceRoot) {
      floorLabel(this.traceRoot, 'select')
      for (const id of this.traceParticipants) {
        const d = this.devices.get(id)
        if (d) deviceLabel(d)
        else floorLabel(id, 'trace')
      }
    } else {
      if (this.selectedId) floorLabel(this.selectedId, 'select')
      const v = this.focusView
      if (v.node.kind === 'file') {
        for (const f of v.floors) floorLabel(f.id, 'floor', f.kind === 'method' ? 'short' : 'full')
      } else if (this.model.flow && v === this.model.root) {
        // API 흐름 보기: 열 이름과 모든 함수 이름
        for (const col of v.children) plateLabel(col, 'lg', this.model.plateTint?.get(col.id))
        worldLabels() // 장비 이름이 함수 이름보다 먼저(겹치면 뒤엣것이 숨는다)
        for (const col of v.children) for (const leaf of col.children) floorLabel(leaf.id, 'floor', 'center')
      } else if (v === this.model.root) {
        // 아키텍처 단계: 본체 구역(프론트·백엔드) → 그 안의 모듈 폴더 → 보조 폴더 순으로(겹치면 뒤엣것이 숨는다)
        const main = v.children.filter((d) => !d.aux)
        worldLabels() // 인프라 단계: 장비·구역 이름이 먼저(가장 중요한 이름표)
        for (const district of main) plateLabel(district, 'lg')
        for (const district of main)
          for (const child of district.children) if (child.node.kind !== 'file') plateLabel(child, 'md')
        for (const district of v.children.filter((d) => d.aux)) plateLabel(district, 'md')
      } else {
        for (const child of v.children) childLabel(child)
      }
    }
    this.labelSpecs = specs
    this.labelBoxes = []
    while (this.labelEls.length < specs.length) {
      const el = document.createElement('div')
      el.className = 'cv-label'
      el.innerHTML = '<span class="cv-label-text"></span><span class="cv-label-sub"></span>'
      this.labelLayer.appendChild(el)
      this.labelEls.push(el)
    }
    this.labelEls.forEach((el, i) => {
      const s = specs[i]
      if (!s) {
        el.style.display = 'none'
        return
      }
      el.style.display = ''
      el.dataset.tone = s.tone
      el.dataset.size = s.size
      if (s.mark === 'zone') el.dataset.el = '4.1'
      else if (s.mark === 'plinth') el.dataset.el = '4.2'
      else if (s.mark === 'device') el.dataset.el = '4.3'
      else if (s.mark === 'pick') el.dataset.el = '4.4'
      else delete el.dataset.el
      el.dataset.center = s.center ? '1' : ''
      if (s.color) el.style.setProperty('--cv-tone', s.color)
      else el.style.removeProperty('--cv-tone')
      const ellipsis = (t: string) => (t.length > LABEL_MAX ? t.slice(0, LABEL_MAX - 1) + '…' : t)
      ;(el.firstChild as HTMLElement).textContent = ellipsis(s.text)
      const sub = el.lastChild as HTMLElement
      sub.textContent = s.sub ? (s.sub.length > LABEL_MAX + 6 ? s.sub.slice(0, LABEL_MAX + 5) + '…' : s.sub) : ''
      sub.style.display = s.sub ? '' : 'none'
    })
  }

  /** 라벨을 화면 좌표로 옮기고, 앞선(중요한) 라벨과 겹치는 것은 숨긴다. */
  private updateLabelPositions() {
    const w = this.container.clientWidth
    const h = this.container.clientHeight
    const v = new THREE.Vector3()
    const placed: Array<[number, number, number, number]> = []
    // 양옆 패널에 가리지 않는 영역
    const minX = this.insets.left + 6
    const maxX = w - this.insets.right - 6
    this.labelSpecs.forEach((s, i) => {
      const el = this.labelEls[i]
      // 크기와 여백은 글자가 바뀔 때만 다시 잰다(refreshLabels가 비움)
      const boxOf = () => {
        let box = this.labelBoxes[i]
        if (!box) {
          const cs = getComputedStyle(el)
          box = this.labelBoxes[i] = s.center
            ? [-el.offsetWidth / 2, parseFloat(cs.marginTop), el.offsetWidth, el.offsetHeight]
            : [parseFloat(cs.marginLeft), parseFloat(cs.marginTop), el.offsetWidth, el.offsetHeight]
        }
        return box
      }
      /** 이 자리에 놓을 수 있으면 화면 좌표 */
      const at = (anchor: THREE.Vector3): [number, number] | null => {
        v.copy(anchor).project(this.camera)
        if (!(v.z < 1 && v.x > -1.1 && v.x < 1.1 && v.y > -1.1 && v.y < 1.1)) return null
        let x = (v.x * 0.5 + 0.5) * w
        const y = (-v.y * 0.5 + 0.5) * h
        const box = boxOf()
        // 패널 쪽으로 넘치면 안으로 밀어 넣는다(잘림 방지)
        const left = x + box[0]
        const right = left + box[2]
        if (right > maxX) x -= right - maxX
        else if (left < minX) x += minX - left
        const r: [number, number, number, number] = [x + box[0], y + box[1], x + box[0] + box[2], y + box[1] + box[3]]
        if (placed.some((p) => r[0] < p[2] + 3 && r[2] > p[0] - 3 && r[1] < p[3] + 2 && r[3] > p[1] - 2)) return null
        placed.push(r)
        return [x, y]
      }
      let spot = at(s.anchor)
      for (const alt of s.alts ?? []) if (!spot) spot = at(alt)
      el.style.opacity = spot ? '' : '0'
      if (spot) el.style.transform = `translate(${(spot[0] + (s.center ? centerShift(this.labelBoxes[i]) : 0)).toFixed(1)}px, ${spot[1].toFixed(1)}px)`
    })
    // 호출 순서 번호: 호 가운데부터 앞뒤로 옮겨 보며 이름표·다른 번호와 겹치지 않는 자리에
    const R = 10
    for (const b of this.badges) {
      let spot: [number, number] | null = null
      let first: [number, number] | null = null
      const free = (x: number, y: number) => !placed.some((p) => x + R > p[0] && x - R < p[2] && y + R > p[1] && y - R < p[3])
      const onCurve: Array<[number, number]> = []
      for (const t of [0.5, 0.38, 0.62, 0.28, 0.72, 0.2, 0.8]) {
        v.copy(b.curve.getPoint(t)).project(this.camera)
        if (!(v.z < 1 && v.x > -1 && v.x < 1 && v.y > -1 && v.y < 1)) continue
        onCurve.push([(v.x * 0.5 + 0.5) * w, (-v.y * 0.5 + 0.5) * h])
      }
      first = onCurve[0] ?? null
      spot = onCurve.find(([x, y]) => free(x, y)) ?? null
      // 짧은 호는 어디를 골라도 이름표 밑이다: 호 옆(위·좌우·아래)으로 비켜 놓는다
      if (!spot)
        for (const [x, y] of onCurve.slice(0, 3))
          for (const [dx, dy] of [[0, -20], [20, -8], [-20, -8], [0, 20], [26, 0], [-26, 0]]) {
            if (free(x + dx, y + dy)) {
              spot = [x + dx, y + dy]
              break
            }
          }
      spot ??= first
      b.el.style.visibility = spot ? '' : 'hidden'
      if (!spot) continue
      placed.push([spot[0] - R, spot[1] - R, spot[0] + R, spot[1] + R])
      b.el.style.transform = `translate(${spot[0].toFixed(1)}px, ${spot[1].toFixed(1)}px)`
    }
  }

  // ------------------------------------------------------------------ 카메라

  /** close: 건물 하나를 볼 때. 더 위에서 내려다봐 이웃 건물이 가리지 않게 한다. */
  private flyTo(box: Box, animate: boolean, margin: number, close = false) {
    const target = new THREE.Vector3(box.x, box.y + box.h * 0.35, box.z)
    const radius = 0.5 * Math.sqrt(box.w * box.w + box.d * box.d + box.h * box.h)
    const fov = THREE.MathUtils.degToRad(this.camera.fov)
    const visibleW = Math.max(1, this.container.clientWidth - this.insets.left - this.insets.right)
    const aspect = visibleW / Math.max(1, this.container.clientHeight)
    const fit = (radius / Math.tan(fov / 2)) * Math.max(1, 1 / aspect) * margin * 1.05
    const dist = Math.max(fit, close ? 4.5 : 2.2)
    // 지금 보는 방향을 유지하되 너무 눕거나 너무 위에서 보지 않게
    const dir = this.camera.position.clone().sub(this.controls.target)
    // 처음 보는 방향: 도시는 비스듬히 위에서, API 흐름은 열이 왼쪽→오른쪽으로 읽히게 정면 위에서
    if (dir.lengthSq() < 1e-6) dir.set(this.model.flow ? 0.18 : 0.55, this.model.flow ? 0.85 : 0.9, 1)
    const sph = new THREE.Spherical().setFromVector3(dir)
    // API 흐름은 더 위에서: 앞뒤 줄이 화면에서도 위아래로 떨어져 이름표가 덜 겹친다
    sph.phi = close
      ? THREE.MathUtils.clamp(sph.phi, 0.5, 0.78)
      : this.model.flow
        ? THREE.MathUtils.clamp(sph.phi, 0.62, 0.98)
        : THREE.MathUtils.clamp(sph.phi, 0.55, 1.05)
    sph.radius = dist
    this.desiredTarget.copy(target)
    this.desiredPos.copy(target).add(new THREE.Vector3().setFromSpherical(sph))
    if (!animate) {
      this.camera.position.copy(this.desiredPos)
      this.controls.target.copy(this.desiredTarget)
      this.controls.update()
      this.flying = false
    } else this.flying = true
  }

  private resize = () => {
    this.dirty = true
    const w = Math.max(1, this.container.clientWidth)
    const h = Math.max(1, this.container.clientHeight)
    this.renderer.setSize(w, h)
    this.camera.aspect = w / h
    this.camera.setViewOffset(w, h, (this.insets.right - this.insets.left) / 2, 0, w, h)
    this.camera.updateProjectionMatrix()
  }

  // ------------------------------------------------------------------ 입력

  private bindEvents() {
    const el = this.renderer.domElement
    const on = <K extends keyof HTMLElementEventMap>(type: K, fn: (e: HTMLElementEventMap[K]) => void) => {
      el.addEventListener(type, fn)
      this.cleanups.push(() => el.removeEventListener(type, fn))
    }
    // API 흐름: 블록 위에서 누르면 회전 대신 끌기(OrbitControls 보다 먼저 받으려고 capture 단계)
    const onDownCapture = (e: PointerEvent) => {
      if (!this.model.flow || e.button !== 0 || !this.cb.onDrop) return
      const r = el.getBoundingClientRect()
      this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
      const id = this.pick()
      if (!id || !this.layout.floors.has(id)) return
      this.drag = { id, column: null, active: false }
      this.controls.enabled = false
    }
    el.addEventListener('pointerdown', onDownCapture, { capture: true })
    this.cleanups.push(() => el.removeEventListener('pointerdown', onDownCapture, { capture: true }))
    on('pointermove', (e) => {
      const r = el.getBoundingClientRect()
      this.pointerClient = { x: e.clientX - r.left, y: e.clientY - r.top }
      this.pointer.set((this.pointerClient.x / r.width) * 2 - 1, -(this.pointerClient.y / r.height) * 2 + 1)
      this.pointerDirty = true
      if (this.drag && this.downAt && (this.drag.active || Math.hypot(e.clientX - this.downAt.x, e.clientY - this.downAt.y) > 5)) {
        this.drag.active = true
        const column = this.columnAt()
        if (column !== this.drag.column) {
          this.drag.column = column
          this.placeOutline(this.dropBox, column ? this.layout.plates.get(column) : undefined, 0.12)
          this.dirty = true
        }
        el.style.cursor = 'grabbing'
        this.cb.onDrag?.({ id: this.drag.id, column, x: this.pointerClient.x, y: this.pointerClient.y })
      }
    })
    on('pointerleave', () => {
      if (this.drag) {
        this.drag = null
        this.controls.enabled = true
        this.placeOutline(this.dropBox, undefined, 0)
        this.cb.onDrag?.(null)
      }
      this.hoverId = null
      this.hoverBox.visible = false
      this.cb.onHover(null, 0, 0)
    })
    on('pointerdown', (e) => {
      this.downAt = { x: e.clientX, y: e.clientY }
    })
    on('pointerup', (e) => {
      const drag = this.drag
      if (drag) {
        this.drag = null
        this.controls.enabled = true
        this.placeOutline(this.dropBox, undefined, 0)
        this.dirty = true
        if (drag.active) {
          this.downAt = null
          el.style.cursor = 'pointer'
          this.cb.onDrag?.(null)
          this.cb.onDrop?.(drag.id, drag.column)
          return
        }
      }
      if (!this.downAt || Math.hypot(e.clientX - this.downAt.x, e.clientY - this.downAt.y) > 5) return
      this.downAt = null
      const r = el.getBoundingClientRect()
      this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
      const hit = this.pick()
      if (hit) this.cb.onClick(hit)
    })
    this.controls.addEventListener('start', () => (this.flying = false))
    const observer = new ResizeObserver(this.resize)
    observer.observe(this.container)
    this.cleanups.push(() => observer.disconnect())
    this.resize()
  }

  /** 포인터 아래 열 판(API 흐름의 col:*). 블록에 가려도 판만 본다 */
  private columnAt(): string | null {
    this.raycaster.setFromCamera(this.pointer, this.camera)
    for (const h of this.raycaster.intersectObject(this.plateMesh, false)) {
      const id = h.instanceId === undefined ? undefined : this.plateIds[h.instanceId]
      if (id?.startsWith('col:')) return id
    }
    return null
  }

  private pick(): string | null {
    this.raycaster.setFromCamera(this.pointer, this.camera)
    const hits = this.raycaster.intersectObjects([...this.floorMeshes, this.plateMesh, ...this.deviceMeshes], false)
    for (const h of hits) {
      if (h.object.userData.deviceId) return h.object.userData.deviceId as string
      if (h.instanceId === undefined) continue
      const floors = this.meshFloors.get(h.object as THREE.InstancedMesh)
      if (floors) return this.floorIds[floors[h.instanceId]]
      if (h.object === this.plateMesh) return this.plateIds[h.instanceId]
    }
    return null
  }

  // ------------------------------------------------------------------ 흐름 재생

  private enterEvent(index: number) {
    const e = this.trace[index]
    this.traceT = 0
    this.pulse.visible = false
    if (e.type === 'skipped') this.markTraversed(e) // 안 탄 호출은 점선만 긋고 지나간다
    const active = e.type === 'call' ? e.to : e.type === 'return' ? e.to : e.from
    this.placeOutline(this.activeBox, this.boxOf(active), 0.08)
    ;(this.activeBox.material as THREE.LineBasicMaterial).color.set(
      e.type === 'return' ? (e.failed ? COLORS.raise : COLORS.ret) : e.type === 'raise' ? COLORS.raise : COLORS.call
    )
    // 도시 보기: 장비로 가는 호출·브라우저↔서버 HTTP 에서는 카메라를 인프라 크기로 빼고, 코드로 돌아오면 다시 들어간다
    if (this.model.world && !this.model.flow && !this.follow && (e.type === 'call' || e.type === 'return')) {
      const far = this.devices.has(e.from) || this.devices.has(e.to) || (e.type === 'call' && e.step.edge === 'http')
      if (far !== this.farView) {
        this.farView = far
        const box = far ? unionBox([this.boxOf(e.from), this.boxOf(e.to)].filter((b): b is Box => !!b)) : this.codeBox
        if (box) this.flyTo(box, true, far ? 1.35 : 1.3)
      }
    }
    if (this.follow) {
      const c = this.center(active)
      if (c) {
        const offset = this.camera.position.clone().sub(this.controls.target)
        this.desiredTarget.copy(c)
        this.desiredPos.copy(c).add(offset)
        this.flying = true
      }
    }
  }

  private markTraversed(e: TraceEvent) {
    if (e.type === 'skipped') {
      const key = `skip:${e.from}→${e.to}`
      if (e.from === e.to || this.traversed.has(key)) return // 던지지 않은 raise 는 선을 긋지 않는다
      this.traversed.add(key)
      const curve = this.curveBetween(e.from, e.to)
      if (!curve) return
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(curve.getPoints(40)),
        new THREE.LineDashedMaterial({ color: COLORS.external, dashSize: 0.12 * this.k, gapSize: 0.1 * this.k, transparent: true, opacity: 0.7 })
      )
      line.computeLineDistances()
      this.traceGroup.add(line)
      this.dirty = true
      return
    }
    if (e.type !== 'call' && e.type !== 'return') return
    const key = e.type === 'call' ? `${e.from}→${e.to}` : `${e.to}→${e.from}`
    if (this.traversed.has(key)) return
    this.traversed.add(key)
    const [from, to] = e.type === 'call' ? [e.from, e.to] : [e.to, e.from]
    const curve = this.curveBetween(from, to)
    if (!curve) return
    // 실행 기록 재생이면 그 갈래의 색으로(같은 API라도 간 길이 다르면 색이 다르다)
    const color = this.traceColor ?? (e.type === 'call' && e.step.edge === 'http' ? COLORS.http : COLORS.call)
    this.traceGroup.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 40, (this.traceColor ? 0.026 : 0.018) * this.k, 6, false), glow(color, this.traceColor ? 0.9 : 0.6)))
  }

  private stepTrace(dt: number) {
    if (!this.trace.length) return
    if (this.playing && (this.traceIdx < 0 || this.traceT >= 1)) {
      if (this.traceIdx >= this.trace.length - 1) {
        this.playing = false
        this.dirty = true
        this.cb.onTraceEnd()
      } else {
        if (this.traceIdx >= 0) this.markTraversed(this.trace[this.traceIdx])
        this.traceIdx++
        this.enterEvent(this.traceIdx)
        this.cb.onTraceStep(this.traceIdx)
      }
    }
    if (this.traceIdx < 0) return
    const e = this.trace[this.traceIdx]
    if (this.playing) this.traceT = Math.min(1, this.traceT + (dt * this.speed) / EVENT_SECONDS[e.type])
    const t = this.playing ? this.traceT : Math.max(this.traceT, 1)
    this.packet.visible = false
    this.trail.forEach((d) => (d.visible = false))
    if (e.type === 'call' || e.type === 'return') {
      const curve = e.type === 'call' ? this.curveBetween(e.from, e.to) : this.curveBetween(e.to, e.from)
      if (!curve) return
      const color =
        e.type === 'return' ? (e.failed ? COLORS.raise : COLORS.ret) : e.step.edge === 'http' ? COLORS.http : COLORS.call
      const eased = easeInOut(t)
      // 돌아올 때는 같은 호를 거꾸로
      const at = (u: number) => curve.getPoint(e.type === 'call' ? u : 1 - u)
      this.packet.visible = true
      this.packet.position.copy(at(eased))
      ;(this.packet.material as THREE.MeshBasicMaterial).color.set(color)
      this.trail.forEach((dot, k) => {
        const u = eased - (k + 1) * 0.035
        if (u <= 0) return
        dot.visible = true
        dot.position.copy(at(u))
        ;(dot.material as THREE.MeshBasicMaterial).color.set(color)
      })
    } else if (e.type !== 'skipped') {
      const c = this.center(e.from)
      if (!c) return
      const b = this.boxOf(e.from)!
      this.pulse.visible = true
      this.pulse.position.set(c.x, b.y + b.h + 0.02, c.z)
      const s = (0.6 + t * (Math.max(b.w, b.d) * 0.9)) * Math.sqrt(this.k)
      this.pulse.scale.setScalar(s)
      const mat = this.pulse.material as THREE.MeshBasicMaterial
      mat.color.set(e.type === 'raise' ? COLORS.raise : e.type === 'cycle' ? COLORS.call : COLORS.external)
      mat.opacity = 0.9 * (1 - t)
    }
  }

  // ------------------------------------------------------------------ 반복

  private loop = (now: number) => {
    this.raf = requestAnimationFrame(this.loop)
    const dt = Math.min(0.05, (now - this.last) / 1000)
    this.last = now
    if (this.flying) {
      const k = 1 - Math.exp(-dt * 4.5)
      this.camera.position.lerp(this.desiredPos, k)
      this.controls.target.lerp(this.desiredTarget, k)
      if (this.camera.position.distanceTo(this.desiredPos) < 0.01) this.flying = false
    }
    const moved = this.controls.update() // 끌기·감속 회전 중이면 true
    if (this.pointerDirty) {
      this.pointerDirty = false
      const id = this.pick()
      if (id !== this.hoverId) {
        this.hoverId = id
        this.placeOutline(this.hoverBox, id ? this.boxOf(id) : undefined, 0.03)
        this.renderer.domElement.style.cursor = id ? 'pointer' : 'grab'
      }
      this.cb.onHover(id, this.pointerClient.x, this.pointerClient.y)
    }
    this.stepTrace(dt)
    // 아무것도 움직이지 않으면 그리지 않는다: 띄워 둬도 GPU를 쓰지 않게
    if (!this.dirty && !moved && !this.flying && !this.playing) return
    this.dirty = false
    this.renderer.render(this.scene, this.camera)
    this.updateLabelPositions()
  }
}

// ------------------------------------------------------------------ 도우미

/** 보조 폴더(tests, scripts …) 안에 있는지. */
function ancestorsAux(view: ViewNode): boolean {
  for (let v: ViewNode | null = view; v; v = v.parent) if (v.aux) return true
  return false
}

/** 가운데 맞춘 이름표는 왼쪽 끝을 너비의 절반만큼 당겨 그린다. */
function centerShift(box: [number, number, number, number] | undefined) {
  return box ? box[0] : 0
}

function ancestorsOf(view: ViewNode): string[] {
  const ids: string[] = []
  for (let v: ViewNode | null = view; v; v = v.parent) ids.push(v.id)
  return ids
}

function glow(color: string, opacity = 1) {
  return new THREE.MeshBasicMaterial({ color, transparent: opacity < 1, opacity, toneMapped: false, depthWrite: opacity >= 1 })
}

function outlineBox(color: string, opacity: number) {
  const geo = new THREE.EdgesGeometry(new THREE.BoxGeometry(1, 1, 1))
  const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity, toneMapped: false, depthTest: false })
  const lines = new THREE.LineSegments(geo, mat)
  lines.renderOrder = 10
  lines.visible = false
  return lines
}

function clearGroup(group: THREE.Group) {
  for (const child of [...group.children]) {
    group.remove(child)
    const mesh = child as THREE.Mesh
    mesh.geometry?.dispose()
    const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
    mats.forEach((m) => m.dispose())
  }
}

function edgeColor(kind: GraphEdge['kind']) {
  if (kind === 'http') return COLORS.http
  if (kind === 'depends') return COLORS.depends
  if (kind === 'renders') return COLORS.renders
  return COLORS.call
}

function layerName(layer: string | undefined) {
  return layer === 'frontend' ? 'FRONTEND' : layer === 'backend' ? 'BACKEND' : undefined
}

function easeInOut(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
}


/** 장비 종류 색(앞면 불빛·이름표 띠) */
const DEVICE_COLORS: Record<string, string> = {
  browser: '#38bdf8',
  backend: '#ff7a1a',
  db: '#60a5fa',
  cache: '#f87171',
  storage: '#fbbf24',
  queue: '#fb923c',
  search: '#facc15',
  api: '#a78bfa',
}
/** 연결선 색: 프로토콜마다 */
const LINK_COLORS: Record<string, string> = {
  HTTP: '#ffb347',
  SQL: '#60a5fa',
  Mongo: '#60a5fa',
  Bolt: '#60a5fa',
  Redis: '#f87171',
  S3: '#fbbf24',
  HTTPS: '#a78bfa',
  AMQP: '#fb923c',
  Kafka: '#fb923c',
}

/**
 * 장비 한 대의 3D 모양(하드웨어처럼): 받침대는 서버 랙 앞면 불빛 줄, DB는 디스크 세 장, 캐시는 낮은 원통,
 * 저장소는 서랍 달린 상자, 큐는 눕힌 원통, 외부 API는 구름. userData.pick 인 메시만 누를 수 있다.
 */
function deviceModel(d: Device): THREE.Group {
  const g = new THREE.Group()
  const b = d.box
  const accent = DEVICE_COLORS[d.node.kind] ?? '#9aa4b2'
  const metal = (color: string, m = 0.5) => new THREE.MeshStandardMaterial({ color, metalness: m, roughness: 0.42 })
  const add = (geo: THREE.BufferGeometry, mat: THREE.Material, x: number, y: number, z: number, pick = true) => {
    const mesh = new THREE.Mesh(geo, mat)
    mesh.position.set(x, y, z)
    mesh.castShadow = pick
    mesh.receiveShadow = true
    mesh.userData.pick = pick
    g.add(mesh)
    return mesh
  }
  const kind = d.node.kind
  if (d.carries) {
    add(new THREE.BoxGeometry(b.w, b.h, b.d), metal(kind === 'browser' ? '#1a2532' : '#232a33', 0.6), b.x, b.y + b.h / 2, b.z)
    // 앞면: 랙처럼 불빛 줄 + 오른쪽 끝 표시등
    const rows = Math.max(2, Math.min(4, Math.round(b.h / 0.5)))
    for (let i = 0; i < rows; i++) {
      const y = b.y + b.h * (0.22 + (0.56 * i) / Math.max(1, rows - 1))
      add(new THREE.BoxGeometry(b.w * 0.86, 0.05, 0.04), glow(accent, 0.8), b.x - b.w * 0.04, y, b.z + b.d / 2 + 0.02, false)
      add(new THREE.SphereGeometry(0.09, 10, 8), glow(i % 2 ? '#4ade80' : accent, 1), b.x + b.w / 2 - 0.35, y, b.z + b.d / 2 + 0.05, false)
    }
    return g
  }
  if (kind === 'db' || kind === 'search') {
    const r = Math.min(b.w, b.d) / 2
    const gap = b.h * 0.05
    const hh = (b.h - gap * 2) / 3
    for (let i = 0; i < 3; i++) {
      const y0 = b.y + i * (hh + gap)
      add(new THREE.CylinderGeometry(r, r, hh, 40), metal('#2a3442', 0.6), b.x, y0 + hh / 2, b.z)
      add(new THREE.TorusGeometry(r * 1.005, 0.035, 8, 56), glow(accent, 0.9), b.x, y0 + hh, b.z, false).rotation.x = Math.PI / 2
    }
  } else if (kind === 'cache') {
    const r = Math.min(b.w, b.d) / 2
    add(new THREE.CylinderGeometry(r * 0.94, r, b.h, 40), metal('#3a2427', 0.5), b.x, b.y + b.h / 2, b.z)
    add(new THREE.TorusGeometry(r * 0.95, 0.04, 8, 56), glow(accent, 0.95), b.x, b.y + b.h, b.z, false).rotation.x = Math.PI / 2
  } else if (kind === 'storage') {
    add(new THREE.BoxGeometry(b.w, b.h, b.d), metal('#2c2f36', 0.55), b.x, b.y + b.h / 2, b.z)
    for (let i = 0; i < 3; i++)
      add(new THREE.BoxGeometry(b.w * 0.8, 0.05, 0.04), glow(accent, 0.85), b.x, b.y + b.h * (0.25 + 0.25 * i), b.z + b.d / 2 + 0.02, false)
  } else if (kind === 'queue') {
    const r = Math.min(b.h, b.d) / 2
    add(new THREE.CylinderGeometry(r, r, b.w - r * 2, 32), metal('#33291f', 0.5), b.x, b.y + r, b.z).rotation.z = Math.PI / 2
    for (const sx of [-1, 1]) add(new THREE.SphereGeometry(r, 24, 16), metal('#33291f', 0.5), b.x + sx * (b.w / 2 - r), b.y + r, b.z)
    add(new THREE.TorusGeometry(r * 1.01, 0.03, 8, 40), glow(accent, 0.9), b.x, b.y + r, b.z, false).rotation.y = Math.PI / 2
  } else {
    // 외부 API: 구름(공 네 개) + 바닥 빛 고리
    const r = Math.min(b.w, b.d) * 0.3
    const cloud = metal('#c9d2df', 0.15)
    for (const [dx, dy, s] of [[0, 0.55, 1], [-0.85, 0.35, 0.78], [0.85, 0.38, 0.8], [0.1, 1.1, 0.72]] as const)
      add(new THREE.SphereGeometry(r * s, 28, 18), cloud, b.x + dx * r, b.y + dy * r * 1.6 + r * 0.4, b.z)
    add(new THREE.TorusGeometry(r * 1.6, 0.04, 8, 56), glow(accent, 0.9), b.x, b.y + 0.06, b.z, false).rotation.x = Math.PI / 2
  }
  return g
}

/** 블록 옆면에 층 줄(세계 좌표 높이 0.3마다 옅은 어두운 띠). 인스턴스마다 높이가 달라도 줄 간격은 같다 */
function floorLines(shader: THREE.WebGLProgramParametersWithUniforms) {
  shader.vertexShader = shader.vertexShader
    .replace('#include <common>', '#include <common>\nvarying float vWorldY;\nvarying float vSide;')
    .replace(
      '#include <project_vertex>',
      `#include <project_vertex>
      vec4 lineWorld = vec4(transformed, 1.0);
      #ifdef USE_INSTANCING
        lineWorld = instanceMatrix * lineWorld;
      #endif
      vWorldY = (modelMatrix * lineWorld).y;
      vSide = 1.0 - abs(normalize(objectNormal).y);`
    )
  shader.fragmentShader = shader.fragmentShader
    .replace('#include <common>', '#include <common>\nvarying float vWorldY;\nvarying float vSide;')
    .replace(
      '#include <color_fragment>',
      `#include <color_fragment>
      float floorF = fract(vWorldY / 0.3);
      float floorLine = 1.0 - smoothstep(0.05, 0.12, floorF);
      diffuseColor.rgb *= 1.0 - 0.32 * floorLine * step(0.5, vSide);`
    )
}
