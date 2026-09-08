/** UI-5 문서 뷰 — SYNC-UI-002#UI-5. 유저용(기본)·원본 탭, 목차, 오른쪽 패널(참조·댓글), 상태 변경 + 상위 대조 다이얼로그.
 *  유저용 탭 본문은 view/*.ts(view_build.py 포트, STD-002)가 만든 HTML을 innerHTML로 넣고 mermaid를 돌린다. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import mermaid from 'mermaid'
import { api, ApiError, STATUS_KO, type Comment, type Document, type ItemReferences, type UpstreamCheck } from '../api/client'
import { extraCss, renderView } from '../view'
import { esc, splitRef } from '../view/md'

const FLAG_KO: Record<string, string> = { needs_check: '확인 필요', broken_ref: '끊어진 참조', upstream_impact: '하위 불일치' }

export function DocView() {
  const { code = '', docId = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const tab = sp.get('tab') === 'raw' ? 'raw' : 'user'
  const [doc, setDoc] = useState<Document | null>(null)
  const [err, setErr] = useState('')
  const [panel, setPanel] = useState<'refs' | 'comments'>('refs')
  const [selected, setSelected] = useState<string | null>(null)
  const [refs, setRefs] = useState<ItemReferences | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [line, setLine] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [statusOpen, setStatusOpen] = useState(false)
  const [upstream, setUpstream] = useState<UpstreamCheck[] | null>(null)
  const [mismatch, setMismatch] = useState<Set<string>>(new Set())
  const [reason, setReason] = useState('')
  const mainRef = useRef<HTMLElement>(null)

  const load = useCallback(() => {
    api
      .get<Document>(`/api/docs/${docId}`)
      .then(setDoc)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)))
    api.get<Comment[]>(`/api/docs/${docId}/comments`).then(setComments)
  }, [docId])
  useEffect(() => {
    setSelected(null)
    setRefs(null)
    load()
  }, [load])

  const view = useMemo(() => (doc ? renderView(doc, code) : null), [doc, code])

  // 유저용 본문: innerHTML → onMount → mermaid → 항목 클릭·참조 링크·해시 스크롤
  useEffect(() => {
    const root = mainRef.current
    if (!root || !view || tab !== 'user') return
    root.innerHTML = view.html
    const cleanup = view.onMount?.(root)
    mermaid.initialize({ startOnLoad: false, theme: 'neutral' })
    mermaid.run({ nodes: root.querySelectorAll<HTMLElement>('pre.mermaid') }).catch(() => undefined) // 문법 오류면 코드가 남는다 (UC-H2 2a)
    for (const el of root.querySelectorAll<HTMLElement>('[data-item]')) {
      const badge = el.querySelector('.iid') ?? el
      const fl = doc?.items.find((i) => i.item_id === el.dataset.item)?.flags ?? []
      if (fl.length && !el.querySelector('.flagx')) badge.insertAdjacentHTML('afterend', fl.map((f) => `<span class="flag flagx">${FLAG_KO[f] ?? f}</span>`).join(''))
    }
    const onClick = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement
      const a = t.closest<HTMLAnchorElement>('a[data-ref]')
      if (a) {
        ev.preventDefault()
        if (a.classList.contains('missing')) return
        const [d, it] = splitRef(a.dataset.ref ?? '')
        nav(`/p/${d.split('-')[0]}/d/${d}${it ? '#item-' + it : ''}`)
        return
      }
      const item = t.closest<HTMLElement>('[data-item]')
      if (item && item.dataset.item) {
        setSelected(item.dataset.item)
        setPanel('refs')
      }
    }
    root.addEventListener('click', onClick)
    if (window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: 'start' })
    return () => {
      root.removeEventListener('click', onClick)
      if (typeof cleanup === 'function') cleanup()
    }
  }, [view, tab, doc, nav])

  useEffect(() => {
    if (!selected) return
    api.get<ItemReferences>(`/api/docs/${docId}/items/${selected.replace(/\//g, '~')}/references`).then(setRefs).catch(() => setRefs(null))
  }, [selected, docId])

  async function openStatus(to: string) {
    setStatusOpen(false)
    if (to !== 'approved') {
      await changeStatus(to, false, [])
      return
    }
    const u = await api.get<UpstreamCheck[]>(`/api/docs/${docId}/upstream`)
    setUpstream(u)
    setMismatch(new Set())
  }
  async function changeStatus(to: string, reviewed: boolean, mism: string[]) {
    try {
      await api.post(`/api/docs/${docId}/status`, { to, reason: reason || null, upstream_reviewed: reviewed, upstream_mismatch: mism })
      setUpstream(null)
      load()
    } catch (e) {
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    }
  }
  async function addComment(parent: number | null) {
    if (!draft.trim() || !line) return
    await api.post(`/api/docs/${docId}/comments`, { line_no: line, body: draft, parent_comment_id: parent })
    setDraft('')
    load()
  }
  async function resolve(c: Comment, v: boolean) {
    await api.post(`/api/comments/${c.id}/resolve`, { resolved: v })
    load()
  }

  if (err) return <div className="page banner err">{err}</div>
  if (!doc || !view) return null
  const unresolved = comments.filter((c) => !c.is_resolved).length
  const lines = doc.body.split('\n')
  const key = (u: UpstreamCheck) => `${u.target.doc_id}${u.target.item_id ? '#' + u.target.item_id : ''}`
  const toc = tocOf(doc)

  return (
    <>
      <div className="docbar" data-el="1">
        <span>
          <b>{doc.doc_id}</b> ·{' '}
          <span className={`st st-${doc.status}`} data-el="1.1">
            {STATUS_KO[doc.status]}
          </span>{' '}
          · <span data-el="1.2">v{doc.current_version_no}</span>
        </span>
        <span className="tabs" data-el="2">
          <span className={tab === 'user' ? 'on' : ''} data-el="2.1" onClick={() => setSp({})}>
            유저용
          </span>
          <span className={tab === 'raw' ? 'on' : ''} data-el="2.2" onClick={() => setSp({ tab: 'raw' })}>
            원본
          </span>
          <span data-el="2.3" title="UI-7 — B4">
            이력
          </span>
        </span>
        <span className="grow" />
        {unresolved > 0 && (
          <span data-el="5" className="lbl" onClick={() => setPanel('comments')}>
            미해결 댓글 {unresolved}
          </span>
        )}
        <span className="statuswrap">
          <button className="btn" data-el="3" disabled={doc.has_convention_error} onClick={() => setStatusOpen((o) => !o)}>
            상태 변경 ▾
          </button>
          {statusOpen && (
            <div className="menu">
              {['draft', 'review', 'approved']
                .filter((s) => s !== doc.status)
                .map((s) => (
                  <div key={s} className={`mi${s === 'approved' && doc.incomplete_warnings.length ? ' dis' : ''}`} onClick={() => !(s === 'approved' && doc.incomplete_warnings.length) && openStatus(s)}>
                    {STATUS_KO[s]}
                  </div>
                ))}
            </div>
          )}
        </span>
      </div>

      {doc.has_convention_error && (
        <div className="banner" data-el="4">
          ⚠ 규약 오류: {doc.convention_error_detail} (커밋 {doc.commit_hash?.slice(0, 7)} · {doc.last_author?.user?.display_name})
        </div>
      )}
      {doc.incomplete_warnings.length > 0 && (
        <div className="banner warn" data-el="4a">
          미완성: {doc.incomplete_warnings.join(' · ')} · 승인 불가
        </div>
      )}

      {tab === 'user' ? (
        <div className="body3" data-el="7">
          <nav className="toc" data-el="6">
            <div className="lbl">목차</div>
            {toc.map((t) => (
              <div key={t.id} className={t.depth ? 'd1' : ''} onClick={() => document.getElementById(t.id)?.scrollIntoView({ block: 'start' })}>
                {t.text}
              </div>
            ))}
          </nav>
          <style>{extraCss}</style>
          <article className="main body" ref={mainRef} />
          <aside className="panel" data-el="8">
            <div className="ptabs">
              <span className={panel === 'refs' ? 'on' : ''} data-el="8.1" onClick={() => setPanel('refs')}>
                참조
              </span>
              <span className={panel === 'comments' ? 'on' : ''} data-el="8.2" onClick={() => setPanel('comments')}>
                댓글
              </span>
            </div>
            <div className="pbody">
              {panel === 'refs' && (!selected ? <div className="lbl">항목을 선택하세요</div> : refs ? <Refs refs={refs} /> : <div className="lbl">선택: #{selected}</div>)}
              {panel === 'comments' && (
                <Comments comments={comments} line={line} setLine={setLine} draft={draft} setDraft={setDraft} add={addComment} resolve={resolve} lines={lines} />
              )}
            </div>
          </aside>
        </div>
      ) : (
        <div className="rawwrap" data-el="10">
          <div className="rawbar">
            <span className="lbl">에이전트가 읽는 원본 그대로 · 읽기 전용</span>
            <span className="grow" />
            <button className="btn" data-el="10.2" onClick={() => navigator.clipboard.writeText(doc.body)}>
              복사
            </button>
          </div>
          <div className="editor" data-el="10.1">
            <div className="gutter">
              {lines.map((_, i) => (
                <span key={i}>{i + 1}</span>
              ))}
            </div>
            <pre className="code">{doc.body}</pre>
          </div>
        </div>
      )}

      <div className="nav" data-el="9">
        {doc.prev_doc_id ? <Link className="btn" to={`/p/${code}/d/${doc.prev_doc_id}`}>← {doc.prev_doc_id}</Link> : <span className="btn dis">←</span>}
        {doc.next_doc_id ? <Link className="btn" to={`/p/${code}/d/${doc.next_doc_id}`}>{doc.next_doc_id} →</Link> : <span className="btn dis">→</span>}
      </div>

      {upstream !== null && (
        <div className="dialog" data-el="11">
          <div className="dhead">승인 전 상위 대조 — {doc.doc_id}</div>
          <div className="dbody">
            {upstream.length === 0 ? (
              <p>상위 없음 — 이 문서는 근거로 삼은 상위 항목이 없습니다.</p>
            ) : (
              <>
                이 문서가 근거로 삼은 상위 항목입니다. 이 문서의 내용과 <b>어긋난 것</b>이 있으면 표시하세요. 표시한 항목에 <b>하위 불일치</b> 플래그가 붙어 상위 담당자에게 갑니다.
                <table className="uptbl" data-el="11.1">
                  <thead>
                    <tr>
                      <th />
                      <th>상위 항목</th>
                      <th>현재</th>
                      <th>참조한 곳</th>
                    </tr>
                  </thead>
                  <tbody>
                    {upstream.map((u) => (
                      <tr key={key(u)} data-el="11.2">
                        <td>
                          <input
                            type="checkbox"
                            disabled={!u.target.item_id}
                            checked={mismatch.has(key(u))}
                            onChange={(e) => {
                              const n = new Set(mismatch)
                              if (e.target.checked) n.add(key(u))
                              else n.delete(key(u))
                              setMismatch(n)
                            }}
                          />
                        </td>
                        <td>
                          <a href={`/p/${u.target.doc_id?.split('-')[0]}/d/${u.target.doc_id}${u.target.item_id ? '#item-' + u.target.item_id : ''}`} target="_blank" rel="noreferrer">
                            <b>{key(u)}</b>
                          </a>{' '}
                          {u.target.item_id ? u.target.display_name : '(문서 전체)'}
                        </td>
                        <td>
                          v{u.target_version_no} · {STATUS_KO[u.target_status]}
                          {u.target_status !== 'approved' && <span className="lbl"> (상위 미승인)</span>}
                        </td>
                        <td>{u.referenced_from.join(', ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            <input className="inp wide" placeholder="사유 (선택)" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="dacts">
              <button className="btn" data-el="11.4" onClick={() => setUpstream(null)}>
                닫기
              </button>{' '}
              <button className="btn" data-el="11.3" style={{ fontWeight: 600 }} onClick={() => changeStatus('approved', true, [...mismatch])}>
                {mismatch.size ? `어긋남 ${mismatch.size}건 표시하고 승인` : '어긋난 곳 없음 · 승인'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function tocOf(doc: Document): { id: string; text: string; depth: number }[] {
  const out: { id: string; text: string; depth: number }[] = []
  const ids = new Set(doc.items.map((i) => i.item_id))
  let inCode = false
  for (const l of doc.body.split('\n')) {
    if (l.startsWith('```')) inCode = !inCode
    if (inCode) continue
    const h = /^(#{2,6}) (.+)$/.exec(l)
    if (!h) continue
    const tok = h[2].split(' ')[0]
    if (ids.has(tok)) out.push({ id: `item-${tok}`, text: h[2], depth: 1 })
    else if (h[1].length === 2) out.push({ id: `sec-${esc(h[2].replace(/[^\w가-힣]/g, ''))}`, text: h[2], depth: 0 })
  }
  return out
}

function Refs({ refs }: { refs: ItemReferences }) {
  const link = (r: ItemReferences['upstream'][number]) =>
    r.is_missing ? (
      <li className="ref missing" title="미존재 참조">
        {r.raw_target} ?
      </li>
    ) : (
      <li className="ref">
        <Link to={`/p/${r.doc_id?.split('-')[0]}/d/${r.doc_id}${r.item_id ? '#item-' + r.item_id : ''}`}>
          {r.doc_id}
          {r.item_id ? '#' + r.item_id : ' (문서 전체)'}
        </Link>{' '}
        <span className="lbl">{r.display_name}</span>
      </li>
    )
  return (
    <>
      <div className="lbl">
        선택: <b>#{refs.item_id}</b>
      </div>
      <h4>상위 참조</h4>
      <ul>{refs.upstream.length ? refs.upstream.map((r, i) => <span key={i}>{link(r)}</span>) : <li className="lbl">없음</li>}</ul>
      <h4>하위 참조</h4>
      <ul>{refs.downstream.length ? refs.downstream.map((r, i) => <span key={i}>{link(r)}</span>) : <li className="lbl">없음 — 고립 항목</li>}</ul>
      <h4>플래그</h4>
      <ul>
        {refs.flags.length ? (
          refs.flags.map((f) => (
            <li key={f.id}>
              {FLAG_KO[f.kind] ?? f.kind}
              {f.cause && (
                <>
                  {' '}
                  · 원인{' '}
                  <Link className="ref" to={`/p/${f.cause.doc_id?.split('-')[0]}/d/${f.cause.doc_id}#item-${f.cause.item_id}`}>
                    {f.cause.doc_id}#{f.cause.item_id}
                  </Link>
                </>
              )}
              {f.assignee && <span className="lbl"> · 담당 {f.assignee.display_name}</span>}
            </li>
          ))
        ) : (
          <li className="lbl">없음</li>
        )}
      </ul>
    </>
  )
}

function Comments(props: {
  comments: Comment[]
  line: number | null
  setLine: (n: number | null) => void
  draft: string
  setDraft: (s: string) => void
  add: (parent: number | null) => void
  resolve: (c: Comment, v: boolean) => void
  lines: string[]
}) {
  const { comments, line, setLine, draft, setDraft, add, resolve, lines } = props
  const thread = (c: Comment, depth = 0) => (
    <div className={`cmt${c.is_resolved ? ' done' : ''}`} style={{ marginLeft: depth * 14 }} key={c.id}>
      <div className="lbl">
        {c.author?.display_name} · 줄 {c.line_no}
        {c.original_location && ` (원본 위치 ${c.original_location})`}
      </div>
      <div>{c.body}</div>
      <div className="cacts">
        {depth === 0 && (
          <button className="btn sm" onClick={() => resolve(c, !c.is_resolved)}>
            {c.is_resolved ? '다시 열기' : '해결됨'}
          </button>
        )}
        <button
          className="btn sm"
          onClick={() => {
            setLine(c.line_no)
            add(c.id)
          }}
          disabled={!draft.trim()}
        >
          답글로 저장
        </button>
      </div>
      {c.replies.map((r) => thread(r, depth + 1))}
    </div>
  )
  return (
    <>
      <div className="row">
        <span className="lbl">줄</span>
        <input className="inp" type="number" min={1} max={lines.length} value={line ?? ''} onChange={(e) => setLine(e.target.value ? Number(e.target.value) : null)} style={{ width: 70 }} />
        {line && <span className="lbl mono">{lines[line - 1]?.slice(0, 40)}</span>}
      </div>
      <textarea className="inp wide" rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="댓글" />
      <button className="btn" data-el="7.4" disabled={!draft.trim() || !line} onClick={() => add(null)}>
        새 댓글
      </button>
      {comments.map((c) => thread(c))}
    </>
  )
}
