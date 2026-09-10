/** UI-8 참조 그래프 — SYNC-UI-002#UI-8. react-flow 렌더링, 배치는 11단계 열 고정(규칙: 열은 단계, 열 안은 문서 ID → 항목 ID).
 *  요소 번호 = data-el. 1 헤더 · 2.1 전체 · 2.2 단계 · 2.3 문서 · 3 그래프(3.1 노드, 3.2 간선 설명, 3.3 고립 노드) · 4 범례 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api, docPath, STAGE_TYPES, type DocumentSummary, type Graph as GraphData } from '../api/client'

type ItemData = { label: string; isolated: boolean; isDoc: boolean; missing?: boolean; doc_id: string; item_id: string | null }

function ItemNode({ data }: NodeProps<Node<ItemData>>) {
  return (
    <div className={`node${data.isolated ? ' iso' : ''}${data.isDoc ? ' doc' : ''}${data.missing ? ' miss' : ''}`} data-el={data.missing ? undefined : data.isolated ? '3.3' : '3.1'}>
      <Handle type="target" position={Position.Right} style={{ opacity: 0 }} />
      {data.label}
      <Handle type="source" position={Position.Left} style={{ opacity: 0 }} />
    </div>
  )
}
const nodeTypes = { item: ItemNode }
const COL = 230
const ROW = 34

export function Graph() {
  const { code = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const stage = sp.get('stage')
  const doc = sp.get('doc')
  const [g, setG] = useState<GraphData | null>(null)
  const [docs, setDocs] = useState<DocumentSummary[]>([])
  useEffect(() => {
    api.get<DocumentSummary[]>(`/api/projects/${code}/docs`).then(setDocs)
  }, [code])
  useEffect(() => {
    const q = stage ? `?stage=${stage}` : doc ? `?doc=${doc}` : ''
    api.get<GraphData>(`/api/projects/${code}/graph${q}`).then(setG)
  }, [code, stage, doc])

  const { nodes, edges } = useMemo(() => {
    if (!g) return { nodes: [] as Node<ItemData>[], edges: [] as Edge[] }
    const sorted = [...g.nodes].sort((a, b) => (a.stage ?? 0) - (b.stage ?? 0) || (a.doc_id < b.doc_id ? -1 : a.doc_id > b.doc_id ? 1 : (a.item_id ?? '') < (b.item_id ?? '') ? -1 : 1))
    const rowOf: Record<number, number> = {}
    const nodes: Node<ItemData>[] = sorted.map((n) => {
      const col = n.stage ?? 0
      const row = (rowOf[col] = (rowOf[col] ?? 0) + 1)
      const short = n.doc_id.split('-').slice(1).join('-')
      return {
        id: n.id,
        type: 'item',
        position: { x: col * COL, y: row * ROW },
        data: { label: n.item_id ? `${short}#${n.item_id}` : short, isolated: n.isolated, isDoc: !n.item_id, doc_id: n.doc_id, item_id: n.item_id },
      }
    })
    const edges: Edge[] = []
    g.edges.forEach((e, i) => {
      let target = e.to
      if (!target) {
        target = `missing:${i}`
        const src = nodes.find((n) => n.id === e.from)
        nodes.push({ id: target, type: 'item', position: { x: (src?.position.x ?? 0) - COL / 2, y: (src?.position.y ?? 0) + ROW / 2 }, data: { label: `? ${e.raw_target}`, isolated: false, isDoc: false, missing: true, doc_id: '', item_id: null } })
      }
      edges.push({ id: `e${i}`, source: e.from, target, markerEnd: 'arrow', style: e.is_missing ? { strokeDasharray: '4 3' } : undefined })
    })
    return { nodes, edges }
  }, [g])
  const stats = g ? `문서 ${new Set(g.nodes.map((n) => n.doc_id).filter(Boolean)).size} · 항목 ${g.nodes.filter((n) => n.item_id).length} · 참조 ${g.edges.length}` : ''
  return (
    <div className="page graphpage">
      <div className="phead" data-el="1">
        <div>
          <b>참조 그래프</b> <span className="lbl">{code} · {stats}</span>
        </div>
        <span className="grow" />
        <span className="lbl">범위</span>
        <span className={`btn${!stage && !doc ? ' on' : ''}`} data-el="2.1" onClick={() => setSp({})}>
          전체
        </span>
        <select className={`btn${stage ? ' on' : ''}`} data-el="2.2" value={stage ?? ''} onChange={(e) => setSp(e.target.value ? { stage: e.target.value } : {})}>
          <option value="">단계: — ▾</option>
          {STAGE_TYPES.map((t, i) => (
            <option key={t} value={i + 1}>
              단계: {t}
            </option>
          ))}
        </select>
        <select className={`btn${doc ? ' on' : ''}`} data-el="2.3" value={doc ?? ''} onChange={(e) => setSp(e.target.value ? { doc: e.target.value } : {})}>
          <option value="">문서: — ▾</option>
          {docs.map((d) => (
            <option key={d.doc_id} value={d.doc_id}>
              문서: {d.doc_id}
            </option>
          ))}
        </select>
      </div>
      <div className="graph" data-el="3">
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView onNodeClick={(_, n) => n.data.doc_id && nav(docPath(n.data.doc_id, n.data.item_id))} nodesDraggable={false} nodesConnectable={false} proOptions={{ hideAttribution: true }}>
          <Background />
        </ReactFlow>
        <div className="edges lbl" data-el="3.2">
          — 간선: 하위 → 상위 방향 화살표. 미존재 참조는 점선 —
        </div>
      </div>
      <div className="legend lbl" data-el="4">
        <span>● 항목</span> <span>◌ 고립 (참조 없음)</span> <span>─ 참조</span> <span>┈ 미존재 참조</span>
      </div>
    </div>
  )
}
