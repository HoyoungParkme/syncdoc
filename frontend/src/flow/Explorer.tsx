/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 3 탐색기(3.1 트리 줄 · 3.2 고른 줄 · 3.3 접기) — view_arc explorer를 옮겼다(카드 CG).
 *  합친 폴더 트리 › 파일 › 클래스·함수. 맨 위 폴더에 화면·서버·보조 꼬리표, 라우트 함수에 메서드 꼬리표. */
import { useMemo, useState } from 'react'
import type { GraphNode } from './types'
import { type Model, type ViewNode, viewPath } from './model'
import { floorColor } from './scene'

type Props = {
  model: Model
  focusId: string
  selectedId: string | null
  onOpen: (id: string) => void
  onClose: () => void
}

function tagOf(v: ViewNode, depth: number): string | null {
  if (depth !== 1) return null
  if (v.aux) return '보조'
  return v.node.layer === 'frontend' ? '화면' : '서버'
}

export function Explorer({ model, focusId, selectedId, onOpen, onClose }: Props) {
  const [manual, setManual] = useState<Record<string, boolean>>({})
  // 초점·선택까지 가는 길은 저절로 펼친다
  const autoOpen = useMemo(() => {
    const ids = new Set<string>()
    for (const id of [focusId, selectedId]) if (id) viewPath(model, id).forEach((v) => ids.add(v.id))
    return ids
  }, [model, focusId, selectedId])
  const isOpen = (id: string) => manual[id] ?? autoOpen.has(id)

  const row = (node: GraphNode, label: string, depth: number, opts: { open?: boolean; onToggle?: () => void; active?: boolean; tag?: string | null }) => {
    const selected = selectedId === node.id
    const fn = node.kind !== 'project' && node.kind !== 'dir' && node.kind !== 'file'
    return (
      <div
        key={node.id}
        className={`tr${selected ? ' on' : ''}${opts.active ? ' cur' : ''}${fn ? ' fn' : ''}`}
        data-el={selected ? '3.2' : node.id === model.root.id ? '3.1' : undefined}
        style={{ paddingLeft: 10 + depth * 13 }}
        onClick={() => onOpen(node.id)}
        title={node.path}
      >
        {opts.open !== undefined ? (
          <span
            className="tw"
            onClick={(e) => {
              e.stopPropagation()
              opts.onToggle?.()
            }}
          >
            {opts.open ? '▾' : '▸'}
          </span>
        ) : (
          <span className="tw" />
        )}
        {fn && <i className="dot" style={{ background: floorColor(node) }} />}
        <span className="nm">{label}</span>
        {opts.tag && <span className="tag">{opts.tag}</span>}
        {node.route && <span className="tag">{node.route.method}</span>}
      </div>
    )
  }

  const render = (v: ViewNode, depth: number): React.ReactNode => {
    const open = isOpen(v.id)
    const expandable = v.children.length > 0 || v.floors.length > 0
    return (
      <div key={v.id}>
        {row(v.node, v.label, depth, {
          open: expandable ? open : undefined,
          onToggle: () => setManual((m) => ({ ...m, [v.id]: !open })),
          active: focusId === v.id,
          tag: tagOf(v, depth),
        })}
        {open && (
          <>
            {v.children.map((c) => render(c, depth + 1))}
            {v.floors.map((f) => row(f, f.name, depth + (f.kind === 'method' ? 2 : 1), {}))}
          </>
        )}
      </div>
    )
  }

  return (
    <aside className="cgtree fvtree" data-el="3">
      <div className="th">
        탐색기
        <span className="btn sm" data-el="3.3" onClick={onClose}>
          접기
        </span>
      </div>
      {render(model.root, 0)}
    </aside>
  )
}
