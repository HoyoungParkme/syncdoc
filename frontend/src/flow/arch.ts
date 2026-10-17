// 프로젝트마다 다른 설계 패턴을 따르는 레이어 지도: 함수가 어느 레이어(API 흐름의 열)에 속하는지,
// 레이어끼리 어느 방향 호출이 정상인지.
//  1) 자동: 클래스·파일·폴더 이름의 구조 낱말(routers, services, crud, adapters …)과 업무 폴더(domains/<업무>)로 나누고,
//     같은 층 안 순서와 프로젝트 고유 레이어(agents, core …)의 층은 실제 호출 방향으로 정한다.
//  2) 설정: 프로젝트 루트의 view_arc.json(layers·assign·allow) 또는 import-linter layers 계약이 있으면 그것을 따른다.
//  싱크독(UI-19, 카드 CG): 설정 대신 클래스 명세 「폴더 구조」의 층 표(specSource) — 표에 맞는 함수는 그 층, 나머지는 1)로.

import type { GraphNode } from './types'
import { type Model, type Shape, FUNCTION_KINDS } from './model'

export type Concept =
  | 'endpoint' | 'flow' | 'service' | 'logic' | 'store' | 'infra' | 'deps' | 'schema' | 'other' | 'custom'
  // 프론트
  | 'page' | 'component' | 'hook' | 'state' | 'client' | 'util' | 'front-other'

export type ArchLayer = {
  id: string
  name: string
  concept: Concept
  tier: number | null // 위반 판정 층(작을수록 위). null: 판정하지 않음(의존성·스키마·기타)
  color: string
  shape: Shape
  shapeName: string
  count: number // 함수 수(테스트 제외)
  side: 'front' | 'back'
}

/** 금지 규칙(dependency-cruiser forbidden 과 같은 꼴). path 는 정규식, base 는 그 설정이 있던 폴더(경로를 거기 기준으로 맞춘다) */
export type ForbiddenRule = { name: string; from: { path?: string; pathNot?: string }; to: { path?: string; pathNot?: string }; base?: string }

/** 프로젝트 루트 view_arc.json 의 모양. 레이어는 이름으로 가리킨다. */
export type ArchConfig = {
  layers?: Array<{ name: string; match: string[]; concept?: Concept }> // 있으면 자동 추정 대신 이것만(위 → 아래)
  assign?: Record<string, string> // 경로 glob 또는 "경로::함수" → 레이어 이름. 자동 추정·layers 위에 덮어쓴다
  allow?: Record<string, string[]> // 레이어 → 부를 수 있는 레이어. 적힌 레이어만 검사
  strict?: boolean // 엔드포인트가 저장소·외부를 바로 부르면: true 항상 위반, false 위반 아님, 없으면 프로젝트 관례로
  forbidden?: ForbiddenRule[] // 이 경로에서 저 경로로 부르면 위반(dependency-cruiser JSON 도 여기로 읽힌다)
}

export type ArchSource = {
  kind: 'view_arc' | 'import-linter' | 'dependency-cruiser' | 'auto' | 'spec'
  path: string
  config: ArchConfig
  notes?: string[] // 읽지 못한 설정 등 알려 줄 것
}

export type ArchMap = {
  pattern: string // 감지한 설계 패턴(사람이 읽는 말)
  source: ArchSource | null
  layers: ArchLayer[] // 위 → 아래(열 순서)
  byId: Map<string, ArchLayer>
  layerOf: Map<string, string> // 함수 id → 레이어 id
  reason: Map<string, string> // 함수 id → 그 레이어로 본 근거
  allow: Map<string, Set<string>> | null // 설정의 명시 규칙(레이어 id 기준)
  // "건너뜀" 판정: 엔드포인트가 서비스층(via)과 저장소·외부층(direct)을 부른 횟수. strict면 직접 부르기를 위반으로 본다
  convention: { via: number; direct: number; strict: boolean; fixed: boolean }
  ctor: Set<string> // 생성자·클래스: 위 레이어의 값 객체를 만드는 건 위반이 아니다
  file: Map<string, string> // 함수 id → 파일 경로: 같은 파일 안 호출은 위반으로 보지 않는다
  coverage: { classified: number; total: number }
  front: ArchLayer[] // 프론트 레이어(왼쪽 → 오른쪽: 화면 → 컴포넌트 → 훅·상태 → API 호출)
  frontConvention: { via: number; direct: number; strict: boolean }
  frontCoverage: { classified: number; total: number }
  forbidden: Array<{ name: string; test: (from: string, to: string) => boolean }>
}

export const CONCEPTS: Record<Exclude<Concept, 'custom'>, { name: string; tier: number | null; color: string; shape: Shape; shapeName: string }> = {
  endpoint: { name: '엔드포인트', tier: 0, color: '#ff7a1a', shape: 'hex', shapeName: '육각기둥' },
  deps: { name: '의존성 · 설정', tier: null, color: '#facc15', shape: 'sphere', shapeName: '구' },
  flow: { name: '조율 · 유스케이스', tier: 1, color: '#c084fc', shape: 'oct', shapeName: '팔각기둥' },
  service: { name: '서비스', tier: 1, color: '#4ade80', shape: 'rounded', shapeName: '둥근 상자' },
  logic: { name: '도메인 로직', tier: 1, color: '#a3e635', shape: 'oct', shapeName: '팔각기둥' },
  store: { name: '저장소 · DB', tier: 2, color: '#60a5fa', shape: 'cylinder', shapeName: '원통' },
  infra: { name: '외부 연동', tier: 2, color: '#f472b6', shape: 'cone', shapeName: '원뿔' },
  schema: { name: '스키마 · 모델', tier: null, color: '#94a3b8', shape: 'box', shapeName: '납작한 판' },
  other: { name: '기타', tier: null, color: '#d6d3d1', shape: 'box', shapeName: '상자' },
  page: { name: '화면 · 페이지', tier: 0, color: '#62b6c8', shape: 'box', shapeName: '상자' },
  component: { name: '컴포넌트', tier: 1, color: '#7dd3fc', shape: 'box', shapeName: '상자' },
  hook: { name: '훅', tier: 2, color: '#a99be0', shape: 'sphere', shapeName: '구' },
  state: { name: '상태 · 스토어', tier: 2, color: '#f0abfc', shape: 'cylinder', shapeName: '원통' },
  client: { name: 'API 호출', tier: 3, color: '#38bdf8', shape: 'rounded', shapeName: '둥근 상자' },
  util: { name: '프론트 공용', tier: null, color: '#9fb6c8', shape: 'box', shapeName: '상자' },
  'front-other': { name: '프론트 기타', tier: null, color: '#9fb6c8', shape: 'box', shapeName: '상자' },
}
const FRONT_ORDER: Concept[] = ['page', 'component', 'hook', 'state', 'client', 'util', 'front-other']
const FRONT_WORDS: Array<[Concept, RegExp]> = [
  ['page', /^(pages?|routes?|views?|screens?)$/],
  ['component', /^(components?|ui|widgets?|layouts?)$/],
  ['hook', /^hooks?$/],
  ['state', /^(stores?|state|slices?|contexts?|atoms?|reducers?|redux|zustand)$/],
  ['client', /^(api|apis|services?|clients?|http|fetchers?|requests?|queries)$/],
  ['util', /^(utils?|lib|libs|helpers?|shared|common)$/],
]
/** Next.js app 라우터의 화면 파일 */
const PAGE_FILE = /(^|\/)app\/(.*\/)?(page|layout|template)\.[jt]sx?$/
const FRONT_OUTSIDE = /(^|\/)(__tests__|tests?|__mocks__|stories|e2e)\/|\.(test|spec|stories)\.[jt]sx?$/
const CONCEPT_ORDER: Concept[] = ['endpoint', 'deps', 'flow', 'service', 'logic', 'custom', 'store', 'infra', 'schema', 'other']
const CUSTOM_COLORS = ['#2dd4bf', '#fb923c', '#e879f9', '#fde047', '#93c5fd', '#fca5a5']

/**
 * 역할을 가리키는 낱말. 이름을 낱말로 쪼개 통째로 맞춘다(reports 안의 port 같은 오인 방지).
 * 구조 낱말이 먼저고, 기술 낱말(git, llm …)은 구조 낱말이 하나도 없을 때만 — routers/git.py 는 라우터 쪽.
 */
const WORDS: Array<[Concept, RegExp]> = [
  ['endpoint', /^(routers?|routes?|endpoints?|controllers?|views?|urls)$/],
  ['flow', /^(pipelines?|use_?cases?|workflows?|orchestrat(or|ors|ion)|interactors?|flows?)$/],
  ['service', /^(services?|application)$/],
  ['store', /^(repositor(y|ies)|repos?|daos?|crud|stores?|db|database|orm|persistence)$/],
  ['infra', /^(infra|infrastructure|adapters?|clients?|gateways?|external|integrations?|ports?|connectors?)$/],
  ['deps', /^(deps|dependenc(y|ies)|registry|container|wiring|providers?|di|settings|config(uration)?)$/],
  ['schema', /^(schemas?|models?|entit(y|ies)|dtos?|serializers?|mappers?|converters?|responses?|requests?|types)$/],
]
const TOPIC: Array<[Concept, RegExp]> = [['infra', /^(llm|http|storage|queues?|cache|mail(er)?|github|git|s3|redis)$/]]
/** 프로젝트마다 위아래가 다른 낱말: 그 이름의 고유 레이어로 두고 층은 호출 방향으로(syncdoc의 queries 는 서비스 위) */
const AMBIGUOUS = /^(quer(y|ies)|handlers?|managers?|tools?|commands?|jobs?|tasks?|workers?)$/
/** 어디서나 불리는 공용 코드: 고유 레이어로 두되 위반 판정은 하지 않는다 */
const SHARED = /^(utils?|helpers?|common|shared|lib|errors?|exceptions?)$/
/** 앱 밖 코드(테스트 데이터·평가·예제·마이그레이션): 분류하지 않는다 */
const NON_APP = /(^|\/)(fixtures|snapshots?|examples?|evals?|benchmarks?|notebooks?|research|sandbox|vendor|third_party|alembic|migrations)\/|^(data|docs?|local)\//

/** 설정·DB 세션을 꺼내거나 객체를 만들어 주는 배선(get_settings, session_scope, get_ocr_adapter) — 계층 호출이 아니다 */
const WIRING =
  /^(get_|provide_)?(db|session|engine|connection|uow|unit_of_work|settings|config)$|_(scope|factory)$|^(get|make|build|provide)_(\w+_)?(adapter|store|client|repo|repository|service|gateway|port|storage)$/

/** 경로의 뼈대일 뿐인 폴더(그 이름으로 레이어를 만들지 않는다) */
const CONTAINER = /^(backend|server|src|app|apps|lib|libs|packages|python|source|api|core)$/
const TEST = /(^|\/)(tests?|testing|__tests__|scripts?)\/|(^|\/)(test_[^/]*|[^/]*_test|conftest)\.py$/

/** 'UserRepository' → ['user', 'repository'], 'user_service.py' → ['user', 'service'] */
export const words = (s: string) =>
  s
    .replace(/\.[a-z]+$/i, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean)

/** 낱말 묶음의 개념: 뒤 낱말(중심어)부터 본다 — storage_service 는 서비스, service_client 는 외부. */
function conceptOf(ws: string[], table: Array<[Concept, RegExp]>): Concept | undefined {
  for (let i = ws.length - 1; i >= 0; i--) for (const [c, re] of table) if (re.test(ws[i])) return c
}
const isStructural = (name: string) => !!conceptOf(words(name), WORDS)

/** glob → 정규식. ** 여러 폴더, * 폴더 이름 안, ? 한 글자 */
export function globToRegExp(glob: string): RegExp {
  let re = ''
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i]
    if (glob.startsWith('**/', i)) {
      re += '(?:.*/)?'
      i += 2
    } else if (glob.startsWith('/**', i) && i + 3 === glob.length) {
      re += '(?:/.*)?'
      i += 2
    } else if (glob.startsWith('**', i)) {
      re += '.*'
      i += 1
    } else if (c === '*') re += '[^/]*'
    else if (c === '?') re += '[^/]'
    else re += c.replace(/[.+^${}()|[\]\\]/g, '\\$&')
  }
  return new RegExp(`^${re}$`)
}

const qualOf = (n: GraphNode) => n.id.split('::')[1] ?? n.name
const fnKey = (n: GraphNode) => `${n.path}::${qualOf(n)}`

/** 레이어 이름 → 개념(설정에서 "저장소 · DB"나 "store"라고 쓰면 그 개념으로) */
function conceptByName(name: string): Exclude<Concept, 'custom'> | undefined {
  const key = name.trim().toLowerCase()
  for (const [c, meta] of Object.entries(CONCEPTS)) if (c === key || meta.name === name.trim()) return c as Exclude<Concept, 'custom'>
}

type Pick = { key: string; reason: string; shared?: boolean }

export function inferArch(model: Model, source: ArchSource | null = null): ArchMap {
  const config = source?.config ?? {}
  const backend = (n: GraphNode) => n.layer !== 'frontend'
  const fns = model.graph.nodes.filter((n) => FUNCTION_KINDS.has(n.kind) && backend(n))
  const files = model.graph.nodes.filter((n) => n.kind === 'file' && backend(n) && !TEST.test(n.path) && !NON_APP.test(n.path))

  // 폴더 구조: 폴더 → 바로 안 파일 이름들, 하위 폴더 이름들
  const stems = new Map<string, string[]>()
  const subdirs = new Map<string, Set<string>>()
  for (const f of files) {
    const parts = f.path.split('/')
    const dir = parts.slice(0, -1).join('/')
    if (!stems.has(dir)) stems.set(dir, [])
    stems.get(dir)!.push(parts[parts.length - 1])
    for (let i = 1; i < parts.length; i++) {
      const parent = parts.slice(0, i - 1).join('/')
      if (!subdirs.has(parent)) subdirs.set(parent, new Set())
      subdirs.get(parent)!.add(parts[i - 1])
    }
  }
  const join = (a: string, b: string) => (a ? `${a}/${b}` : b)
  // 바로 안에 router·service·crud 같은 파일이 있는 폴더
  const hasStructure = (dir: string) => (stems.get(dir) ?? []).some(isStructural)
  // 업무 폴더: 하위 폴더 둘 이상이 저마다 그런 파일을 갖고, 하위 폴더 이름 대부분이 구조 낱말이 아니면(domains/<업무>, core/<업무>).
  // 이름이 구조 낱말인 업무(domains/registry)도 업무로 본다. 계층형(app/routers, app/services)은 이름이 구조 낱말이라 제외된다
  const business = new Set<string>()
  const featureRoots = new Set<string>()
  for (const [dir, subs] of subdirs) {
    if (dir.split('/').some(isStructural)) continue // infrastructure/llm 같은 구조 폴더 안은 업무가 아니다
    const kids = [...subs].filter((s) => !CONTAINER.test(s))
    const feats = kids.filter((s) => hasStructure(join(dir, s)))
    if (feats.length >= 2 && kids.filter(isStructural).length * 2 < kids.length) {
      featureRoots.add(dir)
      for (const s of feats) business.add(join(dir, s))
    }
  }

  // 설정
  const cfgLayers = (config.layers ?? []).map((l) => ({ ...l, res: l.match.map(globToRegExp) }))
  const assigns = Object.entries(config.assign ?? {})
    .map(([key, name]) => ({ key, name, re: key.includes('::') ? null : globToRegExp(key) }))
    // 더 구체적인(긴) 규칙이 먼저 — 명세 층 표는 위 줄이 이긴다(SYNC-STD-001 2.6)
    .sort((a, b) => (source?.kind === 'spec' ? 0 : b.key.length - a.key.length))
  // 레이어 이름 → id: 아는 개념이면 그 개념, 아니면 고유 레이어(자동으로 찾은 agents 와 설정의 agents 는 같은 열)
  const namedKey = (name: string): string => conceptByName(name) ?? `custom:${name.trim()}`

  const depended = new Set(model.graph.edges.filter((e) => e.kind === 'depends').map((e) => e.to))
  const outside = (path: string) => TEST.test(path) || NON_APP.test(path)

  const classify = (n: GraphNode): Pick => {
    const key = fnKey(n)
    for (const a of assigns)
      if (a.re ? a.re.test(n.path) : a.key === key)
        return { key: namedKey(a.name), reason: `${source?.kind === 'spec' ? '명세 층 표' : '설정 assign'}: ${a.key}` }
    if (cfgLayers.length) {
      for (const l of cfgLayers) if (l.res.some((re) => re.test(n.path))) return { key: namedKey(l.name), reason: `설정 layers: ${l.name}` }
      return { key: 'other', reason: '설정 layers 어디에도 맞지 않음' }
    }
    if (outside(n.path)) return { key: 'other', reason: '앱 밖 코드(테스트·데이터·평가·마이그레이션)' }
    if (n.route) return { key: 'endpoint', reason: `라우트 ${n.route.method} ${n.route.path}` }
    if (depended.has(n.id)) return { key: 'deps', reason: 'Depends로 주입됨' }
    if (WIRING.test(n.name)) return { key: 'deps', reason: `배선 함수 이름 ${n.name}` }
    const qual = qualOf(n)
    const outer = qual.includes('.') ? qual.split('.').slice(-2, -1)[0] : ''
    const owner = /^[A-Z]/.test(outer) ? outer : '' // 클래스만(감싼 함수 이름은 역할과 무관)
    const parts = n.path.split('/')
    const file = parts[parts.length - 1]
    // 가까운 폴더부터, 업무 폴더를 만나면 거기서 멈춘다(업무 이름과 그 위 뼈대는 역할이 아니다)
    const dirs: string[] = []
    let inBusiness: string | null = null
    for (let i = parts.length - 1; i >= 1; i--) {
      const dir = parts.slice(0, i).join('/')
      if (business.has(dir)) {
        inBusiness = dir
        break
      }
      dirs.push(parts[i - 1])
    }
    const named: Array<[string, string]> = [
      ...(owner ? [[owner, `클래스 이름 ${owner}`] as [string, string]] : []),
      [file, `파일 이름 ${file}`],
      ...dirs.map((d) => [d, `폴더 이름 ${d}/`] as [string, string]),
    ]
    for (const [name, why] of named) {
      const ws = words(name)
      // 같은 이름 안에서는 뒤 낱말(중심어)이 이긴다: query_service 는 서비스, user_queries 는 queries
      for (let i = ws.length - 1; i >= 0; i--) {
        const c = conceptOf([ws[i]], WORDS)
        if (c) return { key: c, reason: why }
        if (AMBIGUOUS.test(ws[i])) return { key: `custom:${ws[i]}`, reason: `${why} — 프로젝트마다 위치가 달라 호출 방향으로 층을 정함` }
        if (SHARED.test(ws[i])) return { key: `custom:${ws[i]}`, reason: `${why} — 공용 코드(위반 판정 안 함)`, shared: true }
      }
    }
    // 기술 낱말(llm, git …)은 업무 폴더 밖에서만: domains/x/llm.py 는 그 업무의 로직이다
    if (!inBusiness)
      for (const [name, why] of named) {
        const c = conceptOf(words(name), TOPIC)
        if (c) return { key: c, reason: why }
      }
    // 업무 폴더 안: 바로 안 파일은 도메인 로직, 중간 폴더가 있으면 그 폴더가 고유 레이어(domains/x/agents)
    const between = dirs.filter((d) => !CONTAINER.test(d))
    if (inBusiness && !between.length) return { key: 'logic', reason: `업무 폴더 ${inBusiness}/ 안 파일` }
    // 맨 위 폴더(모노레포의 앱 이름)는 레이어가 아니다
    const own = inBusiness ? between[0] : between.find((d) => d !== parts[0])
    if (own) return { key: `custom:${own}`, reason: `폴더 ${own}/ (프로젝트 고유 레이어)` }
    // 폴더 구조가 없는 납작한 백엔드(backend/chat.py, parser.py …): 파일 하나가 레이어 하나
    const stem = file.replace(/\.[a-z]+$/i, '')
    if (!/^(main|__init__|index|app)$/.test(stem)) return { key: `custom:${stem}`, reason: `파일 ${file} (폴더 구조가 없어 파일을 레이어로)` }
    return { key: 'other', reason: '이름으로 알 수 있는 구조 낱말이 없음' }
  }

  const picks = new Map<string, Pick>()
  for (const n of fns) picks.set(n.id, classify(n))
  // 고유 레이어는 함수 3개 이상일 때만(작으면 기타)
  const count = new Map<string, number>()
  for (const p of picks.values()) count.set(p.key, (count.get(p.key) ?? 0) + 1)
  for (const p of picks.values())
    if (p.key.startsWith('custom:') && !p.reason.startsWith('설정') && (count.get(p.key) ?? 0) < 3) {
      p.reason += ' — 함수가 적어 기타로'
      p.key = 'other'
    }

  // 레이어 목록
  const present = new Set([...picks.values()].map((p) => p.key))
  const sharedIds = new Set([...picks.values()].filter((p) => p.shared && p.key.startsWith('custom:')).map((p) => p.key))
  const ids = new Set(present)
  for (const l of cfgLayers) ids.add(namedKey(l.name))
  for (const a of assigns) ids.add(namedKey(a.name))
  const layers = new Map<string, ArchLayer>()
  let palette = 0
  const cfgIndex = new Map(cfgLayers.map((l, i) => [namedKey(l.name), i]))
  for (const id of ids) {
    const concept = (id.includes(':') ? 'custom' : id) as Concept
    const cfg = cfgLayers.find((l) => namedKey(l.name) === id)
    // 설정 레이어는 concept 가 없으면 이름 낱말로 색·모양만 맞춘다(services → 서비스 색)
    const metaConcept = concept === 'custom' ? (cfg?.concept ?? (cfg ? conceptOf(words(cfg.name), WORDS) : undefined)) : concept
    const meta = metaConcept && metaConcept !== 'custom' ? CONCEPTS[metaConcept] : null
    const name = concept === 'custom' ? id.slice(7) : CONCEPTS[concept as keyof typeof CONCEPTS].name
    layers.set(id, {
      id,
      name,
      concept,
      // 설정 layers 는 적힌 순서가 곧 층, 고유 레이어는 아래에서 호출 방향으로
      tier: cfgIndex.has(id) ? (meta && meta.tier === null ? null : cfgIndex.get(id)!) : concept !== 'custom' && meta ? meta.tier : null,
      color: meta?.color ?? CUSTOM_COLORS[palette++ % CUSTOM_COLORS.length],
      shape: meta?.shape ?? 'box',
      shapeName: meta?.shapeName ?? '상자',
      count: 0,
      side: 'back',
    })
  }
  const layerOf = new Map<string, string>()
  const reason = new Map<string, string>()
  for (const [id, p] of picks) {
    layerOf.set(id, p.key)
    reason.set(id, p.reason)
    if (!outside(model.byId.get(id)!.path)) layers.get(p.key)!.count++
  }

  // 함수끼리 호출을 레이어끼리 호출 수로
  const flow = new Map<string, number>() // "a|b" → 횟수
  for (const e of model.graph.edges) {
    if (e.kind !== 'calls') continue
    const a = layerOf.get(e.from)
    const b = layerOf.get(e.to)
    if (!a || !b || a === b) continue
    flow.set(`${a}|${b}`, (flow.get(`${a}|${b}`) ?? 0) + 1)
  }
  const calls = (a: string, b: string) => flow.get(`${a}|${b}`) ?? 0

  // 고유 레이어의 층: 부르는 쪽 층의 평균 + 1, 부르는 쪽이 없으면 불리는 쪽 층의 평균 - 1
  for (const l of layers.values()) {
    if (l.concept !== 'custom' || cfgIndex.has(l.id) || sharedIds.has(l.id)) continue
    let callerSum = 0
    let callerN = 0
    let calleeSum = 0
    let calleeN = 0
    for (const o of layers.values()) {
      if (o.tier === null || o.id === l.id || (o.concept === 'custom' && !cfgIndex.has(o.id))) continue
      const inn = calls(o.id, l.id)
      const out = calls(l.id, o.id)
      callerSum += o.tier * inn
      callerN += inn
      calleeSum += o.tier * out
      calleeN += out
    }
    if (callerN) l.tier = Math.min(2, Math.round(callerSum / callerN) + 1)
    else if (calleeN) l.tier = Math.max(0, Math.round(calleeSum / calleeN) - 1)
  }

  // 열 순서: 층 → 같은 층 안에서는 더 많이 부르는 쪽이 앞(호출 방향) → 개념 순서
  const all = [...layers.values()].filter((l) => present.has(l.id) || cfgIndex.has(l.id) || assigns.some((a) => namedKey(a.name) === l.id))
  const sameTierScore = (l: ArchLayer) => {
    let s = 0
    for (const o of all) if (o.id !== l.id && o.tier !== null && o.tier === l.tier) s += calls(l.id, o.id) - calls(o.id, l.id)
    return s
  }
  const rank = (l: ArchLayer) => {
    if (cfgIndex.has(l.id)) return cfgIndex.get(l.id)!
    if (l.concept === 'deps') return 0.5 // 엔드포인트 바로 다음(먼저 불리는 주입)
    if (l.tier === null) return 10 + CONCEPT_ORDER.indexOf(l.concept)
    return l.tier
  }
  const ordered = all.sort(
    (a, b) =>
      rank(a) - rank(b) ||
      sameTierScore(b) - sameTierScore(a) ||
      CONCEPT_ORDER.indexOf(a.concept) - CONCEPT_ORDER.indexOf(b.concept) ||
      a.name.localeCompare(b.name)
  )
  const byId = new Map(ordered.map((l) => [l.id, l]))

  // 건너뜀 관례: 엔드포인트가 서비스층을 거치는 게 보통인 프로젝트에서만 저장소·외부 직접 호출을 위반으로
  let via = 0
  let direct = 0
  for (const a of ordered)
    if (a.tier === 0)
      for (const b of ordered) {
        if (b.tier === 1) via += calls(a.id, b.id)
        if (b.tier === 2) direct += calls(a.id, b.id)
      }
  const fixed = typeof config.strict === 'boolean'
  const strict = fixed ? !!config.strict : via + direct >= 5 && direct / (via + direct) < 0.3

  // 명시 규칙
  let allow: Map<string, Set<string>> | null = null
  if (config.allow) {
    allow = new Map()
    for (const [from, tos] of Object.entries(config.allow)) allow.set(namedKey(from), new Set(tos.map(namedKey)))
  }

  const pattern = describePattern(files.map((f) => f.path), featureRoots, business, fns.length)
  const total = fns.filter((n) => !outside(n.path)).length
  const classified = fns.filter((n) => !outside(n.path) && layerOf.get(n.id) !== 'other').length
  const front = inferFront(model, assigns)
  for (const [id, key] of front.layerOf) layerOf.set(id, key)
  for (const [id, why] of front.reason) reason.set(id, why)
  for (const l of front.layers) byId.set(l.id, l)
  const allFns = model.graph.nodes.filter((n) => FUNCTION_KINDS.has(n.kind))
  return {
    pattern,
    source,
    layers: ordered,
    byId,
    layerOf,
    reason,
    allow,
    convention: { via, direct, strict, fixed },
    ctor: new Set(allFns.filter((n) => /^(__init__|__post_init__|constructor)$/.test(n.name)).map((n) => n.id)),
    file: new Map(allFns.map((n) => [n.id, n.path])),
    coverage: { classified, total },
    front: front.layers,
    frontConvention: front.convention,
    frontCoverage: front.coverage,
    forbidden: compileForbidden(config.forbidden ?? []),
  }
}

/**
 * 프론트 레이어: 화면·페이지 → 컴포넌트 → 훅·상태 → API 호출(+ 공용·기타).
 * 함수 종류(컴포넌트·훅·요청 보냄)와 파일·폴더 이름(pages, components, hooks, store, api …)으로 나눈다.
 * "건너뜀"은 백엔드처럼 그 프로젝트 관례로: 화면·컴포넌트가 대개 훅·상태를 거쳐 API를 부르는 프로젝트에서만 직접 부르기를 위반으로.
 */
function inferFront(model: Model, assigns: Array<{ key: string; name: string; re: RegExp | null }>) {
  const fns = model.graph.nodes.filter((n) => FUNCTION_KINDS.has(n.kind) && n.layer === 'frontend')
  const frontKey = (name: string): string => {
    const c = conceptByName(name)
    return c && FRONT_ORDER.includes(c) ? c : `fcustom:${name.trim()}`
  }
  const classify = (n: GraphNode): Pick => {
    for (const a of assigns)
      if (a.re ? a.re.test(n.path) : a.key === fnKey(n)) return { key: frontKey(a.name), reason: `설정 assign: ${a.key}` }
    if (FRONT_OUTSIDE.test(n.path)) return { key: 'front-other', reason: '테스트·스토리' }
    if (n.kind === 'hook') return { key: 'hook', reason: `훅(${n.name})` }
    // 요청을 보내는 일반 함수는 API 호출. 컴포넌트가 직접 보내면 그대로 화면·컴포넌트(그게 바로 "건너뜀" 판정 대상)
    if (n.http?.length && n.kind !== 'component')
      return { key: 'client', reason: `요청을 보냄(${n.http.map((h) => `${h.method} ${h.path}`).join(', ')})` }
    const parts = n.path.split('/')
    const file = parts[parts.length - 1]
    if (n.kind === 'component' && PAGE_FILE.test(n.path)) return { key: 'page', reason: `화면 파일 ${file}` }
    for (const [name, why] of [[file, `파일 이름 ${file}`], ...parts.slice(0, -1).reverse().map((d) => [d, `폴더 이름 ${d}/`])] as Array<[string, string]>) {
      const c = conceptOf(words(name), FRONT_WORDS)
      if (c) return { key: c === 'page' && n.kind !== 'component' ? 'util' : c, reason: why }
    }
    if (n.kind === 'component') return { key: 'component', reason: '컴포넌트' }
    return { key: 'front-other', reason: '이름으로 알 수 있는 구조 낱말이 없음' }
  }
  const layerOf = new Map<string, string>()
  const reason = new Map<string, string>()
  for (const n of fns) {
    const p = classify(n)
    layerOf.set(n.id, p.key)
    reason.set(n.id, p.reason)
  }
  const layers = new Map<string, ArchLayer>()
  let palette = 0
  for (const [id, key] of layerOf) {
    if (!layers.has(key)) {
      const meta = key.startsWith('fcustom:') ? null : CONCEPTS[key as keyof typeof CONCEPTS]
      layers.set(key, {
        id: key,
        name: meta?.name ?? key.slice(8),
        concept: (meta ? key : 'custom') as Concept,
        tier: meta?.tier ?? null,
        color: meta?.color ?? CUSTOM_COLORS[palette++ % CUSTOM_COLORS.length],
        shape: meta?.shape ?? 'box',
        shapeName: meta?.shapeName ?? '상자',
        count: 0,
        side: 'front',
      })
    }
    if (!FRONT_OUTSIDE.test(model.byId.get(id)!.path)) layers.get(key)!.count++
  }
  const ordered = [...layers.values()].sort(
    (a, b) => (FRONT_ORDER.indexOf(a.concept) + 1 || 99) - (FRONT_ORDER.indexOf(b.concept) + 1 || 99) || a.name.localeCompare(b.name)
  )
  let via = 0
  let direct = 0
  for (const e of model.graph.edges) {
    if (e.kind !== 'calls') continue
    const a = layers.get(layerOf.get(e.from) ?? '')
    const b = layers.get(layerOf.get(e.to) ?? '')
    if (!a || !b || a.tier === null || b.tier === null || a.tier > 1) continue
    if (b.tier === 2) via++
    if (b.tier === 3) direct++
  }
  const total = fns.filter((n) => !FRONT_OUTSIDE.test(n.path)).length
  const classified = fns.filter((n) => !FRONT_OUTSIDE.test(n.path) && layerOf.get(n.id) !== 'front-other').length
  return {
    layers: ordered,
    layerOf,
    reason,
    convention: { via, direct, strict: via + direct >= 5 && direct / (via + direct) < 0.3 },
    coverage: { classified, total },
  }
}

/** 금지 규칙을 검사 함수로. 경로는 규칙이 있던 폴더(base) 기준으로 맞춘다. 깨진 정규식은 그 규칙만 버린다 */
function compileForbidden(rules: ForbiddenRule[]) {
  const out: ArchMap['forbidden'] = []
  for (const r of rules) {
    try {
      const re = (p?: string) => (p ? new RegExp(p) : null)
      const [fp, fn, tp, tn] = [re(r.from.path), re(r.from.pathNot), re(r.to.path), re(r.to.pathNot)]
      const rel = (p: string) => (r.base && p.startsWith(`${r.base}/`) ? p.slice(r.base.length + 1) : p)
      out.push({
        name: r.name,
        test: (from, to) => {
          const a = rel(from)
          const b = rel(to)
          return (!fp || fp.test(a)) && !(fn && fn.test(a)) && (!tp || tp.test(b)) && !(tn && tn.test(b))
        },
      })
    } catch {
      // 이 엔진이 못 읽는 정규식
    }
  }
  return out
}

/** 감지한 설계 패턴을 한 줄로: 업무별 폴더형 + 포트·어댑터, 계층형, 클린, MVC … */
function describePattern(paths: string[], featureRoots: Set<string>, business: Set<string>, fnCount: number): string {
  const segs = new Set(paths.flatMap((p) => p.split('/').map((s) => s.replace(/\.[a-z]+$/, ''))))
  const has = (...names: string[]) => names.some((n) => segs.has(n))
  const featureShare = paths.filter((p) => [...business].some((b) => p.startsWith(`${b}/`))).length / Math.max(1, paths.length)
  const parts: string[] = []
  if (featureShare >= 0.3) {
    // 업무 폴더 안 파일이 가장 많은 뿌리(상위 폴더는 모든 걸 품으니 업무 폴더 안만 센다)
    const under = (r: string) => paths.filter((p) => [...business].some((d) => d.startsWith(`${r}/`) && d.split('/').length === r.split('/').length + 1 && p.startsWith(`${d}/`))).length
    const root = [...featureRoots].sort((a, b) => under(b) - under(a))[0] ?? ''
    parts.push(`업무별 폴더형 (${root.split('/').pop() || root}/<업무>/…)`)
  }
  if (has('ports', 'port') && has('adapters', 'adapter')) parts.push('포트·어댑터')
  if (has('usecases', 'use_cases', 'interactors') && has('entities')) parts.push('클린 아키텍처')
  if (has('views') && has('models') && has('urls')) parts.push('MVC')
  if (!parts.length && has('routers', 'routes', 'api') && has('services', 'service') && has('repositories', 'repository', 'crud'))
    parts.push('계층형 (router → service → repository)')
  if (!parts.length) parts.push(fnCount ? '정해진 패턴 없음 · 이름으로 추정' : '백엔드 없음')
  return parts.join(' + ')
}

export type Violation = 'back' | 'skip' | `rule:${string}`

/**
 * 두 함수 사이 호출이 레이어 규칙을 어기는지: back(아래가 위를 부름) · skip(관례상 거쳐야 할 층을 건너뜀)
 * · rule:이름(금지 규칙). 프론트 ↔ 백엔드(HTTP)는 보지 않는다.
 */
export function violationOf(arch: ArchMap, from: string, to: string): Violation | undefined {
  const pf = arch.file.get(from)
  const pt = arch.file.get(to)
  if (pf && pt && pf !== pt) for (const r of arch.forbidden) if (r.test(pf, pt)) return `rule:${r.name}`
  const a = arch.byId.get(arch.layerOf.get(from) ?? '')
  const b = arch.byId.get(arch.layerOf.get(to) ?? '')
  if (!a || !b || a.id === b.id || a.side !== b.side || arch.ctor.has(to) || pf === pt) return
  if (a.side === 'front') {
    if (a.tier === null || b.tier === null) return
    if (b.tier < a.tier) return 'back'
    if (a.tier <= 1 && b.tier === 3 && arch.frontConvention.strict) return 'skip'
    return
  }
  const index = (l: ArchLayer) => arch.layers.indexOf(l)
  if (arch.allow) {
    const ok = arch.allow.get(a.id)
    if (!ok || ok.has(b.id) || b.tier === null) return
    return index(b) < index(a) ? 'back' : 'skip'
  }
  if (a.tier === null || b.tier === null) return
  if (b.tier < a.tier) return 'back'
  if (a.tier === 0 && b.tier === 2 && arch.convention.strict) return 'skip'
}

/** 화면에서 옮길 때 쓰는 규칙 키: 함수 하나 / 파일 / 폴더 */
export function assignKey(n: GraphNode, scope: 'function' | 'file' | 'dir'): string {
  if (scope === 'function') return fnKey(n)
  if (scope === 'file') return n.path
  return `${n.path.split('/').slice(0, -1).join('/')}/**`
}

/** 클래스 명세 층 표 → 층 설정(assign). 표가 없으면 null — 자동 추정만 (UI-19 6.8, 카드 CG) */
export function specSource(rows: Array<{ name: string; patterns: string[] }>): ArchSource | null {
  if (!rows.length) return null
  const assign: Record<string, string> = {}
  for (const r of rows) for (const p of r.patterns) if (!(p in assign)) assign[p] = r.name
  return { kind: 'spec', path: '클래스 명세 「폴더 구조」 층 표', config: { assign } }
}
