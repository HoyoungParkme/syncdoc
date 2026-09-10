/** UI-5 문서 뷰 — SYNC-UI-002#UI-5. 유저용(기본)·원본 탭, 목차, 오른쪽 패널(참조·댓글), 상태 변경 + 상위 대조 다이얼로그.
 *  유저용 탭 본문은 view/*.ts(view_build.py 포트, STD-002)가 만든 HTML을 innerHTML로 넣고 mermaid를 돌린다.
 *  1 문서 바(1.1 상태, 1.2 버전) · 2 탭(2.1~2.3) · 3 상태 변경 · 4 규약 오류 · 4a 미완성 · 5 미해결 댓글
 *  6 목차(6.1 표시된 항목, 6.2 왼쪽 손잡이) · 7 유저용 본문(7.1~7.4) · 8 패널(8.1 참조, 8.2 댓글, 8.3 오른쪽 손잡이)
 *  9 단계 이동 · 10 원본(10.1 MD, 10.2 복사, 10.3 원문, 10.4 렌더링) · 11 상위 대조(11.1~11.4) */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import mermaid from 'mermaid'
import { api, ApiError, FLAG_KO, STATUS_KO, type Comment, type Document, type DownstreamView, type ItemReferences, type UpstreamCheck } from '../api/client'
import { extraCss, renderView } from '../view'
import { esc, renderBlocks, splitRef } from '../view/md'
import { StatusPill } from '../components/ui'


export function DocView() {
  const { code = '', docId = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const tab = sp.get('tab') === 'raw' ? 'raw' : 'user'
  const [doc, setDoc] = useState<Document | null>(null)
  const [err, setErr] = useState('')
  const [panel, setPanel] = useState<'refs' | 'comments'>(sp.get('panel') === 'comments' ? 'comments' : 'refs')
  const [selected, setSelected] = useState<string | null>(null)
  const [refs, setRefs] = useState<ItemReferences | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [downstream, setDownstream] = useState<DownstreamView | null>(null)
  const [line, setLine] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [statusOpen, setStatusOpen] = useState(false)
  const [upstream, setUpstream] = useState<UpstreamCheck[] | null>(null)
  const [mismatch, setMismatch] = useState<Set<string>>(new Set())
  const [reason, setReason] = useState('')
  const mainRef = useRef<HTMLElement>(null)
  // 규칙: 사이드바 폭과 원문/렌더링 선택은 사람마다 기억한다. 화면을 옮겨도 유지된다
  const [tocW, addTocW] = useWidth('syncdoc.ui5.toc', 200, 140, 400)
  const [panelW, addPanelW] = useWidth('syncdoc.ui5.panel', 300, 180, 460)
  const [rawMode, setRawMode] = useState<'text' | 'rendered'>(() => (readStore('syncdoc.ui5.raw') === 'rendered' ? 'rendered' : 'text'))
  const pickRaw = (m: 'text' | 'rendered') => {
    setRawMode(m)
    writeStore('syncdoc.ui5.raw', m)
  }

  const load = useCallback(() => {
    api
      .get<Document>(`/api/docs/${docId}`)
      .then(setDoc)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)))
    api.get<Comment[]>(`/api/docs/${docId}/comments`).then(setComments)
    api.get<DownstreamView>(`/api/docs/${docId}/downstream`).then(setDownstream).catch(() => setDownstream(null))
  }, [docId])
  useEffect(() => {
    setSelected(null)
    setRefs(null)
    load()
  }, [load])

  const view = useMemo(() => (doc ? renderView(doc, code, downstream) : null), [doc, code, downstream])

  // 유저용 본문: innerHTML → onMount → mermaid → 항목 클릭·참조 링크·해시 스크롤
  useEffect(() => {
    const root = mainRef.current
    if (!root || !view || tab !== 'user') return
    root.innerHTML = view.html
    const cleanup = view.onMount?.(root)
    // 와이어프레임 요소 번호 (DEV-17) — 뷰 포트 HTML은 view_build와 같아야 하므로 여기서 붙인다
    for (const el of root.querySelectorAll<HTMLElement>('[data-item]')) el.dataset.el = '7.1'
    for (const el of root.querySelectorAll<HTMLElement>('a[data-ref]')) el.dataset.el = '7.2'
    for (const el of root.querySelectorAll<HTMLElement>('pre.mermaid')) el.dataset.el = '7.3'
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
    if (window.location.hash) {
      document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: 'start' })
      const it = window.location.hash.startsWith('#item-') ? window.location.hash.slice(6) : ''
      if (it && doc?.items.some((i) => i.item_id === it)) setSelected(it) // 내 할 일 3.1·7.1 진입 — 패널에 플래그 정보
      const ln = /^#line-(\d+)$/.exec(window.location.hash)
      if (ln) {
        setLine(Number(ln[1])) // 내 할 일 6.1 진입 — ?panel=comments#line-N
        setPanel('comments')
      }
    }
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
  const marked = markedItems(doc, comments)
  const goItem = (id: string) => {
    document.getElementById(`item-${id}`)?.scrollIntoView({ block: 'start' })
    setSelected(id)
    setPanel('refs')
  }

  return (
    // 폭 변수를 화면 전체가 쥔다 — 원본 탭도 같은 값으로 사이드바 자리를 비워 둬야
    // 탭을 오갈 때 본문이 좌우로 안 흔들린다 (UI-5 규칙)
    <div className="docscreen" style={{ '--toc-w': `${tocW}px`, '--panel-w': `${panelW}px` } as React.CSSProperties}>
      <div className="docbar" data-el="1">
        <span>
          <b>{doc.doc_id}</b> ·{' '}
          <StatusPill status={doc.status} el="1.1" />{' '}
          ·{' '}
          <Link data-el="1.2" to={`/p/${code}/d/${docId}/history`}>
            v{doc.current_version_no}
          </Link>
        </span>
        <span className="tabs" data-el="2">
          <span className={tab === 'user' ? 'on' : ''} data-el="2.1" onClick={() => setSp({})}>
            유저용
          </span>
          <span className={tab === 'raw' ? 'on' : ''} data-el="2.2" onClick={() => setSp({ tab: 'raw' })}>
            원본
          </span>
          <Link data-el="2.3" to={`/p/${code}/d/${docId}/history`}>
            이력
          </Link>
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
            {/* 규칙: 플래그·미해결 댓글이 붙은 항목만. 하나도 없으면 블록 자체가 안 보인다 */}
            {marked.length > 0 && (
              <div className="marked" data-el="6.1">
                <div className="lbl">표시된 항목</div>
                {marked.map((m) => (
                  <div key={m.id} onClick={() => goItem(m.id)}>
                    <span className={`dot ${m.kind}`} /> {m.id} <span className="lbl">{m.label}</span>
                  </div>
                ))}
              </div>
            )}
          </nav>
          <Handle el="6.2" onDrag={(dx) => addTocW(dx)} />
          <style>{extraCss}</style>
          <article className="main body" ref={mainRef} />
          <Handle el="8.3" onDrag={(dx) => addPanelW(-dx)} />
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
          <div className="rawinner">
            <div className="rawbar">
              <span className="lbl">에이전트가 읽는 원본 그대로 · 읽기 전용</span>
              <span className="grow" />
              <span className={`radio${rawMode === 'text' ? ' on' : ''}`} data-el="10.3" onClick={() => pickRaw('text')}>
                원문
              </span>
              <span className={`radio${rawMode === 'rendered' ? ' on' : ''}`} data-el="10.4" onClick={() => pickRaw('rendered')}>
                렌더링
              </span>
              <button className="btn" data-el="10.2" onClick={() => navigator.clipboard.writeText(doc.body)}>
                복사
              </button>
            </div>
            {rawMode === 'text' ? (
              <div className="editor" data-el="10.1">
                <div className="gutter">
                  {lines.map((_, i) => (
                    <span key={i}>{i + 1}</span>
                  ))}
                </div>
                <pre className="code">{doc.body}</pre>
              </div>
            ) : (
              // 같은 MD를 파싱해 그린 것. 사람용 뷰(7)가 아니라 원본을 읽은 결과라
              // frontmatter를 지우지 않고 회색 블록으로 남긴다
              <div className="rawview" data-el="10.1">
                <RawRendered doc={doc} />
              </div>
            )}
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
    </div>
  )
}

/** 10.4 렌더링 — 원본 MD를 그대로 파싱한 결과. frontmatter는 회색 블록으로 남긴다.
 *  유저용 탭(7)과 다른 점: 참조를 링크로 잇지 않는다. 원본을 읽는 화면이라 이동이 목적이 아니다 */
function RawRendered({ doc }: { doc: Document }) {
  const m = /^---\n([\s\S]*?)\n---\n?/.exec(doc.body)
  const front = m ? m[1] : ''
  const rest = m ? doc.body.slice(m[0].length) : doc.body
  const ctx = { selfId: doc.doc_id, href: () => '', exists: () => true }
  return (
    <>
      {front && <pre className="front">{front}</pre>}
      <div className="body" dangerouslySetInnerHTML={{ __html: renderBlocks(rest, ctx) }} />
    </>
  )
}

/** 6.1 표시된 항목 — 플래그가 붙은 항목과 미해결 댓글이 달린 항목. 본문 순서를 지킨다 */
function markedItems(doc: Document, comments: Comment[]): { id: string; kind: string; label: string }[] {
  const owner = itemOfLine(doc)
  const cm = new Map<string, number>()
  for (const c of comments) {
    if (c.is_resolved) continue
    const id = owner(c.line_no)
    if (id) cm.set(id, (cm.get(id) ?? 0) + 1)
  }
  const out: { id: string; kind: string; label: string }[] = []
  for (const it of doc.items) {
    const n = cm.get(it.item_id) ?? 0
    if (it.flags.length) out.push({ id: it.item_id, kind: 'flag', label: it.flags.map((f) => FLAG_KO[f] ?? f).join(' · ') })
    else if (n) out.push({ id: it.item_id, kind: 'cm', label: `미해결 댓글 ${n}` })
  }
  return out
}

/** 줄 번호 → 그 줄이 속한 항목 ID. 댓글은 줄에 붙고 표시된 항목(6.1)은 항목 단위라 이어 줘야 한다 */
function itemOfLine(doc: Document): (line: number) => string | null {
  const ids = new Set(doc.items.map((i) => i.item_id))
  const owner: (string | null)[] = []
  let cur: string | null = null
  let inCode = false
  for (const l of doc.body.split('\n')) {
    if (l.startsWith('```')) inCode = !inCode
    const h = inCode ? null : /^#{2,6} (.+)$/.exec(l)
    if (h) {
      const tok = h[1].split(' ')[0]
      cur = ids.has(tok) ? tok : null // 항목이 아닌 절 헤딩을 만나면 앞 항목이 끝난다
    }
    owner.push(cur)
  }
  return (line: number) => owner[line - 1] ?? null
}

/** localStorage는 사파리 프라이빗 모드 등에서 던진다. 기억은 편의라 실패해도 화면은 떠야 한다 */
function readStore(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function writeStore(key: string, v: string): void {
  try {
    localStorage.setItem(key, v)
  } catch {
    /* 기억만 못 할 뿐이다 */
  }
}

/** 손잡이가 끄는 폭. 저장해 둔 값이 명세 범위 밖일 수 있어 잘라 넣는다.
 *  **더하기는 반드시 함수형으로.** mousemove 리스너는 mousedown 때 한 번 만들어지므로
 *  바깥 값을 그대로 읽으면 드래그 내내 같은 시작값에 마지막 증분만 더해진다 */
function useWidth(key: string, init: number, min: number, max: number) {
  const [w, setW] = useState(() => {
    const v = Number(readStore(key))
    return Number.isFinite(v) && v > 0 ? Math.min(max, Math.max(min, v)) : init
  })
  const add = (dx: number) =>
    setW((prev) => {
      const v = Math.min(max, Math.max(min, prev + dx))
      writeStore(key, String(v))
      return v
    })
  return [w, add] as const
}

/** 세로 손잡이. 드래그하는 동안만 window에 붙는다 — 놓으면 떼어 낸다 */
function Handle({ el, onDrag }: { el: string; onDrag: (dx: number) => void }) {
  const down = (e: React.MouseEvent) => {
    e.preventDefault()
    let last = e.clientX
    const move = (m: MouseEvent) => {
      onDrag(m.clientX - last)
      last = m.clientX
    }
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none' // 끄는 동안 본문이 선택되지 않게
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }
  return <div className="handle" data-el={el} onMouseDown={down} />
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
      <li className="ref missing">
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
