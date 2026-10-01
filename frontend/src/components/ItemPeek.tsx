/** UI-18 항목 미리보기 — SYNC-UI-002#UI-18 (카드 BH). 참조 줄·카드를 누르면 그 항목 블록 하나만 다이얼로그에.
 *  1 다이얼로그(1.1 뒤로 · 1.2 항목 ID · 1.3 문서·상태·버전 · 1.4 이동 · 1.5 새 창 · 1.6 닫기) · 2 본문(2.1 블록 안 참조 링크) ·
 *  3 문서 머리(문서 전체 참조일 때). 블록은 서버가 자르고(GET /api/docs/{doc}/items/{item} — MCP get_item과 같은 함수)
 *  화면은 유저용 렌더(renderBlocks)로 그린다. 블록 안 참조는 스택에 쌓아 팝업 안에서 이어 보고 「뒤로」로 되짚는다 —
 *  브라우저 히스토리는 안 건드린다(팝업은 URL이 없다). 그림(mermaid)은 그리지 않는다 — 보려면 「이동」. */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, type Document, type ItemView } from '../api/client'
import { renderBlocks } from '../view/md'
import { ItemIdBadge, StatusPill, useEscape } from './ui'

export interface PeekTarget {
  doc_id: string
  item_id: string | null
}
type Entry = { kind: 'item'; v: ItemView } | { kind: 'doc'; d: Document; title: string } | { kind: 'deleted'; at: string } | { kind: 'error'; msg: string }

const keyOf = (t: PeekTarget) => `${t.doc_id}#${t.item_id ?? ''}`
/** 프로젝트 코드 접두는 뺀다 — 뱃지는 좁고 같은 프로젝트 안이다 (UI-15와 같은 규칙) */
const short = (id: string) => id.split('-').slice(1).join('-')
const pathOf = (code: string, t: PeekTarget) => `/p/${t.doc_id.split('-')[0] || code}/d/${t.doc_id}${t.item_id ? '#item-' + t.item_id : ''}`
/** frontmatter title — Document DTO에 제목이 없어 본문에서 읽는다 */
const titleOf = (body: string) => /^title:\s*(.*)$/m.exec(body.startsWith('---') ? body.slice(3).split('\n---', 1)[0] : '')?.[1]?.trim() ?? ''
const PEEK_LINK = /^\/p\/[^/]+\/d\/([^#?]+)(?:#item-(.+))?$/

export function ItemPeek({ code, target, onClose }: { code: string; target: PeekTarget; onClose: () => void }) {
  const nav = useNavigate()
  const [stack, setStack] = useState<PeekTarget[]>([target])
  const cache = useRef(new Map<string, Entry>())
  const [, tick] = useState(0)
  useEscape(onClose)
  // 밖에서 다른 참조를 누르면 스택을 새로 시작한다
  const targetKey = keyOf(target)
  useEffect(() => {
    setStack([target])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetKey])

  const cur = stack[stack.length - 1]
  const curKey = keyOf(cur)
  // 받은 블록은 스택을 내려갈 때 다시 받지 않는다 (UI-18 규칙)
  useEffect(() => {
    if (cache.current.has(curKey)) return
    let alive = true
    const done = (e: Entry) => {
      if (!alive) return
      cache.current.set(curKey, e)
      tick((t) => t + 1)
    }
    const fail = (e: unknown) => {
      if (e instanceof ApiError && e.kind === 'item-deleted') done({ kind: 'deleted', at: String((e.problem as { deleted_at?: string }).deleted_at ?? '') })
      else done({ kind: 'error', msg: e instanceof ApiError ? e.message : String(e) })
    }
    if (cur.item_id) api.get<ItemView>(`/api/docs/${cur.doc_id}/items/${cur.item_id.replace(/\//g, '~')}`).then((v) => done({ kind: 'item', v })).catch(fail)
    else api.get<Document>(`/api/docs/${cur.doc_id}`).then((d) => done({ kind: 'doc', d, title: titleOf(d.body) })).catch(fail)
    return () => {
      alive = false
    }
  }, [curKey, cur.doc_id, cur.item_id])

  const entry = cache.current.get(curKey)
  const path = pathOf(code, cur)
  const go = () => {
    onClose()
    nav(path)
  }
  // 2.1 — 블록 안 참조 링크는 팝업이 그 항목으로 바뀐다(스택). 같은 항목이면 아무 일도 없다
  const onBodyClick = (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a[href]')
    if (!a) return
    const m = PEEK_LINK.exec(a.getAttribute('href') ?? '')
    if (!m) return
    e.preventDefault()
    const next: PeekTarget = { doc_id: m[1], item_id: m[2] ? decodeURIComponent(m[2]) : null }
    if (keyOf(next) === curKey) return
    setStack((s) => [...s, next])
  }
  const ctx = { selfId: cur.doc_id, href: (d: string, it?: string) => pathOf(code, { doc_id: d, item_id: it ?? null }), exists: () => true }
  const status = entry?.kind === 'item' ? entry.v.doc_status : entry?.kind === 'doc' ? entry.d.status : null
  const version = entry?.kind === 'item' ? entry.v.doc_version_no : entry?.kind === 'doc' ? entry.d.current_version_no : null

  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog wide peek" data-el="1" onClick={(e) => e.stopPropagation()}>
        <div className="dhead">
          {stack.length > 1 && (
            <span className="bk" data-el="1.1" onClick={() => setStack((s) => s.slice(0, -1))}>
              ‹ 뒤로
            </span>
          )}
          <ItemIdBadge el="1.2">
            {short(cur.doc_id)}
            {cur.item_id ? '#' + cur.item_id : ''}
          </ItemIdBadge>
          <span className="doc" data-el="1.3" title={cur.doc_id}>
            {short(cur.doc_id)}
            {status && <StatusPill status={status} />}
            {version != null && <span className="mono">v{version}</span>}
          </span>
          <span className="grow" />
          <span className="btn sm" data-el="1.5" onClick={() => window.open(path, '_blank')}>
            새 창
          </span>
          <span className="btn sm solid" data-el="1.4" onClick={go}>
            이동
          </span>
          <span className="x" data-el="1.6" onClick={onClose}>
            ✕
          </span>
        </div>
        <div className="dbody" data-el="2" onClick={onBodyClick}>
          {!entry ? (
            <div className="lbl">불러오는 중…</div>
          ) : entry.kind === 'item' ? (
            // 블록 안 첫 참조 링크에 2.1 — 나머지도 같은 링크다
            <div className="body" dangerouslySetInnerHTML={{ __html: renderBlocks(entry.v.body, ctx).replace('<a ', '<a data-el="2.1" ') }} />
          ) : entry.kind === 'doc' ? (
            <div className="dochead" data-el="3">
              <div className="t">{entry.title || entry.d.doc_id}</div>
              <div className="m">
                {entry.d.stage}단계 {entry.d.doc_type} · {entry.d.status === 'approved' ? '완료' : '초안'} · 항목 {entry.d.items.length} · 문서 전체를 가리키는 참조라 본문은 열지 않는다
              </div>
            </div>
          ) : entry.kind === 'deleted' ? (
            <div className="lbl">삭제된 항목 — {entry.at ? entry.at.slice(0, 10) : ''}</div>
          ) : (
            <div className="lbl">{entry.msg}</div>
          )}
        </div>
        <div className="dfoot">
          <span className="lbl">{cur.item_id ? '그림은 「이동」해서 본다 · Esc로 닫힘' : '문서를 보려면 「이동」'}</span>
          <span className="grow" />
        </div>
      </div>
    </>
  )
}
