/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 서버의 FlowView를 view_arc 뷰어가 읽는 그래프 꼴(CodeGraph)로 바꾼다.
 *  뷰어 계산(model·layout·world·flow·arch·scene)은 view_arc에서 옮긴 그대로 두고 데이터만 맞춘다(카드 CG).
 *  함수 노드 id는 싱크독 그래프 열쇠(`파일:줄`) 그대로 — 실행 기록의 사건 `fn`과 같다(MS-024·MS-025). */
import type { FlowFunction, FlowView } from '../api/client'
import type { CodeGraph, GraphEdge, GraphNode, InfraMap, Lang, NodeKind, SpecOverlay, StackPart, Step } from './types'

const LANG: Record<string, Lang> = {
  python: 'py',
  typescript: 'ts',
  javascript: 'ts',
  rust: 'rust',
  go: 'go',
  java: 'java',
  kt: 'kotlin',
  scala: 'scala',
  rb: 'ruby',
  php: 'php',
  cs: 'csharp',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  hpp: 'cpp',
  swift: 'swift',
  vue: 'vue',
  svelte: 'svelte',
}
const PKG_STEMS = new Set(['service', '__init__', 'index'])
const REQ = /\.(get|post|put|patch|delete|del|head|request)$|^fetch$/

const fileId = (path: string) => `file:${path}`
const dirId = (path: string) => `dir:${path}`
const ext = (path: string) => path.slice(path.lastIndexOf('.') + 1).toLowerCase()

function langOf(path: string, lang: string | null | undefined): Lang | undefined {
  const l = lang ?? ext(path)
  return LANG[l] ?? (ext(path) === 'py' ? 'py' : /^(ts|tsx|js|jsx|mjs)$/.test(ext(path)) ? 'ts' : ext(path) === 'rs' ? 'rust' : undefined)
}

/** 그래프 qual의 모듈 이름 — MS-011 reduce 2 · enrich 2e와 같은 규칙 */
function moduleOf(path: string): string {
  const parts = path.split('/')
  const name = parts[parts.length - 1]
  const stem = name.includes('.') ? name.slice(0, name.lastIndexOf('.')) : name
  const parent = parts.length > 1 ? parts[parts.length - 2] : ''
  if (path.endsWith('.rs')) {
    if (stem === 'mod' && parent) return parent
    if ((stem === 'lib' || stem === 'main') && parent === 'src' && parts.length > 2) return parts[parts.length - 3]
    return stem
  }
  return PKG_STEMS.has(stem) && parent ? parent : stem
}

function isFront(path: string, webDirs: string[]): boolean {
  if (/\.(tsx|jsx)$/.test(path)) return true
  if (!/\.(ts|js|mjs)$/.test(path)) return false
  return webDirs.some((d) => d === '' || path.startsWith(d + '/'))
}

function kindOf(f: FlowFunction, front: boolean, owner: string | null): NodeKind {
  if (owner) return 'method'
  if (front && /^use[A-Z]/.test(f.name)) return 'hook'
  if (front && /\.(tsx|jsx)$/.test(f.file) && /^[A-Z]/.test(f.name)) return 'component'
  return 'function'
}

/** FlowView → view_arc CodeGraph. `name`은 프로젝트 이름 */
export function toCodeGraph(view: FlowView, name: string): CodeGraph {
  const webDirs = view.units.filter((u) => u.kind === 'web').map((u) => u.dir)
  const nodes: GraphNode[] = [{ id: 'project', kind: 'project', name, parent: null, path: '' }]
  const files = new Map(view.files.map((f) => [f.path, f]))
  for (const f of view.functions) if (!files.has(f.file)) files.set(f.file, { path: f.file, lang: null, loc: f.end ?? f.line })
  const paths = [...files.keys()].sort()

  // 폴더 — 화면 파일만 든 폴더는 화면 쪽
  const dirs = new Map<string, { front: number; all: number }>()
  for (const p of paths) {
    const parts = p.split('/')
    for (let i = 1; i < parts.length; i++) {
      const d = parts.slice(0, i).join('/')
      const c = dirs.get(d) ?? { front: 0, all: 0 }
      c.all++
      if (isFront(p, webDirs)) c.front++
      dirs.set(d, c)
    }
  }
  for (const d of [...dirs.keys()].sort()) {
    const parent = d.includes('/') ? dirId(d.slice(0, d.lastIndexOf('/'))) : 'project'
    const c = dirs.get(d)!
    nodes.push({ id: dirId(d), kind: 'dir', name: d.split('/').pop()!, parent, path: d, layer: c.front === c.all ? 'frontend' : 'backend' })
  }
  for (const p of paths) {
    const f = files.get(p)!
    const parent = p.includes('/') ? dirId(p.slice(0, p.lastIndexOf('/'))) : 'project'
    nodes.push({ id: fileId(p), kind: 'file', name: p.split('/').pop()!, parent, path: p, lang: langOf(p, f.lang), layer: isFront(p, webDirs) ? 'frontend' : 'backend', loc: f.loc })
  }

  // 화면 요청 → 그 함수의 요청 호출(대상 없음)에 라우트를 대상으로 단다 — 흐름 재생이 프론트→백엔드를 건넌다
  const httpOf = new Map<string, string[]>()
  for (const h of view.http) httpOf.set(h.from, [...(httpOf.get(h.from) ?? []), h.to])
  const classes = new Map<string, GraphNode>()
  const uses = new Map<string, Set<string>>()
  for (const f of view.functions) {
    const front = isFront(f.file, webDirs)
    const prefix = f.qual.includes('.') ? f.qual.slice(0, f.qual.lastIndexOf('.')) : ''
    const owner = prefix && prefix !== moduleOf(f.file) && !prefix.includes('.') ? prefix : null
    let parent = fileId(f.file)
    if (owner) {
      const cid = `class:${f.file}::${owner}`
      const c = classes.get(cid)
      if (!c) {
        const node: GraphNode = { id: cid, kind: 'class', name: owner, parent, path: f.file, lang: langOf(f.file, null), layer: front ? 'frontend' : 'backend', line: f.line }
        classes.set(cid, node)
        nodes.push(node)
      } else if ((c.line ?? 0) > f.line) c.line = f.line
      parent = cid
    }
    const routes = [...(httpOf.get(f.key) ?? [])]
    const steps: Step[] = f.steps.map((s) => {
      if (s.k !== 'call') return { kind: s.k, line: s.line, label: s.label }
      const step: Step = { kind: 'call', line: s.line, label: s.label, edge: 'calls', confidence: s.inferred ? 'inferred' : 'exact' }
      if (s.to) step.target = s.to
      else if (routes.length && REQ.test(s.label)) {
        step.target = routes.shift()!
        step.edge = 'http'
      }
      if (s.awaited) step.awaited = true
      if (s.deferred) step.deferred = true
      if (s.infra) {
        step.infra = s.infra
        ;(uses.get(s.infra) ?? uses.set(s.infra, new Set()).get(s.infra)!).add(f.key)
      }
      return step
    })
    nodes.push({
      id: f.key,
      kind: kindOf(f, front, owner),
      name: f.name,
      parent,
      path: f.file,
      lang: langOf(f.file, null),
      layer: front ? 'frontend' : 'backend',
      line: f.line,
      ...(f.end ? { endLine: f.end, loc: f.end - f.line + 1 } : {}),
      ...(f.route ? { route: f.route } : {}),
      ...(f.route ? {} : routesOf(view, f.key)),
      steps,
    })
  }

  const edges: GraphEdge[] = [
    ...view.calls.map(([from, to]): GraphEdge => ({ from, to, kind: 'calls', confidence: 'exact' })),
    ...view.http.map((h): GraphEdge => ({ from: h.from, to: h.to, kind: 'http', confidence: h.inferred ? 'inferred' : 'exact' })),
  ]
  const infra: InfraMap | undefined = view.infra.nodes.length
    ? {
        nodes: view.infra.nodes.map((n) => ({
          id: n.id,
          kind: n.kind,
          name: n.name,
          where: n.where,
          ...(n.host ? { host: n.host } : {}),
          evidence: n.evidence,
          uses: uses.get(n.id)?.size ?? 0,
          ...(n.dir !== null ? { dir: n.dir } : {}),
        })),
        links: view.infra.links,
      }
    : undefined
  const parts: StackPart[] = view.units.map((u) => ({
    id: `${u.kind}:${u.dir}`,
    role: u.kind === 'server' ? 'backend' : u.kind === 'web' ? 'frontend' : 'worker',
    dir: u.dir,
    lang: langOf(u.dir || 'x', u.lang) ?? 'py',
    framework: u.framework ?? '',
    ...(u.command ? { run: { cmd: u.command, cwd: u.dir, from: '목록 파일' } } : {}),
    ...(u.port ? { port: u.port } : {}),
    trace: ['python', 'typescript', 'javascript', 'rust', 'java', 'go'].includes(u.lang) ? 'ready' : 'none',
  }))
  const fns = view.functions
  return {
    version: 1,
    project: { name, root: '', generatedAt: view.graph?.built_at ?? '' },
    nodes,
    edges,
    stats: {
      files: paths.length,
      functions: fns.length,
      components: nodes.filter((n) => n.kind === 'component').length,
      routes: fns.filter((f) => f.route).length,
      calls: view.calls.length,
      httpLinked: view.http.length,
    },
    ...(specsOf(fns) ? { specs: specsOf(fns)! } : {}),
    ...(infra ? { infra } : {}),
    stack: { parts },
  }
}

/** 화면 함수가 보내는 요청 — 라우트 쪽 경로로(뷰어의 「API 호출」 층 판정에 쓴다) */
function routesOf(view: FlowView, key: string): Partial<GraphNode> {
  const routes = view.http
    .filter((h) => h.from === key)
    .map((h) => view.functions.find((f) => f.key === h.to)?.route)
    .filter((r): r is NonNullable<typeof r> => !!r)
  return routes.length ? { http: routes } : {}
}

/** 명세 대조 덧칠 — MINISPEC 항목이 있는 함수의 상태(같음 → ok, 코드만·명세만 → diff) */
function specsOf(fns: FlowFunction[]): SpecOverlay | null {
  const items = fns
    .filter((f) => f.ms)
    .map((f) => {
      const [doc, name] = f.ms!.split('#')
      return {
        id: f.ms!,
        doc,
        name,
        title: '',
        node: f.key,
        match: 'docstring' as const,
        calls: [],
        status: f.status === 'same' ? ('ok' as const) : ('diff' as const),
        onlySpec: [],
        onlyCode: [],
      }
    })
  if (!items.length) return null
  const docs = [...new Set(items.map((i) => i.doc))].map((id) => ({ id, type: 'MS', title: id, status: '', path: '', items: items.filter((i) => i.doc === id).length }))
  return { root: '', docs, items }
}
