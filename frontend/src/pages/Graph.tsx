/** UI-8 참조 그래프 — SYNC-UI-002#UI-8. 열은 11단계 고정, 노드는 항목.
 *  1 헤더(1.1 통계) · 2 툴바(2.1 전체, 2.2 완료만, 2.4 포커스 라벨, 2.5 전체보기)
 *  3 캔버스(3.1 노드, 3.2 참조 간선, 3.3 되돌아오는 간선, 3.4 미존재 참조, 3.5 고립 노드) · 4 범례
 *  2.6 코드 호출 — MINISPEC 열에 실제 호출(3.6 같음 · 3.7 코드만 · 3.8 명세만)을 겹친다 (카드 AY)
 *
 *  배치는 브라우저가 한다 — 서버는 노드·간선 목록만 준다(MS-008 graph_view 8).
 *  라이브러리를 안 쓴다: 열이 고정이고 간선 넷이 저마다 다른 길로 가야 해서
 *  범용 그래프 엔진의 배치·라우팅과 계속 싸우게 된다. */
import { ProjName } from '../components/ui'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, STAGE_TYPES, type CodeCalls, type Graph as GraphData, type GraphScope } from '../api/client'
import { ItemChain } from '../components/ItemChain'

/** 열 간격과 노드 폭이 다르다 — 그 차(32px)가 간선이 지나는 거터다 */
const COL_PITCH = 150
const NODE_W = 118
const NODE_H = 26
const ROW_H = 40
const HEAD_H = 26
const PAD = 18
/** 되돌아오는 간선이 지나는 전용 레인. 모든 행 아래에 둔다 — 노드를 관통하지 않게 */
const LANE_GAP = 12
/** 되돌아오는 간선이 꺾이는 모서리 반지름 */
const R = 8

type Placed = { id: string; col: number; row: number; label: string; title: string; iso: boolean; docId: string; itemId: string | null }

export function Graph() {
  const { code = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const scope = (sp.get('scope') ?? 'all') as GraphScope
  const codeOn = sp.get('code') === '1' // 2.6 — URL ?code=1
  const [calls, setCalls] = useState<CodeCalls | null>(null)
  const [g, setG] = useState<GraphData | null>(null)
  const [focus, setFocus] = useState<string | null>(null)
  const [full, setFull] = useState(false)
  const [chain, setChain] = useState<{ docId: string; itemId: string } | null>(null)
  useEffect(() => {
    api.get<GraphData>(`/api/projects/${code}/graph?scope=${scope}`).then(setG)
  }, [code, scope])
  // 코드 호출은 켤 때만 받는다 — 대조는 서버가 부를 때 계산한다
  useEffect(() => {
    if (!codeOn) return
    let alive = true
    api.get<CodeCalls>(`/api/projects/${code}/code-calls`).then((c) => alive && setCalls(c))
    return () => {
      alive = false
    }
  }, [code, codeOn])
  // 범위·코드 호출은 서로를 지우지 않는다
  const setParam = (k: 'scope' | 'code', v: string | null) => {
    const next = new URLSearchParams(sp)
    if (v === null) next.delete(k)
    else next.set(k, v)
    setSp(next)
  }

  const layout = useMemo(() => (g ? place(g) : null), [g])
  // 직접 이웃만. 전이적으로 따라가는 건 UI-15가 한다
  const near = useMemo(() => {
    if (!g || !focus) return null
    const up = new Set<string>()
    const down = new Set<string>()
    for (const e of g.edges) {
      if (e.from === focus && e.to) up.add(e.to)
      if (e.to === focus) down.add(e.from)
    }
    return { up, down, all: new Set([focus, ...up, ...down]) }
  }, [g, focus])

  const stats = g
    ? `${code} · 문서 ${new Set(g.nodes.map((n) => n.doc_id)).size} · 항목 ${g.nodes.filter((n) => n.item_id).length} · 참조 ${g.edges.length}`
    : code
  const focusLabel = focus
    ? `${focus} — 상위 ${near?.up.size ?? 0} · 하위 ${near?.down.size ?? 0}`
    : '노드에 마우스를 올려 그 항목만 보기'

  const card = (
    <div className={`gcard${full ? ' full' : ''}`}>
      <div className="gbar" data-el="2">
        <span className="lbl">범위</span>
        {/* 범위는 잘라내는 게 아니라 골라낸다 — 열 11개는 늘 그대로다 */}
        <span className={`btn sm${scope === 'all' ? ' on' : ''}`} data-el="2.1" onClick={() => setParam('scope', null)}>
          전체
        </span>
        <span className={`btn sm${scope === 'approved' ? ' on' : ''}`} data-el="2.2" onClick={() => setParam('scope', 'approved')}>
          완료만
        </span>
        <span className="sep" />
        <span className="lbl" data-el="2.4">
          {codeOn && calls && !calls.graph ? '코드 그래프 없음 — 코드를 push하면 만들어집니다' : focusLabel}
        </span>
        <span className="grow" />
        <span className={`btn sm${codeOn ? ' on' : ''}`} data-el="2.6" onClick={() => setParam('code', codeOn ? null : '1')}>
          코드 호출
        </span>
        <span className="btn sm" data-el="2.5" onClick={() => setFull((f) => !f)}>
          {full ? '전체보기 끄기' : '전체보기'}
        </span>
      </div>
      <div className="canvas" data-el="3">
        {layout && (
          <div className="cinner" style={{ width: layout.w, height: layout.h }}>
            {STAGE_TYPES.map((t, i) => (
              <div key={t} className="colh" style={{ left: colX(i + 1), width: NODE_W }}>
                {i + 1} {t}
              </div>
            ))}
            <Edges layout={layout} g={g!} near={near} calls={codeOn ? (calls?.edges ?? []) : []} />
            {layout.nodes.map((n) => (
              <div
                key={n.id}
                className={`node${n.iso ? ' iso' : ''}${near && !near.all.has(n.id) ? ' dim' : ''}`}
                data-el={n.iso ? '3.5' : '3.1'}
                style={{ left: colX(n.col), top: rowY(n.row), width: NODE_W, height: NODE_H }}
                onMouseEnter={() => setFocus(n.id)}
                onMouseLeave={() => setFocus(null)}
                onClick={() => n.itemId && setChain({ docId: n.docId, itemId: n.itemId })}
                title={n.title}
              >
                <span className="nlabel">
                  {n.iso && '◌ '}
                  {n.label}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="glegend lbl" data-el="4">
        <span>노드 = 항목 · 열 = 11단계</span>
        <span>
          <svg className="sw" viewBox="0 0 22 8">
            <path className="e" d="M1 4 H21" />
          </svg>{' '}
          참조 (하위 → 상위)
        </span>
        <span className="back">
          <svg className="sw" viewBox="0 0 22 8">
            <path className="e back" d="M1 4 H21" />
          </svg>{' '}
          되돌아오는 참조
        </span>
        <span className="gone">
          <svg className="sw" viewBox="0 0 22 8">
            <path className="e gone" d="M1 4 H21" />
          </svg>{' '}
          미존재 참조
        </span>
        <span>◌ 고립 (참조 없음)</span>
        {codeOn && (
          <>
            <span>
              <svg className="sw" viewBox="0 0 22 8">
                <path className="e cg same" d="M1 4 H21" />
              </svg>{' '}
              호출 — 명세와 같음
            </span>
            <span className="cgl">
              <svg className="sw" viewBox="0 0 22 8">
                <path className="e cg code" d="M1 4 H21" />
              </svg>{' '}
              호출 — 코드만
            </span>
            <span className="gone">
              <svg className="sw" viewBox="0 0 22 8">
                <path className="e cg spec" d="M1 4 H21" />
              </svg>{' '}
              호출 — 명세만
            </span>
          </>
        )}
        <span className="grow" />
        <span>노드에 마우스를 올리면 그 항목의 참조만 남는다 · 클릭 → 11단계 흐름</span>
      </div>
    </div>
  )

  return (
    <div className="page graphpage">
      <div className="phead" data-el="1">
        <div>
          <div className="crumbs">
            <Link to={`/p/${code}`}>
              <ProjName code={code} name={g?.project_name} />
            </Link>
            <span className="sep">›</span>
            <span>참조 그래프</span>
          </div>
          <b>참조 그래프</b>
        </div>
        <span className="grow" />
        <span className="lbl" data-el="1.1">
          {stats}
        </span>
      </div>
      {/* 전체보기는 상단 바까지 덮는다 — 그래서 body로 포털을 쓴다 */}
      {full ? createPortal(card, document.body) : card}
      {chain && <ItemChain docId={chain.docId} itemId={chain.itemId} onPick={setChain} onClose={() => setChain(null)} />}
    </div>
  )
}

const colX = (stage: number) => PAD + (stage - 1) * COL_PITCH
const rowY = (row: number) => HEAD_H + row * ROW_H

/** 열 안 순서를 이웃의 평균 위치로 정렬한다(barycenter). 상위 기준과 하위 기준을 번갈아 네 번.
 *  이웃이 없는 노드는 제자리 — 그래서 언제 그려도 같은 그림이 나온다. */
function place(g: GraphData) {
  const cols: string[][] = Array.from({ length: 12 }, () => [])
  const byId = new Map(g.nodes.map((n) => [n.id, n]))
  // 시작 순서는 문서 ID → 항목 ID. 정렬이 이걸 흔들되 결정론은 여기서 나온다
  for (const n of [...g.nodes].sort((a, b) => cmp(a.doc_id, b.doc_id) || cmp(a.item_id ?? '', b.item_id ?? ''))) {
    cols[n.stage ?? 1].push(n.id)
  }
  const up = new Map<string, string[]>() // 하위 → 상위
  const down = new Map<string, string[]>()
  for (const e of g.edges) {
    if (!e.to) continue
    push(up, e.from, e.to)
    push(down, e.to, e.from)
  }
  for (let pass = 0; pass < 4; pass++) {
    const nbr = pass % 2 === 0 ? up : down
    const order = pass % 2 === 0 ? [...Array(11).keys()].map((i) => i + 1) : [...Array(11).keys()].map((i) => 11 - i)
    for (const c of order) {
      const rows = new Map<string, number>()
      cols.forEach((col) => col.forEach((id, i) => rows.set(id, i)))
      const bary = new Map<string, number>()
      cols[c].forEach((id, i) => {
        const ns = (nbr.get(id) ?? []).map((x) => rows.get(x)).filter((v): v is number => v !== undefined)
        bary.set(id, ns.length ? ns.reduce((a, b) => a + b, 0) / ns.length : i) // 이웃이 없으면 제자리
      })
      cols[c] = [...cols[c]].sort((a, b) => bary.get(a)! - bary.get(b)! || cmp(a, b))
    }
  }
  const nodes: Placed[] = []
  cols.forEach((col, c) =>
    col.forEach((id, row) => {
      const n = byId.get(id)!
      const short = n.doc_id.split('-').slice(1).join('-')
      nodes.push({
        id,
        col: c,
        row,
        label: n.item_id ? `${short}#${n.item_id}` : short,
        title: n.item_id ? `${n.doc_id}#${n.item_id}` : n.doc_id,
        iso: n.isolated,
        docId: n.doc_id,
        itemId: n.item_id,
      })
    }),
  )
  const tallest = Math.max(1, ...cols.map((c) => c.length))
  const lane = rowY(tallest) + LANE_GAP
  return {
    nodes,
    pos: new Map(nodes.map((n) => [n.id, n])),
    w: colX(11) + NODE_W + PAD,
    h: lane + 26,
    lane,
  }
}

type Layout = ReturnType<typeof place>

/** 간선 넷. 상위가 왼쪽이면 곡선, 같은 열이면 왼쪽으로 나갔다 돌아오고,
 *  오른쪽이면(되돌아오는 참조) 행 아래 전용 레인으로 우회하고, 대상이 없으면 짧게 뻗다 끊긴다. */
function Edges({
  layout,
  g,
  near,
  calls,
}: {
  layout: Layout
  g: GraphData
  near: { all: Set<string> } | null
  calls: CodeCalls['edges']
}) {
  // 와이어프레임처럼 종류마다 한 번씩만 요소 번호를 붙인다 (DEV-17 반복 행 규칙)
  const seen = { e: false, back: false, gone: false }
  const paths: React.ReactNode[] = []
  g.edges.forEach((edge, i) => {
    const f = layout.pos.get(edge.from)
    if (!f) return
    const fx = colX(f.col)
    const fy = rowY(f.row) + NODE_H / 2
    const lit = !near || (near.all.has(edge.from) && (!edge.to || near.all.has(edge.to)))
    const cls = (k: 'e' | 'back' | 'gone') => `e${k === 'e' ? '' : ' ' + k}${lit ? '' : ' dim'}`
    const first = (k: 'e' | 'back' | 'gone') => !seen[k] && ((seen[k] = true), true)
    if (!edge.to) {
      // 3.4 미존재 참조 — 대상이 어느 문서에도 없다. 범위 밖이라 빠진 것과 다르다
      paths.push(<path key={i} className={cls('gone')} data-el={first('gone') ? '3.4' : undefined} d={`M${fx} ${fy} H${fx - 13}`} />)
      return
    }
    const t = layout.pos.get(edge.to)
    if (!t) return // 범위 밖 — 그리지 않는다 (MS-008 5)
    const tx = colX(t.col) + NODE_W
    const ty = rowY(t.row) + NODE_H / 2
    if (t.col < f.col) {
      const mid = (fx + tx) / 2
      paths.push(<path key={i} className={cls('e')} data-el={first('e') ? '3.2' : undefined} d={`M${fx} ${fy} C${mid} ${fy} ${mid} ${ty} ${tx} ${ty}`} />)
    } else if (t.col === f.col) {
      // 같은 열 — 왼쪽으로 나갔다 돌아오는 꺾은선
      const out = fx - 13
      paths.push(<path key={i} className={cls('e')} data-el={first('e') ? '3.2' : undefined} d={`M${fx} ${fy} H${out} V${ty} H${tx - NODE_W}`} />)
    } else {
      // 3.3 되돌아오는 참조 — 상위가 오른쪽 열. 열 사이 빈 자리로 빠져나가 행 아래 레인을
      // 가로지른 뒤 올라온다. 열 안으로 내려가면 그 열 노드들을 관통한다
      const lane = layout.lane
      const x1 = colX(f.col) + NODE_W
      const out = x1 + 16
      const inn = colX(t.col) - 16
      // 모서리를 둥글게 — 직각으로 꺾으면 레인 위에서 선이 서로 붙어 보인다
      const d =
        `M${x1} ${fy} L${out - R} ${fy} Q${out} ${fy} ${out} ${fy + R}` +
        ` L${out} ${lane - R} Q${out} ${lane} ${out + R} ${lane}` +
        ` L${inn - R} ${lane} Q${inn} ${lane} ${inn} ${lane - R}` +
        ` L${inn} ${ty + R} Q${inn} ${ty} ${inn + R} ${ty} L${colX(t.col)} ${ty}`
      paths.push(<path key={i} className={cls('back')} data-el={first('back') ? '3.3' : undefined} d={d} />)
    }
  })
  // 2.6 코드 호출 — MINISPEC 항목끼리, 열 **오른쪽으로** 나갔다 돌아온다(참조 간선은 왼쪽).
  // 종류마다 거터 안 다른 거리로 돌아 셋이 한 줄로 겹치지 않는다 (카드 AY)
  const kinds = { same: ['same', 8], code_only: ['code', 14], spec_only: ['spec', 20] } as const
  const firstCode = { same: false, code_only: false, spec_only: false }
  calls.forEach((c, i) => {
    const f = layout.pos.get(c.from)
    const t = layout.pos.get(c.to)
    if (!f || !t) return // 범위 밖
    const [cls, gap] = kinds[c.status]
    const x = colX(f.col) + NODE_W
    const fy = rowY(f.row) + NODE_H / 2 + (c.status === 'code_only' ? 3 : c.status === 'spec_only' ? -3 : 0)
    const ty = rowY(t.row) + NODE_H / 2
    const tx = colX(t.col) + NODE_W
    const lit = !near || (near.all.has(c.from) && near.all.has(c.to))
    const tag = !firstCode[c.status] && ((firstCode[c.status] = true), true)
    paths.push(
      <path
        key={`c${i}`}
        className={`e cg ${cls}${lit ? '' : ' dim'}`}
        data-el={tag ? (c.status === 'same' ? '3.6' : c.status === 'code_only' ? '3.7' : '3.8') : undefined}
        d={`M${x} ${fy} H${x + gap} V${ty} H${tx}`}
      />,
    )
  })
  return (
    <svg className="edges" width={layout.w} height={layout.h}>
      {/* 화살촉이 없으면 어느 쪽이 상위인지 그림만 보고는 못 읽는다 */}
      <defs>
        <marker id="ah" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 z" fill="var(--graph-edge)" />
        </marker>
        <marker id="ahb" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 z" fill="var(--danger)" />
        </marker>
        <marker id="ahr" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 z" fill="var(--ref-backlink)" />
        </marker>
        <marker id="ahc" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 z" fill="var(--graph-edge)" />
        </marker>
      </defs>
      {paths}
    </svg>
  )
}

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)
const push = (m: Map<string, string[]>, k: string, v: string) => m.set(k, [...(m.get(k) ?? []), v])
