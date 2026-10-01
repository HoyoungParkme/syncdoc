/** UI-17 코드 그래프 — SYNC-UI-002#UI-17 (카드 BD). 프로젝트의 함수 전부를 커뮤니티로 접은 힘 배치 그림.
 *  1 헤더(1.1 통계) · 2 툴바(2.1 검색, 2.2 전부 펼치기/접기, 2.3 상태 라벨)
 *  3 캔버스 — 그림은 canvas가 그린다. 올리거나 고른 노드 하나와 그 선만 DOM 겹층으로 다시 그린다:
 *    3.1 커뮤니티 노드 · 3.2 함수 노드 · 3.3 호출 선 · 3.4 대조 표시
 *  4 옆 패널(4.1 이름·자리, 4.2 부르는 것, 4.3 불리는 곳, 4.4 코드 탭으로, 4.5 커뮤니티 칩, 4.6 코드) · 5 범례(5.1 커뮤니티 행, 5.2 설명)
 *  6 파일 트리(6.1 폴더·파일 행, 6.2 함수 행, 6.3 접기) — 카드 BF. 그래프 옆에 코드: 함수를 고르면 4.6에 본문이 바로,
 *    커뮤니티면 허브 함수의 본문. 트리는 functions[].file로 브라우저가 만든다 — 요청이 없다
 *  카드 BI — 패널 탭 4.9(함수 | 질문, ?panel=ask) · 7 질문 탭(UI-5 질문 탭과 같은 AskPanel, 맥락은 고른 함수) · 7.1 맥락 줄
 *  카드 BG — 트리는 폴더 한 단씩, 폴더·파일을 고르면 그 아래 함수 노드를 펼쳐 보인다(트리 포커스). 4.7 명세 —
 *    항목·근거(상위 참조)·하위 참조(…/references, 참조 탭과 같은 자료), 항목 없으면 가까운 항목
 *
 *  배치는 브라우저가 한다 — 서버는 노드·선·커뮤니티만 준다(MS-008 code_nodes). 커뮤니티는 서버가 그래프를
 *  만들 때 계산한 것(MS-011 communities). d3-force는 번들 안에 있어 바깥 요청이 없다 — 폐쇄망판도 같다. */
import { ItemIdBadge, ProjName } from '../components/ui'
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type Simulation, type SimulationLinkDatum, type SimulationNodeDatum } from 'd3-force'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useOutletContext, useParams, useSearchParams } from 'react-router-dom'
import { ago, api, ApiError, type CodeNode, type CodeNodes, type CodeText, type ItemRef, type ItemReferences, type Me, type ProjectSummary } from '../api/client'
import { AskPanel } from './DocView'
import type { AskChat } from '../components/Shell'
import { CodeLines } from './codeSrc'
import { ItemPeek, type PeekTarget } from '../components/ItemPeek'

type Sel = { kind: 'c'; id: number } | { kind: 'f'; key: string }
interface GNode extends SimulationNodeDatum {
  id: string
  kind: 'c' | 'f'
  cid: number | null
  r: number
  fn?: CodeNode
  size?: number
  label: string
}
interface GLink extends SimulationLinkDatum<GNode> {
  count: number
}

const PALETTE = 12
const STATUS_MARK: Record<string, string> = { same: '✓', code_only: '▲', spec_only: '◌' }
const STATUS_CLS: Record<string, string> = { same: 'same', code_only: 'code', spec_only: 'spec' }
/** 라벨이 파일 경로 꼴이면 파일 이름만 — 전체는 title로 (UI-17 규칙) */
const short = (label: string) => (label.includes('/') ? label.slice(label.lastIndexOf('/') + 1) : label)
const cNodeId = (cid: number) => `c:${cid}`
const fNodeId = (key: string) => `f:${key}`
/** 6 트리 한 단 — 폴더(한 단씩)와 그 안 파일. 접힌 폴더 안은 그리지 않는다 */
interface TDir {
  name: string
  path: string
  dirs: TDir[]
  files: { file: string; fns: CodeNode[] }[]
}
/** 항목 ID `SYNC-MS-007#pipeline.save_pipeline` → 문서·항목·화면 링크 */
const msParts = (ms: string) => {
  const [doc, item] = ms.split('#')
  return { doc, item, short: ms.split('-').slice(1).join('-'), to: `/p/${doc.split('-')[0]}/d/${doc}#item-${item}` }
}

export function CodeGraph() {
  const { code = '' } = useParams()
  const { user, projects, ask } = useOutletContext<{ user: Me; projects: ProjectSummary[]; ask: AskChat }>()
  const [sp, setSp] = useSearchParams()
  // 4.9 패널 탭 — 질문 탭은 ?panel=ask (UI-5 8.4와 같은 키). 모델 키가 없으면 탭 줄이 없다 (카드 BI)
  const askTab = !!user?.llm_enabled
  const panelTab: 'fn' | 'ask' = askTab && sp.get('panel') === 'ask' ? 'ask' : 'fn'
  const setPanelTab = (tab: 'fn' | 'ask') =>
    setSp(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (tab === 'ask') next.set('panel', 'ask')
        else next.delete('panel')
        return next
      },
      { replace: true },
    )
  const [data, setData] = useState<CodeNodes | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set())
  const [hidden, setHidden] = useState<Set<number>>(() => new Set())
  const [q, setQ] = useState('')
  const [notFound, setNotFound] = useState(false)
  const [sel, setSel] = useState<Sel | null>(null)
  const [hover, setHover] = useState<Sel | null>(null)
  const [dragging, setDragging] = useState(false)
  // 6 파일 트리 · 4.6 코드 (카드 BF)
  const [treeOpen, setTreeOpen] = useState(() => typeof window === 'undefined' || window.innerWidth > 720)
  const [openDirs, setOpenDirs] = useState<Set<string>>(() => new Set())
  const [treeFocus, setTreeFocus] = useState<{ path: string; keys: Set<string>; cids: Set<number> } | null>(null)
  const [src, setSrc] = useState<{ key: string; text?: CodeText; error?: string } | null>(null)
  const srcSeq = useRef(0)
  const [refs, setRefs] = useState<{ key: string; data?: ItemReferences; error?: string } | null>(null) // 4.7 명세 (카드 BG)
  const [peek, setPeek] = useState<PeekTarget | null>(null) // UI-18 항목 미리보기 (카드 BH)
  const refSeq = useRef(0)
  const [, bump] = useState(0) // 틱마다 겹층 자리를 다시 — canvas는 rAF가 직접 그린다
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const simRef = useRef<Simulation<GNode, GLink> | null>(null)
  const nodesRef = useRef<GNode[]>([])
  const linksRef = useRef<GLink[]>([])
  const view = useRef({ x: 0, y: 0, k: 1 })
  const dirty = useRef(true)
  const focusRef = useRef<Sel | null>(null)
  const treeFocusRef = useRef<{ keys: Set<string>; cids: Set<number> } | null>(null)
  const fitted = useRef(false) // 처음 안정될 때 한 번 전체가 보이게 맞춘다
  const colors = useRef<{ cg: string[]; ok: string; code: string; spec: string; edge: string; ink: string }>({ cg: [], ok: '', code: '', spec: '', edge: '', ink: '' })

  useEffect(() => {
    api
      .get<CodeNodes>(`/api/projects/${code}/code-graph`)
      .then(setData)
      .catch((e) => setErr(e instanceof ApiError ? e.message : String(e)))
  }, [code])

  // 색은 토큰에서 한 번 읽는다 — 컴포넌트에 색을 직접 쓰지 않는다 (DEV-17)
  useEffect(() => {
    const cs = getComputedStyle(document.documentElement)
    const v = (n: string) => cs.getPropertyValue(n).trim()
    colors.current = {
      cg: Array.from({ length: PALETTE }, (_, i) => v(`--cg-${i + 1}`)),
      ok: v('--status-approved'),
      code: v('--caution-ink'),
      spec: v('--danger'),
      edge: v('--graph-edge'),
      ink: v('--ink-body'),
    }
  }, [])

  const grouped = !!data && data.communities.length > 0 // 5a — 옛 그래프면 커뮤니티 없이 전부 펼친다
  const byKey = useMemo(() => new Map((data?.functions ?? []).map((f) => [f.key, f])), [data])
  const commOf = useMemo(() => new Map((data?.communities ?? []).map((c) => [c.id, c])), [data])
  const degree = useMemo(() => {
    const d = new Map<string, number>()
    for (const [a, b] of data?.calls ?? []) {
      d.set(a, (d.get(a) ?? 0) + 1)
      d.set(b, (d.get(b) ?? 0) + 1)
    }
    return d
  }, [data])

  /** 6 파일 트리 — 폴더 한 단씩 › 파일 › 함수(줄 순). 함수가 있는 파일만, 이름순. 자식 하나뿐인 폴더도 묶지 않는다 (카드 BG) */
  const tree = useMemo(() => {
    const root: TDir = { name: '', path: '', dirs: [], files: [] }
    const byFile = new Map<string, CodeNode[]>()
    for (const f of data?.functions ?? []) byFile.set(f.file, [...(byFile.get(f.file) ?? []), f])
    for (const [file, fns] of byFile) {
      const parts = file.split('/')
      let d = root
      for (const seg of parts.slice(0, -1)) {
        let next = d.dirs.find((x) => x.name === seg)
        if (!next) {
          next = { name: seg, path: d.path ? `${d.path}/${seg}` : seg, dirs: [], files: [] }
          d.dirs.push(next)
        }
        d = next
      }
      d.files.push({ file, fns: fns.sort((a, b) => a.line - b.line) })
    }
    const sortDir = (d: TDir) => {
      d.dirs.sort((a, b) => a.name.localeCompare(b.name)).forEach(sortDir)
      d.files.sort((a, b) => a.file.localeCompare(b.file))
    }
    sortDir(root)
    return root
  }, [data])
  /** 파일의 조상 폴더 전부 + 파일 — pick·?focus가 트리를 연다 */
  const ancestors = (file: string) => {
    const parts = file.split('/')
    return parts.map((_, i) => parts.slice(0, i + 1).join('/'))
  }

  /** 표시 그래프 — 접힌 커뮤니티는 큰 원 하나, 펼친 커뮤니티는 함수들. 선은 양 끝을 표시 노드로 접어 센다 */
  const shown = useMemo(() => {
    if (!data) return { nodes: [] as GNode[], links: [] as GLink[] }
    const nodes: GNode[] = []
    const nodeOf = new Map<string, string>() // 함수 key → 표시 노드 id
    for (const c of data.communities) {
      if (hidden.has(c.id)) continue
      if (!expanded.has(c.id)) nodes.push({ id: cNodeId(c.id), kind: 'c', cid: c.id, r: 8 + 2.2 * Math.sqrt(c.size), size: c.size, label: c.label })
    }
    for (const f of data.functions) {
      const cid = grouped ? f.community : null
      if (cid !== null && cid !== undefined) {
        if (hidden.has(cid)) continue
        if (!expanded.has(cid)) {
          nodeOf.set(f.key, cNodeId(cid))
          continue
        }
      }
      nodes.push({ id: fNodeId(f.key), kind: 'f', cid, r: f.ms ? 6 : 4, fn: f, label: f.qual })
      nodeOf.set(f.key, fNodeId(f.key))
    }
    const counts = new Map<string, number>()
    for (const [a, b] of data.calls) {
      const s = nodeOf.get(a)
      const t = nodeOf.get(b)
      if (!s || !t || s === t) continue
      const k = `${s}\u0000${t}`
      counts.set(k, (counts.get(k) ?? 0) + 1)
    }
    const links: GLink[] = [...counts].map(([k, count]) => {
      const [source, target] = k.split('\u0000')
      return { source, target, count }
    })
    return { nodes, links }
  }, [data, expanded, hidden, grouped])

  // 시뮬레이션 — 표시 그래프가 바뀌면 옛 노드 객체는 자리를 지키고, 새 함수 노드는 제 커뮤니티 자리에서 시작한다
  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    const W = box.clientWidth || 900
    const H = box.clientHeight || 560
    const old = new Map(nodesRef.current.map((n) => [n.id, n]))
    const nodes = shown.nodes.map((n) => {
      const prev = old.get(n.id)
      if (prev) return Object.assign(prev, { r: n.r, size: n.size, label: n.label, fn: n.fn, cid: n.cid })
      let x = W / 2 + (Math.random() - 0.5) * 80
      let y = H / 2 + (Math.random() - 0.5) * 80
      const home = n.cid !== null ? old.get(cNodeId(n.cid)) : undefined
      if (home && home.x !== undefined && home.y !== undefined) {
        x = home.x + (Math.random() - 0.5) * 60
        y = home.y + (Math.random() - 0.5) * 60
      } else if (n.kind === 'c') {
        // 접을 때 — 그 안 함수들의 가운데에서
        const members = nodesRef.current.filter((m) => m.kind === 'f' && m.cid === n.cid && m.x !== undefined)
        if (members.length) {
          x = members.reduce((s, m) => s + (m.x ?? 0), 0) / members.length
          y = members.reduce((s, m) => s + (m.y ?? 0), 0) / members.length
        }
      }
      return { ...n, x, y }
    })
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const links: GLink[] = shown.links
      .map((l) => ({ source: byId.get(l.source as string)!, target: byId.get(l.target as string)!, count: l.count }))
      .filter((l) => l.source && l.target)
    nodesRef.current = nodes
    linksRef.current = links
    const sim =
      simRef.current ??
      forceSimulation<GNode, GLink>()
        .force('charge', forceManyBody<GNode>().strength((d) => (d.kind === 'c' ? -220 : -30)))
        .force('collide', forceCollide<GNode>().radius((d) => d.r + 3))
        .force('center', forceCenter(W / 2, H / 2).strength(0.05))
        .force('x', forceX<GNode>(W / 2).strength(0.03))
        .force('y', forceY<GNode>(H / 2).strength(0.03))
        .on('tick', () => {
          dirty.current = true
          bump((t) => t + 1)
          if (!fitted.current && (simRef.current?.alpha() ?? 1) < 0.08) {
            fitted.current = true
            fitAll()
          }
        })
    simRef.current = sim
    sim.nodes(nodes)
    sim.force(
      'link',
      forceLink<GNode, GLink>(links)
        .id((d) => d.id)
        .distance((l) => ((l.source as GNode).kind === 'c' && (l.target as GNode).kind === 'c' ? 140 : 32))
        .strength(0.5),
    )
    sim.alpha(0.6).restart()
    dirty.current = true
  }, [shown])

  useEffect(
    () => () => {
      simRef.current?.stop()
    },
    [],
  )

  // 그리기 — rAF 한 곳. 선 → 노드 → 라벨. 포커스가 있으면 이웃이 아닌 것은 흐린다 (UI-8과 같은 문법)
  const focus = hover ?? sel
  focusRef.current = focus
  useEffect(() => {
    let raf = 0
    const draw = () => {
      raf = requestAnimationFrame(draw)
      const canvas = canvasRef.current
      const box = boxRef.current
      if (!canvas || !box || !dirty.current) return
      dirty.current = false
      const dpr = window.devicePixelRatio || 1
      const W = box.clientWidth
      const H = box.clientHeight
      if (canvas.width !== W * dpr || canvas.height !== H * dpr) {
        canvas.width = W * dpr
        canvas.height = H * dpr
      }
      const ctx = canvas.getContext('2d')!
      const { x, y, k } = view.current
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * x, dpr * y)
      const col = colors.current
      const fid = focusRef.current ? (focusRef.current.kind === 'c' ? cNodeId(focusRef.current.id) : fNodeId(focusRef.current.key)) : null
      const near = new Set<string>()
      if (fid) {
        near.add(fid)
        for (const l of linksRef.current) {
          const s = (l.source as GNode).id
          const t = (l.target as GNode).id
          if (s === fid) near.add(t)
          if (t === fid) near.add(s)
        }
      }
      ctx.strokeStyle = col.edge
      ctx.lineCap = 'round'
      // 트리 포커스(6.1) — 선과 노드 둘 다 보므로 루프 앞에서 읽는다 (#260)
      const ff = treeFocusRef.current
      const litNode = (n: GNode) => (ff === null ? true : n.kind === 'f' ? ff.keys.has(n.fn!.key) : ff.cids.has(n.cid!))
      for (const l of linksRef.current) {
        const s = l.source as GNode
        const t = l.target as GNode
        const lit = fid ? s.id === fid || t.id === fid : litNode(s) && litNode(t)
        ctx.globalAlpha = lit ? 0.35 : 0.06
        ctx.lineWidth = (0.6 + Math.log2(l.count)) / k
        ctx.beginPath()
        ctx.moveTo(s.x!, s.y!)
        ctx.lineTo(t.x!, t.y!)
        ctx.stroke()
      }
      for (const n of nodesRef.current) {
        // 포커스 노드가 있으면 그 이웃만, 없고 트리(6.1)에서 골랐으면 그 아래 함수(와 그 함수가 든 커뮤니티)만 밝다
        const dim = fid !== null ? !near.has(n.id) : !litNode(n)
        ctx.globalAlpha = dim ? 0.15 : n.kind === 'c' ? 0.85 : 0.9
        ctx.fillStyle = n.cid === null ? col.edge : col.cg[n.cid % PALETTE]
        ctx.beginPath()
        ctx.arc(n.x!, n.y!, n.r, 0, Math.PI * 2)
        ctx.fill()
        if (n.fn?.status) {
          // 3.4 — MINISPEC 함수의 고리. 색은 코드 탭과 같은 상태 색
          ctx.strokeStyle = n.fn.status === 'same' ? col.ok : n.fn.status === 'code_only' ? col.code : col.spec
          ctx.lineWidth = 2.2 / k
          ctx.stroke()
          ctx.strokeStyle = col.edge
        }
        if (n.kind === 'c' && n.r * k >= 12) {
          ctx.fillStyle = '#fff'
          ctx.font = `600 ${11 / k}px ${getComputedStyle(document.documentElement).getPropertyValue('--font-mono')}`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(short(n.label), n.x!, n.y!, n.r * 1.9)
        } else if (n.kind === 'f' && k >= 1.8 && !dim) {
          ctx.fillStyle = col.ink
          ctx.font = `${10 / k}px ${getComputedStyle(document.documentElement).getPropertyValue('--font-mono')}`
          ctx.textAlign = 'left'
          ctx.textBaseline = 'middle'
          ctx.fillText(n.fn!.name, n.x! + n.r + 2 / k, n.y!)
        }
      }
      ctx.globalAlpha = 1
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [])
  useEffect(() => {
    dirty.current = true
  }, [focus])
  useEffect(() => {
    treeFocusRef.current = treeFocus ? { keys: treeFocus.keys, cids: treeFocus.cids } : null
    dirty.current = true
    bump((t) => t + 1)
  }, [treeFocus])

  // 좌표 — 화면 → 세계
  const toWorld = (sx: number, sy: number) => {
    const { x, y, k } = view.current
    return [(sx - x) / k, (sy - y) / k] as const
  }
  const findNode = (sx: number, sy: number): GNode | undefined => {
    const [wx, wy] = toWorld(sx, sy)
    return simRef.current?.find(wx, wy, 24 / view.current.k)
  }
  /** 노드들이 보이게 — 그 상자에 맞춰 줌·이동. 처음 한 번은 전부, 트리 포커스는 그 노드들 */
  const fitNodes = (ns: GNode[]) => {
    const box = boxRef.current
    ns = ns.filter((n) => n.x !== undefined)
    if (!box || !ns.length) return
    const xs = ns.map((n) => n.x!)
    const ys = ns.map((n) => n.y!)
    const pad = 40
    const bw = Math.max(1, Math.max(...xs) - Math.min(...xs) + pad * 2)
    const bh = Math.max(1, Math.max(...ys) - Math.min(...ys) + pad * 2)
    const k = Math.min(1.5, box.clientWidth / bw, box.clientHeight / bh)
    view.current = { x: box.clientWidth / 2 - ((Math.min(...xs) + Math.max(...xs)) / 2) * k, y: box.clientHeight / 2 - ((Math.min(...ys) + Math.max(...ys)) / 2) * k, k }
    dirty.current = true
    bump((t) => t + 1)
  }
  const fitAll = () => fitNodes(nodesRef.current)
  const centerOn = useCallback((n: GNode) => {
    const box = boxRef.current
    if (!box || n.x === undefined || n.y === undefined) return
    const { k } = view.current
    view.current = { x: box.clientWidth / 2 - n.x * k, y: box.clientHeight / 2 - n.y * k, k }
    dirty.current = true
    bump((t) => t + 1)
  }, [])

  // 함수 하나를 고른다 — 커뮤니티를 펼치고 가운데로 (검색·?focus·패널 줄이 같은 길)
  const pick = useCallback(
    (f: CodeNode) => {
      if (grouped && f.community !== null && !expanded.has(f.community)) {
        setExpanded((s) => new Set(s).add(f.community!))
        if (hidden.has(f.community)) setHidden((s) => {
          const n = new Set(s)
          n.delete(f.community!)
          return n
        })
      }
      setSel({ kind: 'f', key: f.key })
      setOpenDirs((s) => new Set([...s, ...ancestors(f.file)])) // 트리(6)의 조상 폴더 전부와 파일을 연다
      // 노드는 다음 틱에 생긴다 — 자리가 잡힌 뒤 가운데로
      window.setTimeout(() => {
        const n = nodesRef.current.find((m) => m.id === fNodeId(f.key))
        if (n) centerOn(n)
      }, 60)
    },
    [grouped, expanded, hidden, centerOn],
  )

  // ?focus=파일:줄 (8.23) — 한 번
  const focused = useRef(false)
  useEffect(() => {
    const key = sp.get('focus')
    if (!data || !key || focused.current) return
    focused.current = true
    const f = byKey.get(key)
    if (f) pick(f)
    else setNotFound(true)
  }, [data, sp, byKey, pick])

  // 2.1 검색 — 이름·Class.fn·파일 부분 일치. 맞는 첫 함수로
  useEffect(() => {
    if (!data) return
    const t = window.setTimeout(() => {
      const needle = q.trim().toLowerCase()
      if (!needle) {
        setNotFound(false)
        return
      }
      const hit = data.functions.find((f) => f.qual.toLowerCase().includes(needle) || f.name.toLowerCase().includes(needle) || f.file.toLowerCase().includes(needle))
      setNotFound(!hit)
      if (hit) pick(hit)
    }, 300)
    return () => window.clearTimeout(t)
  }, [q, data, pick])

  // 포인터 — 노드를 끌면 그 노드, 빈 곳을 끌면 이동, 휠은 커서 기준 줌, 클릭은 펼치기·선택
  const drag = useRef<{ node: GNode | null; sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null)
  const onDown = (e: React.PointerEvent) => {
    const rect = boxRef.current!.getBoundingClientRect()
    const sx = e.clientX - rect.left
    const sy = e.clientY - rect.top
    const n = findNode(sx, sy)
    drag.current = { node: n ?? null, sx, sy, ox: view.current.x, oy: view.current.y, moved: false }
    if (n) {
      n.fx = n.x
      n.fy = n.y
      simRef.current?.alphaTarget(0.3).restart()
    }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    setDragging(true)
  }
  const onMove = (e: React.PointerEvent) => {
    const rect = boxRef.current!.getBoundingClientRect()
    const sx = e.clientX - rect.left
    const sy = e.clientY - rect.top
    const d = drag.current
    if (d) {
      if (Math.abs(sx - d.sx) + Math.abs(sy - d.sy) > 3) d.moved = true
      if (d.node) {
        const [wx, wy] = toWorld(sx, sy)
        d.node.fx = wx
        d.node.fy = wy
      } else {
        view.current = { ...view.current, x: d.ox + (sx - d.sx), y: d.oy + (sy - d.sy) }
        dirty.current = true
        bump((t) => t + 1)
      }
      return
    }
    const n = findNode(sx, sy)
    const next: Sel | null = n ? (n.kind === 'c' ? { kind: 'c', id: n.cid! } : { kind: 'f', key: n.fn!.key }) : null
    setHover((h) => (h?.kind === next?.kind && (h?.kind === 'c' ? h.id === (next as { id: number }).id : (h as { key: string } | null)?.key === (next as { key: string } | null)?.key) ? h : next))
  }
  const onUp = () => {
    const d = drag.current
    drag.current = null
    setDragging(false)
    if (!d) return
    if (d.node) {
      d.node.fx = null
      d.node.fy = null
      simRef.current?.alphaTarget(0)
      if (!d.moved) {
        if (d.node.kind === 'c') setExpanded((s) => new Set(s).add(d.node!.cid!))
        else setSel((cur) => (cur?.kind === 'f' && cur.key === d.node!.fn!.key ? null : { kind: 'f', key: d.node!.fn!.key }))
      }
    } else if (!d.moved) setSel(null)
  }
  const onWheel = (e: React.WheelEvent) => {
    const rect = boxRef.current!.getBoundingClientRect()
    const sx = e.clientX - rect.left
    const sy = e.clientY - rect.top
    const { x, y, k } = view.current
    const nk = Math.min(6, Math.max(0.2, k * Math.exp(-e.deltaY * 0.0015)))
    view.current = { x: sx - ((sx - x) * nk) / k, y: sy - ((sy - y) * nk) / k, k: nk }
    dirty.current = true
    bump((t) => t + 1)
  }

  const allOpen = grouped && data!.communities.every((c) => expanded.has(c.id))
  const toggleAll = () => setExpanded(allOpen ? new Set() : new Set((data?.communities ?? []).map((c) => c.id)))
  const toggleHidden = (cid: number) =>
    setHidden((s) => {
      const n = new Set(s)
      if (n.has(cid)) n.delete(cid)
      else n.add(cid)
      return n
    })
  const collapse = (cid: number) => {
    setExpanded((s) => {
      const n = new Set(s)
      n.delete(cid)
      return n
    })
    setSel({ kind: 'c', id: cid })
  }

  // 겹층(3.1~3.4) — 포커스 노드의 화면 자리
  const focusNode = focus ? nodesRef.current.find((n) => n.id === (focus.kind === 'c' ? cNodeId(focus.id) : fNodeId(focus.key))) : undefined
  const toScreen = (n: GNode) => {
    const { x, y, k } = view.current
    return { left: (n.x ?? 0) * k + x, top: (n.y ?? 0) * k + y - n.r * k }
  }
  const focusLinks = focusNode ? linksRef.current.filter((l) => l.source === focusNode || l.target === focusNode) : []

  // 패널(4) — 고른 것
  const selFn = sel?.kind === 'f' ? byKey.get(sel.key) : undefined
  const selComm = sel?.kind === 'c' ? commOf.get(sel.id) : undefined
  const callsOf = (key: string) => (data?.calls ?? []).filter(([a]) => a === key).map(([, b]) => byKey.get(b)).filter((f): f is CodeNode => !!f)
  const callersOf = (key: string) => (data?.calls ?? []).filter(([, b]) => b === key).map(([a]) => byKey.get(a)).filter((f): f is CodeNode => !!f)
  const allMembers = selComm ? data!.functions.filter((f) => f.community === selComm.id).sort((a, b) => (degree.get(b.key) ?? 0) - (degree.get(a.key) ?? 0)) : []
  const members = allMembers.slice(0, 20)
  // 4.6 코드 — 함수를 골랐으면 그 함수, 커뮤니티면 허브 함수(라벨과 이름이 같은 것, 없으면 호출 많은 첫 함수)
  const codeTarget = selFn ?? (selComm ? (allMembers.find((f) => f.qual === selComm.label || f.name === selComm.label) ?? allMembers[0]) : undefined)
  const codeKey = codeTarget?.key
  useEffect(() => {
    if (!codeKey || !codeTarget) {
      setSrc(null)
      return
    }
    const seq = ++srcSeq.current // 앞 요청이 남아 있으면 그 답은 버린다
    setSrc({ key: codeKey })
    api
      .get<CodeText>(`/api/projects/${code}/code/source?file=${encodeURIComponent(codeTarget.file)}&line=${codeTarget.line}`)
      .then((text) => seq === srcSeq.current && setSrc({ key: codeKey, text }))
      .catch((e) => seq === srcSeq.current && setSrc({ key: codeKey, error: e instanceof ApiError ? e.message : String(e) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeKey, code])
  // 4.7 명세 — 항목이 있으면 그 항목의 참조를 한 번 (참조 탭 8.1과 같은 자료). 늦은 답은 버린다
  useEffect(() => {
    if (!codeKey || !codeTarget?.ms) {
      setRefs(null)
      return
    }
    const seq = ++refSeq.current
    const { doc, item } = msParts(codeTarget.ms)
    setRefs({ key: codeKey })
    api
      .get<ItemReferences>(`/api/docs/${doc}/items/${item.replace(/\//g, '~')}/references`)
      .then((d) => seq === refSeq.current && setRefs({ key: codeKey, data: d }))
      .catch((e) => seq === refSeq.current && setRefs({ key: codeKey, error: e instanceof ApiError ? e.message : String(e) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeKey])
  // 6.1 폴더·파일 행 — ▸는 펼침·접힘, 이름은 트리 포커스(그 아래 함수의 커뮤니티를 펼치고 그 노드만 밝게, 화면을 맞춘다)
  const toggleDir = (key: string) =>
    setOpenDirs((s) => {
      const n = new Set(s)
      if (n.has(key)) n.delete(key)
      else n.add(key)
      return n
    })
  const focusTree = (path: string, isFile: boolean) => {
    if (treeFocus?.path === path) {
      setTreeFocus(null)
      return
    }
    const fns = (data?.functions ?? []).filter((f) => (isFile ? f.file === path : f.file.startsWith(path + '/')))
    const keys = new Set(fns.map((f) => f.key))
    const cids = new Set(fns.filter((f) => f.community !== null).map((f) => f.community!))
    setTreeFocus({ path, keys, cids })
    setOpenDirs((s) => new Set(s).add(path))
    if (grouped && cids.size) {
      setExpanded((s) => new Set([...s, ...cids]))
      setHidden((s) => {
        const n = new Set(s)
        cids.forEach((c) => n.delete(c))
        return n
      })
    }
    // 노드는 다음 틱에 생긴다 — 자리가 잡힌 뒤 그 노드들에 맞춘다
    window.setTimeout(() => fitNodes(nodesRef.current.filter((n) => n.kind === 'f' && keys.has(n.fn!.key))), 120)
  }
  /** 6 트리 한 단 그리기 — 접힌 폴더 안은 그리지 않는다. data-el은 첫 폴더 행(6.1)·첫 함수 행(6.2)에만 */
  const marks = { dir: false, fn: false }
  const renderDir = (d: TDir, depth: number): React.ReactNode => (
    <div key={d.path || '/'}>
      {d.dirs.map((c) => {
        const first = !marks.dir
        marks.dir = true
        const open = openDirs.has(c.path)
        return (
          <div key={c.path}>
            <div className={`tr d${treeFocus?.path === c.path ? ' on' : ''}`} style={{ paddingLeft: 10 + 14 * depth }} data-el={first ? '6.1' : undefined} title={c.path} onClick={() => focusTree(c.path, false)}>
              <span className="tw" onClick={(e) => (e.stopPropagation(), toggleDir(c.path))}>
                {open ? '▾' : '▸'}
              </span>
              {c.name}
            </div>
            {open && renderDir(c, depth + 1)}
          </div>
        )
      })}
      {d.files.map(({ file, fns }) => {
        const open = openDirs.has(file)
        return (
          <div key={file}>
            <div className={`tr f${treeFocus?.path === file ? ' on' : ''}`} style={{ paddingLeft: 10 + 14 * depth }} title={file} onClick={() => focusTree(file, true)}>
              <span className="tw" onClick={(e) => (e.stopPropagation(), toggleDir(file))}>
                {open ? '▾' : '▸'}
              </span>
              {short(file)}
            </div>
            {open &&
              fns.map((f) => {
                const first = !marks.fn
                marks.fn = true
                return (
                  <div className={`tr fn${selFn?.key === f.key ? ' on' : ''}`} key={f.key} style={{ paddingLeft: 10 + 14 * (depth + 1) }} data-el={first ? '6.2' : undefined} onClick={() => pick(f)} title={`${f.qual} · ${f.file}:${f.line}`}>
                    <span className={`ring${f.status ? ` ${STATUS_CLS[f.status]}` : ''}`} />
                    {f.name}
                  </div>
                )
              })}
          </div>
        )
      })}
    </div>
  )
  /** 4.7 명세 — 항목 뱃지 · 근거(상위) · 이것을 가리킴(하위). 항목 없으면 가까운 항목 */
  const refRow = (r: ItemRef, first = false) =>
    r.is_missing ? (
      <div className="sr missing" key={r.raw_target} data-el={first ? '4.8' : undefined} title="가리키는 곳 없음 — 항목이 삭제됐거나 아직 안 쓰였다">
        <ItemIdBadge>{r.raw_target.split('-').slice(1).join('-')}</ItemIdBadge> 가리키는 곳 없음
      </div>
    ) : (
      <div className="sr" key={`${r.doc_id}#${r.item_id}`} data-el={first ? '4.8' : undefined} onClick={() => setPeek({ doc_id: r.doc_id!, item_id: r.item_id })} title="항목 미리보기 (UI-18)">
        <ItemIdBadge>{`${r.doc_id}${r.item_id ? '#' + r.item_id : ''}`.split('-').slice(1).join('-')}</ItemIdBadge>
        <span className="nm2">{r.item_id ? r.display_name : `(문서 전체) ${r.display_name ?? ''}`}</span>
      </div>
    )
  const specBlock = (f: CodeNode) => {
    const LIMIT = 8
    if (!f.ms) {
      const near = [...callsOf(f.key), ...callersOf(f.key)].filter((x) => x.ms)
      const seen = new Set<string>()
      const items = near.filter((x) => (seen.has(x.ms!) ? false : (seen.add(x.ms!), true))).sort((a, b) => (degree.get(b.key) ?? 0) - (degree.get(a.key) ?? 0)).slice(0, 6)
      return (
        <div className="spec" data-el="4.7">
          <div className="k">명세</div>
          <div className="it lbl">항목 없음{items.length ? ' · 가까운 항목' : ''}</div>
          {items.map((x, i) => {
            const m = msParts(x.ms!)
            return (
              <div className="sr" key={x.ms} data-el={i === 0 ? '4.8' : undefined} onClick={() => setPeek({ doc_id: m.doc, item_id: m.item })} title={`${x.ms!} — 항목 미리보기 (UI-18)`}>
                <ItemIdBadge>{m.short}</ItemIdBadge>
                <span className="nm2">{x.qual}</span>
              </div>
            )
          })}
        </div>
      )
    }
    const m = msParts(f.ms)
    const d = refs?.data
    const up = d?.upstream ?? []
    const down = d?.downstream ?? []
    return (
      <div className="spec" data-el="4.7">
        <div className="k">명세</div>
        <div className="it">
          <ItemIdBadge>{m.short}</ItemIdBadge>
        </div>
        {refs?.error ? (
          <div className="lbl">참조를 읽을 수 없습니다 — {refs.error}</div>
        ) : !d ? (
          <div className="lbl">불러오는 중…</div>
        ) : (
          <>
            <div className="sk">근거 {up.length || ''}</div>
            {up.length ? up.slice(0, LIMIT).map((r, i) => refRow(r, i === 0)) : <div className="lbl">없음</div>}
            {up.length > LIMIT && <div className="lbl">… {up.length - LIMIT}개 더 — 코드 탭에서</div>}
            <div className="sk">이것을 가리킴 {down.length || ''}</div>
            {down.length ? down.slice(0, LIMIT).map((r) => refRow(r)) : <div className="lbl">없음</div>}
            {down.length > LIMIT && <div className="lbl">… {down.length - LIMIT}개 더 — 코드 탭에서</div>}
          </>
        )}
      </div>
    )
  }
  const codeBlock = (f: CodeNode) => (
    <div className="csrc" data-el="4.6">
      <div className="ch">
        {src?.text ? `코드 L${src.text.start}–L${src.text.end}` : `코드 L${f.line}`}
        {src?.text && <span className="lbl">{src.text.commit_hash.slice(0, 7)}</span>}
        {selComm && <span className="lbl">허브 {f.qual}</span>}
      </div>
      {src?.error ? <div className="lbl">코드를 읽을 수 없습니다 — {src.error}</div> : !src?.text ? <div className="lbl">불러오는 중…</div> : <CodeLines src={src.text} />}
    </div>
  )

  const g = data?.graph
  const stats = data
    ? g
      ? `함수 ${data.functions.length.toLocaleString()} · 호출 ${data.calls.length.toLocaleString()} · 커뮤니티 ${data.communities.length} · 그래프 ${g.commit_hash ? g.commit_hash.slice(0, 7) : '—'} · ${g.source === 'repo' ? '저장소' : '서버'} · ${ago(g.built_at)}${g.error ? ` · 마지막 만들기 실패 — ${g.error}` : ''}`
      : '코드 그래프 없음'
    : ''
  const status = !data
    ? err ?? '불러오는 중…'
    : !g
      ? '코드 그래프 없음 — 코드를 push하면 만들어집니다'
      : notFound
        ? '없음 — 그 이름의 함수가 없습니다'
        : !grouped
          ? '커뮤니티 없음 — 다음 코드 push에 생깁니다'
          : '커뮤니티를 누르면 펼쳐집니다 · 함수를 누르면 옆에 보입니다 · 끌어 옮기고 휠로 확대'
  const projName = projects.find((p) => p.code === code)?.name
  const row = (f: CodeNode) => (
    <div className="crow" key={f.key} onClick={() => pick(f)} title={`${f.file}:${f.line}`}>
      <span className={`st ${f.status ? STATUS_CLS[f.status] : ''}`}>{f.status ? STATUS_MARK[f.status] : ''}</span>
      {f.qual}
    </div>
  )

  return (
    <div className="page cgpage">
      <div className="phead" data-el="1">
        <div>
          <div className="crumbs">
            <Link to={`/p/${code}`}>
              <ProjName code={code} name={projName} />
            </Link>
            <span className="sep">›</span>
            <span>코드 그래프</span>
          </div>
          <b>코드 그래프</b>
        </div>
        <span className="grow" />
        <span className="lbl" data-el="1.1">
          {stats}
        </span>
      </div>
      <div className="gcard">
        <div className="gbar" data-el="2">
          <span data-el="2.1">
            <input className="inp" placeholder="함수 이름 · 파일" value={q} onChange={(e) => setQ(e.target.value)} />
          </span>
          <span className="btn sm" data-el="2.2" onClick={toggleAll}>
            {allOpen ? '전부 접기' : '전부 펼치기'}
          </span>
          {!treeOpen && (
            <span className="btn sm" onClick={() => setTreeOpen(true)}>
              트리
            </span>
          )}
          <span className="sep" />
          <span className="lbl" data-el="2.3">
            {status}
          </span>
          <span className="grow" />
        </div>
        <div className={`cgbody${treeOpen ? '' : ' notree'}`}>
          {treeOpen && (
            <aside className="cgtree" data-el="6">
              <div className="th">
                파일
                <span className="btn sm" data-el="6.3" onClick={() => setTreeOpen(false)}>
                  접기
                </span>
              </div>
              {renderDir(tree, 0)}
            </aside>
          )}
          <div className={`cgcanvas${dragging ? ' drag' : ''}`} data-el="3" ref={boxRef} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} onWheel={onWheel}>
            <canvas ref={canvasRef} />
            {focusNode && (
              <>
                {/* 3.3 — 고른 노드의 선만 DOM으로 다시 */}
                <svg className="cgo" data-el="3.3">
                  {focusLinks.map((l, i) => {
                    const s = l.source as GNode
                    const t = l.target as GNode
                    const { x, y, k } = view.current
                    return <line key={i} x1={(s.x ?? 0) * k + x} y1={(s.y ?? 0) * k + y} x2={(t.x ?? 0) * k + x} y2={(t.y ?? 0) * k + y} strokeWidth={Math.min(6, 0.8 + Math.log2(l.count) * 1.5)} />
                  })}
                </svg>
                {focusNode.kind === 'c' ? (
                  <div className="cgn c" data-el="3.1" style={toScreen(focusNode)} title={focusNode.label}>
                    {short(focusNode.label)}
                    <span className="sub">함수 {focusNode.size} · 펼치기</span>
                  </div>
                ) : (
                  <div className="cgn f" data-el="3.2" style={toScreen(focusNode)}>
                    {focusNode.fn!.qual}
                    {focusNode.fn!.status && (
                      <span className={`mark ${STATUS_CLS[focusNode.fn!.status]}`} data-el="3.4">
                        {STATUS_MARK[focusNode.fn!.status]}
                      </span>
                    )}
                    <span className="sub">
                      {focusNode.fn!.file}:{focusNode.fn!.line}
                    </span>
                  </div>
                )}
              </>
            )}
          </div>
          <aside className={`cgside${panelTab === 'ask' ? ' ask' : ''}`} data-el="4">
            {askTab && (
              <div className="ptabs" data-el="4.9">
                <span className={panelTab === 'fn' ? 'on' : ''} onClick={() => setPanelTab('fn')}>
                  함수
                </span>
                <span className={panelTab === 'ask' ? 'on' : ''} onClick={() => setPanelTab('ask')}>
                  질문
                </span>
              </div>
            )}
            {panelTab === 'ask' ? (
              // 7 질문 탭 — UI-5 질문 탭과 같은 패널. 맥락(7.1)은 고른 함수(커뮤니티면 허브 함수), 없으면 그래프 전체
              <div className="pbody ask" data-el="7">
                <AskPanel ask={ask} elContext="7.1" context={{ kind: 'code', key: codeTarget?.key ?? null, label: codeTarget?.qual ?? '' }} />
              </div>
            ) : selFn ? (
              <>
                <div data-el="4.1">
                  <div className="nm">{selFn.qual}</div>
                  <div className="meta">
                    {selFn.file}:{selFn.line}
                  </div>
                  {selFn.community !== null && commOf.has(selFn.community) && (
                    <span className="chip" data-el="4.5" onClick={() => collapse(selFn.community!)} title={commOf.get(selFn.community)!.label}>
                      <i style={{ background: `var(--cg-${(selFn.community % PALETTE) + 1})` }} />
                      {short(commOf.get(selFn.community)!.label)} · 함수 {commOf.get(selFn.community)!.size} · 접기
                    </span>
                  )}
                </div>
                {codeBlock(selFn)}
                {specBlock(selFn)}
                <div className="k">부르는 것 {callsOf(selFn.key).length}</div>
                <div data-el="4.2">{callsOf(selFn.key).map(row)}</div>
                <div className="k">불리는 곳 {callersOf(selFn.key).length}</div>
                <div data-el="4.3">{callersOf(selFn.key).map(row)}</div>
                {selFn.ms && (
                  <Link className="lnk" data-el="4.4" to={`/p/${selFn.ms.split('-')[0]}/d/${selFn.ms.split('#')[0]}?panel=code#item-${selFn.ms.split('#')[1]}`}>
                    코드 탭으로 → {selFn.ms.split('-').slice(1).join('-')}
                  </Link>
                )}
              </>
            ) : selComm ? (
              <>
                <div data-el="4.1">
                  <div className="nm" title={selComm.label}>
                    {short(selComm.label)}
                  </div>
                  <div className="meta">커뮤니티 · 함수 {selComm.size}</div>
                  <span className="chip" data-el="4.5" onClick={() => (expanded.has(selComm.id) ? collapse(selComm.id) : setExpanded((s) => new Set(s).add(selComm.id)))}>
                    <i style={{ background: `var(--cg-${(selComm.id % PALETTE) + 1})` }} />
                    {expanded.has(selComm.id) ? '접기' : '펼치기'}
                  </span>
                </div>
                {codeTarget && codeBlock(codeTarget)}
                {codeTarget && specBlock(codeTarget)}
                <div className="k">든 함수 — 호출 많은 순 {Math.min(20, members.length)}</div>
                <div data-el="4.2">{members.map(row)}</div>
              </>
            ) : (
              <div className="empty">노드를 고르면 여기에 보입니다 — 함수는 코드와 부르는 것·불리는 곳, 커뮤니티는 허브 함수의 코드와 든 함수.</div>
            )}
          </aside>
        </div>
        <div className="cglegend" data-el="5">
          {(data?.communities ?? []).map((c, i) => (
            <label className={`row${hidden.has(c.id) ? ' off' : ''}`} key={c.id} data-el={i === 0 ? '5.1' : undefined} title={c.label}>
              <input type="checkbox" checked={!hidden.has(c.id)} onChange={() => toggleHidden(c.id)} />
              <i style={{ background: `var(--cg-${(c.id % PALETTE) + 1})` }} />
              {short(c.label)} · {c.size}
            </label>
          ))}
          <span className="grow" />
          <span data-el="5.2">큰 원 = 커뮤니티(크기 = 함수 수) · 선 굵기 = 호출 수 · 고리 = MINISPEC 함수 — ✓ 같음 · ▲ 코드만 · ◌ 명세만</span>
        </div>
      </div>
      {peek && <ItemPeek code={code} target={peek} onClose={() => setPeek(null)} />}
    </div>
  )
}
