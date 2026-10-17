/** UI-19 흐름 보기 — SYNC-UI-002#UI-19 (카드 CG). view_arc의 뷰어(components/code-viewer/code-viewer.tsx)를 옮겼다.
 *  1 브레드크럼 줄(1.1 요약) · 2 툴바(2.1 보기 · 2.2 단계 · 2.3 덧칠 · 2.4 찾기 · 2.5 코드 그래프로)
 *  3 탐색기 | 4 장면(three.js, 이름표 4.1~4.4는 scene.ts · 4.5 위치 · 4.6 장비 왕복) | 5 패널
 *  패널은 고른 것에 따라 — 아무것도 없으면 개요(5.1~5.3·5.11), 함수면 상세(5.4~5.7), 장비면 장비(5.8~5.10),
 *  API 흐름이면 6.x, 재생 중이면 7.x. 주소: ?view=api · ?focus={파일:줄} · ?trace={id} (히스토리는 안 쌓는다).
 *  이 파일과 flow/의 나머지는 three.js와 함께 이 화면을 열 때만 불러온다(INFRA 3장, UI-001 7장 18). */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type FlowView, type TraceBrief, type TraceCoverage } from '../api/client'
import { ProjName } from '../components/ui'
import { toCodeGraph } from './adapt'
import { inferArch, specSource } from './arch'
import { DEFAULT_FLOW, type FlowOptions, apiFlow, layoutFlow } from './flow'
import { layoutCity } from './layout'
import {
  DEFAULT_TRACE,
  FUNCTION_KINDS,
  type TraceEvent,
  type TraceOptions,
  buildModel,
  buildTrace,
  displayName,
  fileOf,
  frontRuntimeTrace,
  runtimeTrace,
  viewPath,
  withFrontChain,
} from './model'
import { COLORS, CodeScene } from './scene'
import type { RuntimeRecord } from './types'
import { type InfraSeen, serverFor, withRuntime, worldCity } from './world'
import { ApiDetail, ApiList } from './ApiPanel'
import { DevicePanel } from './DevicePanel'
import { Explorer } from './Explorer'
import { Inspector } from './Inspector'
import { Overview } from './Overview'
import { branches, useTraces } from './traces'
import { type TraceState, TracePanel } from './TracePanel'

type Mode = 'base' | 'coverage' | 'spec'
type Props = { code: string; projName: string | undefined; view: FlowView; local: boolean }

export default function FlowScreen({ code, projName, view: data, local }: Props) {
  const classDoc = data.layers[0]?.doc ?? null
  const [sp, setSp] = useSearchParams()
  const graph = useMemo(() => toCodeGraph(data, projName ?? code), [data, projName, code])
  const model = useMemo(() => buildModel(graph), [graph])
  const arch = useMemo(() => inferArch(model, specSource(data.layers)), [model, data.layers])
  const fnByKey = useMemo(() => new Map(data.functions.map((f) => [f.key, f])), [data])
  const [infraSeen, setInfraSeen] = useState<InfraSeen[]>([])
  const infra = useMemo(() => withRuntime(model, graph.infra, infraSeen), [model, graph, infraSeen])
  const { layout, cityModel } = useMemo(() => {
    const layout = layoutCity(model.root)
    const world = worldCity(model.root, layout, infra)
    return { layout, cityModel: world ? { ...model, world } : model }
  }, [model, infra])

  const setParam = useCallback(
    (key: string, value: string | null) =>
      setSp(
        (prev) => {
          const p = new URLSearchParams(prev)
          if (value === null) p.delete(key)
          else p.set(key, value)
          return p
        },
        { replace: true },
      ),
    [setSp],
  )
  const viewMode: 'city' | 'api' = sp.get('view') === 'api' ? 'api' : 'city'
  const [apiRoute, setApiRoute] = useState<string | null>(null)
  const [flowOptions, setFlowOptions] = useState<FlowOptions>(DEFAULT_FLOW)
  const defaultRoute = useMemo(() => {
    const routes = graph.nodes.filter((n) => n.route)
    return (routes.find((r) => (model.in.get(r.id) ?? []).some((e) => e.kind === 'http')) ?? routes[0])?.id ?? null
  }, [graph, model])
  const flowData = useMemo(() => {
    const id = apiRoute ?? defaultRoute
    if (viewMode !== 'api' || !id) return null
    const flow = apiFlow(model, arch, id, flowOptions)
    return { flow, ...layoutFlow(model, flow, infra) }
  }, [viewMode, apiRoute, defaultRoute, model, arch, flowOptions, infra])
  const sceneModel = flowData?.model ?? cityModel
  const sceneLayout = flowData?.layout ?? layout

  const stageRef = useRef<HTMLDivElement>(null)
  const labelsRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<CodeScene | null>(null)
  const [focusId, setFocusId] = useState(model.root.id)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null)
  const [trace, setTrace] = useState<TraceState | null>(null)
  const [traceOptions, setTraceOptions] = useState<TraceOptions>(DEFAULT_TRACE)
  const [speed, setSpeed] = useState(1)
  const [follow, setFollow] = useState(false)
  const [showTree, setShowTree] = useState(() => readFlag('syncdoc.flow.tree', true))
  const [live, setLive] = useState(true)
  const [mode, setMode] = useState<Mode>('base')
  const [coverage, setCoverage] = useState<TraceCoverage | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [requestOpen, setRequestOpen] = useState(false)
  const [q, setQ] = useState('')
  const focusRef = useRef(focusId)
  const selectedRef = useRef<string | null>(null)
  useEffect(() => {
    selectedRef.current = selectedId
  }, [selectedId])

  const focus = useCallback((id: string) => {
    focusRef.current = id
    setFocusId(id)
    sceneRef.current?.focus(id)
  }, [])
  const select = useCallback(
    (id: string | null) => {
      selectedRef.current = id
      setSelectedId(id)
      sceneRef.current?.select(id)
      const n = id ? model.byId.get(id) : undefined
      setParam('focus', n && FUNCTION_KINDS.has(n.kind) ? id : null)
    },
    [model, setParam],
  )
  const closeTrace = useCallback(() => {
    setTrace(null)
    sceneRef.current?.setTrace(null, [])
    setParam('trace', null)
  }, [setParam])

  /** 탐색기·패널·장면 어디서 골라도 같은 규칙 — 폴더·파일은 초점, 함수는 그 파일로 들어가 고른다 */
  const open = useCallback(
    (id: string) => {
      const node = model.byId.get(id)
      if (!node) return
      if (trace) closeTrace()
      if (flowData) {
        select(FUNCTION_KINDS.has(node.kind) ? id : null)
        return
      }
      if (node.kind === 'project' || node.kind === 'dir' || node.kind === 'file') {
        const v = model.viewOf.get(id)!
        focus(v.id)
        select(node.kind === 'project' ? null : v.id)
        return
      }
      const file = fileOf(model, id)
      if (file && focusRef.current !== file.id) focus(file.id)
      select(id)
    },
    [model, focus, select, trace, closeTrace, flowData],
  )

  /** 장면 클릭 — 받침대는 그 위 코드로, 다른 장비는 장비 상세, 멀리서 건물은 그 파일로 */
  const onSceneClick = useCallback(
    (id: string) => {
      const node = model.byId.get(id)
      if (node?.kind === 'infra') {
        const device = sceneModel.world?.devices.find((d) => d.id === id)
        if (!flowData && device?.carries) {
          const group = model.root.children.filter(
            (v) => !v.aux && (id === 'infra:browser' ? v.node.layer === 'frontend' : v.node.layer !== 'frontend' && serverFor(infra, v.node.path)?.id === id),
          )
          if (group.length === 1) return open(group[0].id)
        }
        return select(id)
      }
      if (flowData) return select(node && FUNCTION_KINDS.has(node.kind) ? id : null)
      if (!node) return
      const file = fileOf(model, id)
      if (file && node.kind !== 'file' && focusRef.current !== file.id) return open(file.id)
      open(id)
    },
    [model, open, flowData, select, sceneModel, infra],
  )

  // 처음 열 때 ?focus — 그 함수를 골라 코드 단계로 (UI-17 4.11에서 온다)
  const initial = useRef(sp.get('focus'))
  useEffect(() => {
    const id = initial.current
    initial.current = null
    if (id && model.byId.get(id)) open(id)
  }, [model, open])

  const flowEvents = useMemo(() => {
    if (!flowData) return []
    const id = flowData.flow.routeId
    const only = new Set(flowData.flow.columns.flatMap((c) => c.ids))
    for (const d of flowData.model.world?.devices ?? []) only.add(d.id)
    return withFrontChain(model, id, buildTrace(model, id, { ...traceOptions, maxDepth: 12, includeExternal: false, only }), '')
  }, [flowData, model, traceOptions])

  const applyTrace = useCallback((t: TraceState) => {
    setSelectedId(t.rootId)
    sceneRef.current?.select(t.rootId)
    sceneRef.current?.setTrace(t.rootId, t.events, t.branch?.color ?? null)
    setTrace(t)
    sceneRef.current?.play()
  }, [])
  const startTrace = useCallback(
    (rootId: string, options = traceOptions) => applyTrace({ rootId, events: buildTrace(model, rootId, options), index: -1, playing: true }),
    [model, traceOptions, applyTrace],
  )
  const startApiTrace = useCallback(() => {
    if (flowData) applyTrace({ rootId: flowData.flow.routeId, events: flowEvents, index: -1, playing: true })
  }, [flowData, flowEvents, applyTrace])

  const switchView = (next: 'city' | 'api') => {
    if (next === viewMode) return
    setTrace(null)
    setSelectedId(null)
    focusRef.current = model.root.id
    setFocusId(model.root.id)
    setParam('view', next === 'api' ? 'api' : null)
  }

  // 실행 기록 — 고르면 사건을 받아 재생한다. 화면 기록이면 안의 요청마다 시각·경로가 가까운 서버 기록을 잇는다
  const itemsRef = useRef<TraceBrief[]>([])
  const pending = useRef<TraceState | null>(null)
  const viewRef = useRef({ api: false, route: null as string | null })
  useEffect(() => {
    viewRef.current = { api: !!flowData, route: flowData?.flow.routeId ?? null }
  }, [flowData])
  const playRuntime = useCallback(
    async (brief: TraceBrief) => {
      const load = async (id: number) => {
        try {
          return (await api.get<{ record: RuntimeRecord }>(`/api/projects/${code}/traces/${id}`)).record
        } catch {
          return null
        }
      }
      const record = await load(brief.id)
      if (!record) return setNotice('기록을 읽지 못했습니다')
      let built: { rootId: string; events: TraceEvent[]; result: string; via?: string } | null
      if (record.kind === 'front') {
        const backs = new Map<number, RuntimeRecord>()
        const start = new Date(record.startedAt).getTime()
        await Promise.all(
          record.events
            .filter((e) => e.fetch)
            .map(async (e) => {
              const f = e.fetch!
              const at = start + e.t0
              const match = itemsRef.current
                .filter((t) => t.kind !== 'front' && t.method === f.method && (t.path === f.path || t.path.endsWith(f.path) || f.path.endsWith(t.path)))
                .map((t) => ({ t, gap: Math.abs(new Date(t.started_at).getTime() - at) }))
                .filter((x) => x.gap < 10_000)
                .sort((a, b) => a.gap - b.gap)[0]
              const back = match && (await load(match.t.id))
              if (back) backs.set(e.i, back)
            }),
        )
        built = frontRuntimeTrace(model, record, (e) => backs.get(e.i))
      } else {
        const b = runtimeTrace(model, record)
        built = b && { ...b, events: withFrontChain(model, b.rootId, b.events, b.result) }
      }
      if (!built) return setNotice('이 기록의 함수가 지금 그래프에 없습니다 — 기록할 때의 커밋이 그래프와 다를 수 있습니다.')
      setNotice(null)
      setParam('trace', String(brief.id))
      const t: TraceState = {
        rootId: built.rootId,
        events: built.events,
        index: -1,
        playing: true,
        runtime: brief,
        result: built.result,
        via: built.via,
        branch: branches(itemsRef.current).get(brief.id),
      }
      if (viewRef.current.api) {
        const http = built.events.find((e) => e.type === 'call' && e.step.edge === 'http')
        const routeId = http && http.type === 'call' ? http.to : model.byId.get(built.rootId)?.route ? built.rootId : null
        if (routeId && routeId !== viewRef.current.route) {
          pending.current = t
          setSelectedId(null)
          setApiRoute(routeId)
          return
        }
      } else {
        const file = fileOf(model, built.rootId)
        if (file) {
          focusRef.current = file.id
          setFocusId(file.id)
        }
      }
      applyTrace(t)
    },
    [model, code, applyTrace, setParam],
  )
  const liveRef = useRef({ live, playing: false })
  useEffect(() => {
    liveRef.current = { live, playing: !!trace?.playing }
  }, [live, trace])
  const runtime = useTraces(code, (latest) => {
    if (!liveRef.current.live) return
    if (liveRef.current.playing && latest.kind !== 'front') return
    playRuntime(latest)
  })
  useEffect(() => {
    itemsRef.current = runtime.items
  }, [runtime.items])
  // ?trace= — 처음 열 때 그 기록을 재생
  const initialTrace = useRef(sp.get('trace'))
  useEffect(() => {
    const id = Number(initialTrace.current)
    if (!id) return
    const hit = runtime.items.find((t) => t.id === id)
    if (hit) {
      initialTrace.current = null
      playRuntime(hit)
    }
  }, [runtime.items, playRuntime])

  // 커버리지와 실제로 닿은 장비 — 새 기록이 들어올 때마다
  const latestId = runtime.items[0]?.id
  useEffect(() => {
    if (!runtime.items.length) return
    let alive = true
    api
      .get<TraceCoverage>(`/api/projects/${code}/traces/coverage`)
      .then((c) => {
        if (!alive) return
        setCoverage(c)
        setInfraSeen((prev) => {
          const next = c.infra.map((x) => ({ kind: x.kind, target: x.target, count: 1, last: '' }))
          return JSON.stringify(prev.map((x) => [x.kind, x.target])) === JSON.stringify(next.map((x) => [x.kind, x.target])) ? prev : next
        })
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [code, latestId, runtime.items.length])

  const overlay = useMemo(() => {
    if (mode === 'coverage') {
      const colors: Record<string, string> = {}
      const ran = new Set(coverage?.keys ?? [])
      for (const n of graph.nodes) if (ran.has(n.id)) colors[n.id] = COLORS.covered
      return colors
    }
    if (mode === 'spec') {
      const colors: Record<string, string> = {}
      for (const f of data.functions) if (f.ms) colors[f.key] = f.status === 'same' ? COLORS.specOk : COLORS.specDiff
      return colors
    }
    return null
  }, [mode, coverage, graph, data])
  useEffect(() => {
    sceneRef.current?.setOverlay(overlay)
  }, [overlay, sceneModel])

  // 장면 — 모델·배치가 바뀔 때만 다시 짓는다
  const callbacks = useRef({ onSceneClick })
  useEffect(() => {
    callbacks.current.onSceneClick = onSceneClick
  }, [onSceneClick])
  useEffect(() => {
    const stage = stageRef.current
    const labels = labelsRef.current
    if (!stage || !labels) return
    const scene = new CodeScene(stage, labels, sceneModel, sceneLayout, {
      onHover: (id, x, y) => setHover(id ? { id, x, y } : null),
      onClick: (id) => callbacks.current.onSceneClick(id),
      onDrag: () => {},
      onDrop: () => {},
      onTraceStep: (index) => setTrace((t) => (t ? { ...t, index } : t)),
      onTraceEnd: () => setTrace((t) => (t ? { ...t, playing: false } : t)),
    })
    sceneRef.current = scene
    // 장면보다 먼저 정한 초점·선택(?focus 등)을 새 장면에 건다
    if (!sceneModel.flow && focusRef.current !== sceneModel.root.id && sceneModel.viewOf.has(focusRef.current)) scene.focus(focusRef.current)
    if (selectedRef.current) scene.select(selectedRef.current)
    const p = pending.current
    pending.current = null
    const frame = p ? requestAnimationFrame(() => applyTrace(p)) : 0
    return () => {
      cancelAnimationFrame(frame)
      scene.dispose()
      sceneRef.current = null
    }
  }, [sceneModel, sceneLayout, applyTrace])

  useEffect(() => {
    if (!flowData) return
    sceneRef.current?.setFlowEdges(flowData.flow.edges)
    const order: Array<{ from: string; to: string; n: number; bad?: boolean }> = []
    const seen = new Set<string>()
    for (const e of flowEvents) {
      if (e.type !== 'call' || seen.has(`${e.from}|${e.to}`)) continue
      seen.add(`${e.from}|${e.to}`)
      const bad = flowData.flow.edges.some((x) => x.from === e.from && x.to === e.to && x.violation)
      order.push({ from: e.from, to: e.to, n: order.length + 1, bad })
    }
    sceneRef.current?.setFlowOrder(order)
  }, [flowData, flowEvents, sceneModel])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return
      if (e.key === 'Escape') {
        if (trace) return closeTrace()
        if (viewRef.current.api) return select(null)
        const parent = model.viewOf.get(focusRef.current)?.parent
        if (parent) open(parent.id)
      } else if (e.key === ' ' && trace) {
        e.preventDefault()
        if (trace.playing) sceneRef.current?.pause()
        else sceneRef.current?.play()
        setTrace({ ...trace, playing: !trace.playing })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [model, trace, open, closeTrace, select])

  // 2.4 찾기 — 300ms 뒤 첫 맞는 것(함수 이름·Class.fn·라우트 경로·파일)
  useEffect(() => {
    const t = q.trim().toLowerCase()
    if (!t) return
    const timer = setTimeout(() => {
      const hit =
        graph.nodes.find((n) => FUNCTION_KINDS.has(n.kind) && (n.name.toLowerCase() === t || displayName(n).toLowerCase() === t)) ??
        graph.nodes.find((n) => FUNCTION_KINDS.has(n.kind) && (displayName(n).toLowerCase().includes(t) || n.route?.path.toLowerCase().includes(t))) ??
        graph.nodes.find((n) => n.kind === 'file' && n.path.toLowerCase().includes(t))
      if (hit) {
        setNotice(null)
        open(hit.id)
      } else setNotice(`「${q.trim()}」 — 없음`)
    }, 300)
    return () => clearTimeout(timer)
  }, [q, graph, open])

  // 4.6 — 재생 중 장비 사건
  const trip = useMemo(() => {
    if (!trace || trace.index < 0) return null
    const e = trace.events[trace.index]
    if (!e || e.type !== 'call') return null
    const d = model.byId.get(e.to)
    if (d?.kind !== 'infra') return null
    return `${d.name} · ${e.step.label}${e.ms !== undefined ? ` · ${e.ms}ms` : ''}`
  }, [trace, model])

  const runApi = (routeId: string) => {
    const route = model.byId.get(routeId)?.route
    if (!route) return
    setApiRoute(routeId)
    setTrace(null)
    setSelectedId(null)
    setLive(true)
    setRequestOpen(true)
    if (!local) setNotice('싱크독_깃허브는 요청을 대신 보내지 않습니다 — 요청 보내기에서 명령을 복사하세요.')
  }
  const levelOf = model.viewOf.get(focusId)?.node.kind
  const level = levelOf === 'project' ? '장비' : levelOf === 'file' ? '코드' : '폴더'
  const goLevel = (name: '장비' | '폴더' | '코드') => {
    if (name === '장비') return open(model.root.id)
    if (name === '폴더') {
      const main = model.root.children.find((v) => !v.aux) ?? model.root.children[0]
      if (main) open(main.id)
      return
    }
    const sel = selectedId ? fileOf(model, selectedId) : undefined
    const firstFile = (function find(v): string | undefined {
      if (v.node.kind === 'file') return v.id
      for (const c of v.children) {
        const hit = find(c)
        if (hit) return hit
      }
      return undefined
    })(model.viewOf.get(focusId) ?? model.root)
    const target = sel?.id ?? firstFile
    if (target) open(target)
  }
  const crumbs = viewPath(model, focusId)
  const selected = selectedId ? model.byId.get(selectedId) : undefined
  const hovered = hover ? model.byId.get(hover.id) : undefined
  const g = data.graph
  const stats = g
    ? `파일 ${graph.stats.files.toLocaleString()} · 함수 ${graph.stats.functions.toLocaleString()} · 라우트 ${graph.stats.routes} · 장비 ${graph.infra?.nodes.filter((n) => n.kind !== 'browser' && n.kind !== 'backend').length ?? 0} · 그래프 ${g.commit_hash?.slice(0, 7) ?? '—'}${
        data.files.length === 0 && data.functions.length ? ' · 다음 코드 push에 호출 순서가 생깁니다' : ''
      }`
    : '코드 그래프가 없습니다 — 코드를 push하면 만들어집니다'
  const branchOf = useMemo(() => branches(runtime.items), [runtime.items])
  const selectedFn = selected && FUNCTION_KINDS.has(selected.kind) ? selected : undefined
  const device = selected?.kind === 'infra' ? infra?.nodes.find((d) => d.id === selected.id) : undefined

  return (
    <div className="docscreen fvscreen">
      <div className="docbar" data-el="1">
        <Link className="crumb" to={`/p/${code}`}>
          <ProjName code={code} name={projName} />
        </Link>
        <span className="sep">›</span>
        <b>흐름 보기</b>
        <span className="grow" />
        <span className="lbl" data-el="1.1">
          {stats}
        </span>
      </div>
      <div className="gbar" data-el="2">
        <span className="seg" data-el="2.1">
          <span className={viewMode === 'city' ? 'on' : ''} onClick={() => switchView('city')}>
            도시
          </span>
          <span className={viewMode === 'api' ? 'on' : ''} onClick={() => switchView('api')}>
            API 흐름
          </span>
        </span>
        <span className={`seg${flowData ? ' off' : ''}`} data-el="2.2">
          {(['장비', '폴더', '코드'] as const).map((n) => (
            <span key={n} className={level === n && !flowData ? 'on' : ''} onClick={() => !flowData && goLevel(n)}>
              {n}
            </span>
          ))}
        </span>
        <span className="seg" data-el="2.3">
          {(
            [
              ['base', '기본'],
              ['coverage', '커버리지'],
              ['spec', '명세'],
            ] as Array<[Mode, string]>
          ).map(([v, label]) => (
            <span
              key={v}
              className={`${mode === v ? 'on' : ''}${v === 'coverage' && !runtime.items.length ? ' off' : ''}`}
              onClick={() => (v !== 'coverage' || runtime.items.length) && setMode(v)}
              title={v === 'coverage' && !runtime.items.length ? '기록이 하나 이상 있을 때' : undefined}
            >
              {label}
            </span>
          ))}
        </span>
        <span data-el="2.4">
          <input className="inp" placeholder="함수 · 파일 · 경로" value={q} onChange={(e) => setQ(e.target.value)} />
        </span>
        {!showTree && !flowData && (
          <span
            className="btn sm"
            onClick={() => {
              setShowTree(true)
              writeFlag('syncdoc.flow.tree', true)
            }}
          >
            탐색기
          </span>
        )}
        <span className="grow" />
        <Link className="btn sm" data-el="2.5" to={`/p/${code}/code-graph${selectedFn ? `?focus=${encodeURIComponent(selectedFn.id)}` : ''}`}>
          코드 그래프로
        </Link>
      </div>
      <div className={`fv3${showTree || flowData ? '' : ' notree'}`}>
        {flowData ? (
          <ApiList model={model} selected={flowData.flow.routeId} local={local} runs={(id) => runtime.items.filter((t) => routeMatch(model.byId.get(id)?.route, t)).length} onSelect={(id) => (setTrace(null), setSelectedId(null), setRequestOpen(false), setApiRoute(id))} onRun={runApi} />
        ) : (
          showTree && (
            <Explorer
              model={model}
              focusId={focusId}
              selectedId={selectedId}
              onOpen={open}
              onClose={() => {
                setShowTree(false)
                writeFlag('syncdoc.flow.tree', false)
              }}
            />
          )
        )}
        <div className="fvscene" data-el="4">
          <div ref={stageRef} className="stage" role="img" aria-label="코드 구조 3D. 끌어서 돌리고, 휠로 확대. 판은 폴더, 건물은 파일, 층은 함수." />
          <div ref={labelsRef} className="labels" />
          {!flowData && levelOf === 'file' && (
            <div className="crumbs" data-el="4.5">
              {crumbs.slice(1).map((v, i) => (
                <span key={v.id}>
                  {i > 0 && ' › '}
                  <span className="c" onClick={() => open(v.id)}>
                    {v.label}
                  </span>
                </span>
              ))}
              {selectedFn && <b> › {displayName(selectedFn)}</b>}
            </div>
          )}
          {trip && (
            <div className="trip" data-el="4.6">
              {trip}
            </div>
          )}
          {hovered && hover && (
            <div className="hov" style={{ left: hover.x + 14, top: hover.y + 14 }}>
              <b>{model.viewOf.get(hovered.id)?.id === hovered.id ? model.viewOf.get(hovered.id)!.label : displayName(hovered)}</b>
              <span>
                {hovered.loc ? `${hovered.loc}줄` : ''}
                {hovered.route ? ` · ${hovered.route.method} ${hovered.route.path}` : ''}
              </span>
            </div>
          )}
          <Legend mode={mode} />
        </div>
        <aside className="panel fvside" data-el="5">
          <div className="pbody">
            {notice && (
              <div className="notice" onClick={() => setNotice(null)}>
                {notice}
              </div>
            )}
            {trace ? (
              <TracePanel
                model={model}
                trace={trace}
                options={traceOptions}
                speed={speed}
                follow={follow}
                onPlay={() => {
                  sceneRef.current?.play()
                  setTrace({ ...trace, playing: true })
                }}
                onPause={() => {
                  sceneRef.current?.pause()
                  setTrace({ ...trace, playing: false })
                }}
                onSeek={(i) => {
                  sceneRef.current?.pause()
                  sceneRef.current?.seek(i)
                  setTrace({ ...trace, index: i, playing: false })
                }}
                onSpeed={(s) => {
                  setSpeed(s)
                  sceneRef.current?.setSpeed(s)
                }}
                onFollow={(f) => {
                  setFollow(f)
                  sceneRef.current?.setFollow(f)
                }}
                onOptions={(o) => {
                  setTraceOptions(o)
                  startTrace(trace.rootId, o)
                }}
                onClose={closeTrace}
              />
            ) : flowData && (!selected || selected.id === flowData.flow.routeId) ? (
              <ApiDetail
                code={code}
                model={model}
                arch={arch}
                flow={flowData.flow}
                options={flowOptions}
                local={local}
                requestOpen={requestOpen}
                classDoc={classDoc}
                onOptions={(o) => {
                  setTrace(null)
                  setSelectedId(null)
                  setFlowOptions(o)
                }}
                onSelect={open}
                onTrace={startApiTrace}
              />
            ) : device ? (
              <DevicePanel model={model} device={device} onOpen={open} />
            ) : selected ? (
              <>
                {flowData && (
                  <span className="lnk" onClick={() => select(null)}>
                    ← API 요약으로
                  </span>
                )}
                <Inspector code={code} model={model} arch={arch} node={selected} fn={fnByKey.get(selected.id)} onSelect={open} onTrace={(id) => startTrace(id)} />
              </>
            ) : (
              <Overview
                code={code}
                graph={graph}
                units={data.units}
                traces={runtime.items}
                tracesOk={runtime.ok}
                branchOf={branchOf}
                live={live}
                onLive={setLive}
                onPlay={playRuntime}
                onClear={runtime.clear}
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

function routeMatch(route: { method: string; path: string } | undefined, t: TraceBrief): boolean {
  if (!route || (route.method !== 'ANY' && route.method !== t.method)) return false
  const pattern = route.path
    .split(/\{[^}]*\}/)
    .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('[^/]+')
  return new RegExp(`^${pattern}/?$`).test(t.path)
}

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v === '1'
  } catch {
    return fallback
  }
}
function writeFlag(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch {
    // 저장이 막힌 브라우저 — 이번에만
  }
}

function Legend({ mode }: { mode: Mode }) {
  const items: Array<[string, string]> =
    mode === 'spec'
      ? [
          ['명세와 같음', COLORS.specOk],
          ['호출이 명세와 다름', COLORS.specDiff],
          ['명세 없음', COLORS.dim],
        ]
      : mode === 'coverage'
        ? [
            ['기록에 나온 함수', COLORS.covered],
            ['기록에 없음', COLORS.dim],
          ]
        : [
            ['화면', 'var(--fv-front)'],
            ['엔드포인트', 'var(--fv-endpoint)'],
            ['서비스', 'var(--fv-service)'],
            ['저장소', 'var(--fv-repo)'],
          ]
  return (
    <div className="legend">
      {items.map(([label, color]) => (
        <span key={label}>
          <i style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  )
}
