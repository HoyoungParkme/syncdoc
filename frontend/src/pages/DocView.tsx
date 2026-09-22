/** UI-5 문서 뷰 — SYNC-UI-002#UI-5. 유저용(기본)·원본 탭, 목차, 오른쪽 패널(참조), 상태 토글.
 *  유저용 탭 본문은 view/*.ts(view_build.py 포트, STD-002)가 만든 HTML을 innerHTML로 넣고 mermaid를 돌린다.
 *  1 문서 바(1.1 상태, 1.2 버전) · 2 탭(2.1~2.3) · 3 상태 토글 · 4 규약 오류 · 4a 미완성
 *  12 휴지통에 넣기 · 13 휴지통 확인(13.1 무엇이 되나 · 13.2 끊어지는 것 · 13.3 넣기 · 13.4 닫기) · 4b 휴지통 배너(4b.1 되살리기)
 *  6 목차(6.1 표시된 항목, 6.2 왼쪽 손잡이) · 7 유저용 본문(7.1·7.2·7.3·7.5·7.6) · 8 패널(8.1 참조, 8.3 오른쪽 손잡이)
 *  9 단계 이동 · 10 원본(10.1 MD, 10.2 복사, 10.3 원문, 10.4 렌더링)
 *  질문 탭(8.4 탭 · 8.5 맥락 줄 · 8.6 입력 · 8.7 대화 · 8.9 진행 줄) — 카드 U·Y. 대화는 Shell이 프로젝트 단위로 든다 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams, useSearchParams } from 'react-router-dom'
import mermaid from 'mermaid'
import { api, ApiError, incompleteOf, warnText, type AskAnswer, type AskNote, type AskRead, type AskTurn, type Document, type DownstreamView, type ItemReferences, type Me, type Problem } from '../api/client'
import { extraCss, renderView } from '../view'
import { attachDiagramButtons, DiagramFull, type FullDiagram } from '../components/DiagramFull'
import { esc, renderBlocks, splitRef } from '../view/md'
import { ItemIdBadge, StatusPill, ProjName, toast } from '../components/ui'
import { Handle, PANEL, readStore, TOC, useWidth, writeStore } from '../components/panes'
import type { AskChat, AskTurnView } from '../components/Shell'


export function DocView() {
  const { code = '', docId = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const tab = sp.get('tab') === 'raw' ? 'raw' : 'user'
  const [doc, setDoc] = useState<Document | null>(null)
  const [err, setErr] = useState('')
  const [full, setFull] = useState<FullDiagram | null>(null) // 7.6
  const [selected, setSelected] = useState<string | null>(null)
  const [refs, setRefs] = useState<ItemReferences | null>(null)
  const [downstream, setDownstream] = useState<DownstreamView | null>(null)
  const [delOpen, setDelOpen] = useState(false) // 13
  const [delInfo, setDelInfo] = useState<Record<string, unknown> | null>(null) // 13.2 — 서버 답(needs-confirm)으로만 채운다
  // 8 패널 탭 — 기본은 참조. 질문 탭(8.4)은 사람이 누를 때만, URL은 ?panel=ask. 키가 없으면 탭 자체가 없다
  const { user, ask } = useOutletContext<{ user: Me; ask: AskChat }>()
  const askOn = user.llm_enabled
  const panelParam = sp.get('panel') === 'ask' ? 'ask' : 'refs'
  const setPanel = useCallback(
    (p: 'refs' | 'ask') =>
      // 함수형 갱신 — 본문 클릭 핸들러(effect 안 클로저)에서 불러도 낡은 sp를 안 쓴다
      setSp(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (p === 'ask') next.set('panel', 'ask')
          else next.delete('panel')
          return next
        },
        { replace: true },
      ),
    [setSp],
  )
  const mainRef = useRef<HTMLElement>(null)
  // 규칙: 사이드바 폭과 원문/렌더링 선택은 사람마다 기억한다. 화면을 옮겨도 유지된다
  const [tocW, addTocW] = useWidth(TOC)
  const [panelW, addPanelW] = useWidth(PANEL)
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
    for (const el of root.querySelectorAll<HTMLElement>('[data-item]:not(section.screen)')) el.dataset.el = '7.1' // 화면 섹션은 항목 헤더가 아니다
    for (const el of root.querySelectorAll<HTMLElement>('a[data-ref]')) el.dataset.el = '7.2'
    for (const el of root.querySelectorAll<HTMLElement>('pre.mermaid')) el.dataset.el = '7.3'
    mermaid.initialize({ startOnLoad: false, theme: 'neutral' })
    // 7.5 전체보기 — svg가 생긴 뒤(mermaid 끝난 뒤)에 붙인다. 그 사이 본문이 갈렸으면 붙이지 않는다 (공통 1.7)
    mermaid
      .run({ nodes: root.querySelectorAll<HTMLElement>('pre.mermaid') })
      .catch(() => undefined) // 문법 오류면 코드가 남는다 (UC-H2 2a)
      .then(() => {
        if (mainRef.current !== root) return
        for (const b of attachDiagramButtons(root, setFull)) b.dataset.el = '7.5'
      })
    // 7.1 항목 헤더에 끊어진 참조 수(있으면, 경고색)
    for (const el of root.querySelectorAll<HTMLElement>('[data-item]')) {
      const badge = el.querySelector('.iid') ?? el
      const n = doc?.items.find((i) => i.item_id === el.dataset.item)?.missing_refs.length ?? 0
      if (n && !el.querySelector('.missx')) badge.insertAdjacentHTML('afterend', `<span class="miss missx">끊어진 참조 ${n}</span>`)
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
        setPanel('refs') // 7.1 클릭은 참조 탭으로 — 질문 탭은 사람이 직접 누를 때만
      }
    }
    root.addEventListener('click', onClick)
    if (window.location.hash) {
      document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: 'start' })
      const it = window.location.hash.startsWith('#item-') ? window.location.hash.slice(6) : ''
      if (it && doc?.items.some((i) => i.item_id === it)) setSelected(it) // UI-4 다이얼로그(6) 진입 — 참조 패널을 연다
    }
    return () => {
      root.removeEventListener('click', onClick)
      if (typeof cleanup === 'function') cleanup()
    }
  }, [view, tab, doc, nav, setPanel])

  useEffect(() => {
    if (!selected) return
    api.get<ItemReferences>(`/api/docs/${docId}/items/${selected.replace(/\//g, '~')}/references`).then(setRefs).catch(() => setRefs(null))
  }, [selected, docId])

  /** 3 상태 토글 — 갈 곳이 하나라 고를 것이 없다(UC-H8). 완료로 올릴 때 서버가 `status-blocked`로 거절하면
   *  토스트에 이유 — 배너(4·4a)가 이미 말하는 값이다. 다이얼로그 없음 */
  async function toggleStatus() {
    if (!doc) return
    const to = doc.status === 'approved' ? 'draft' : 'approved'
    try {
      await api.post(`/api/docs/${docId}/status`, { to })
      load()
    } catch (e) {
      if (e instanceof ApiError && e.kind === 'status-blocked') {
        const w = (e.problem.warnings as string[] | undefined) ?? []
        toast(`완료로 못 올립니다 — ${[e.problem.convention_error_detail, ...w.map(warnText)].filter(Boolean).join(' · ') || e.message}`)
      } else alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    }
  }
  // UC-H18 — 확인(13)을 열면 confirm 없이 한 번 불러 끊어질 것을 받는다. 판정은 pipeline.trash_document 한 곳
  async function openTrash() {
    setDelInfo(null)
    setDelOpen(true)
    try {
      await api.del(`/api/docs/${docId}`)
    } catch (e) {
      if (e instanceof ApiError && e.kind === 'document-deletion-needs-confirm') setDelInfo(e.problem)
      else alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    }
  }
  async function trashDoc() {
    try {
      await api.del(`/api/docs/${docId}?confirm=true`)
      nav(`/p/${code}`)
    } catch (e) {
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    }
  }
  async function restoreDoc() {
    try {
      await api.post(`/api/docs/${docId}/restore`)
      load()
    } catch (e) {
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    }
  }

  if (err) return <div className="page banner err">{err}</div>
  if (!doc || !view) return null
  const lines = doc.body.split('\n')
  const toc = tocOf(doc)
  const marked = markedItems(doc)
  // 배너(4a)와 `완료로` 비활성이 같은 값을 본다. 끊어진 참조는 컬럼이 아니라 읽을 때 온다 (#35)
  const incomplete = incompleteOf(doc)
  // 가운데 열만 스크롤한다 — scrollIntoView는 가장 가까운 스크롤 조상을 움직인다
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ block: 'start' })
  const goItem = (id: string) => {
    scrollTo(`item-${id}`)
    setSelected(id)
  }

  return (
    // 폭 변수를 화면 전체가 쥔다 — 원본 탭도 같은 값으로 사이드바 자리를 비워 둬야
    // 탭을 오갈 때 본문이 좌우로 안 흔들린다 (UI-5 규칙)
    <div className="docscreen" style={{ '--toc-w': `${tocW}px`, '--panel-w': `${panelW}px` } as React.CSSProperties}>
      {full && <DiagramFull d={full} el="7.6" onClose={() => setFull(null)} />}
      {/* 브레드크럼 — 어디서 들어왔든 지금 자리를 말하고, 앞 두 조각으로 되짚어 올라간다 */}
      <div className="docbar" data-el="1">
        <Link className="crumb" to={`/p/${code}`}>
          <ProjName code={code} name={doc.project_name} />
        </Link>
        <span className="sep">›</span>
        <Link className="crumb mono" to={`/p/${code}#stage-${doc.stage ?? ''}`}>
          {doc.stage ? `${doc.stage} ${doc.doc_type}` : doc.doc_type}
        </Link>
        <span className="sep">›</span>
        <b className="mono">{doc.doc_id}</b>
        <StatusPill status={doc.status} el="1.1" />
        <Link className="ver mono" data-el="1.2" to={`/p/${code}/d/${docId}/history`}>
          v{doc.current_version_no}
        </Link>
        <span className="grow" />
        {/* 휴지통에 있으면 상태 토글(3)·넣기(12)가 없다 — 4b 배너 하나로 말한다 (UI-5 규칙).
            규약 오류(4)면 토글이 비활성, 미완성(4a)이면 `완료로`만 비활성 — `초안으로`는 언제나 된다 */}
        {!doc.trashed_at && (
          <button
            className="btn"
            data-el="3"
            disabled={doc.has_convention_error || (doc.status !== 'approved' && incomplete.length > 0)}
            onClick={toggleStatus}
          >
            {doc.status === 'approved' ? '초안으로' : '완료로'}
          </button>
        )}
        {!doc.trashed_at && (
          // 12 — 어떤 문서든 휴지통엔 넣을 수 있다. 되돌릴 수 있으니 문지기가 없다 (PRD N3)
          <button className="btn danger" data-el="12" onClick={openTrash}>
            휴지통에 넣기
          </button>
        )}
      </div>

      {/* 3단 틀은 탭이 바뀌어도 그대로다 — 목차·패널이 사라지면 본문이 좌우로 흔들린다 (UI-5 규칙) */}
      <div className="body3" data-el="7">
        <nav className="toc" data-el="6">
          <div className="lbl">목차</div>
          {toc.map((t) => (
            <div key={t.id} className={t.depth ? 'd1' : ''} title={t.text} onClick={() => scrollTo(t.id)}>
              {t.text}
            </div>
          ))}
          {/* 규칙: 끊어진 참조(is_missing)를 가진 항목만. 하나도 없으면 블록 자체가 안 보인다 */}
          {marked.length > 0 && (
            <div className="marked" data-el="6.1">
              <div className="lbl">표시된 항목</div>
              {marked.map((m) => (
                <div key={m.id} onClick={() => goItem(m.id)}>
                  <span className="dot dot-miss" /> {m.id} <span className="lbl">{m.label}</span>
                </div>
              ))}
            </div>
          )}
        </nav>
        <Handle el="6.2" onDrag={(dx) => addTocW(dx)} />
        <style>{extraCss}</style>

        <div className="mainwrap" data-el={tab === 'raw' ? '10' : undefined}>
          <div className="tabs" data-el="2">
            <span className={tab === 'user' ? 'on' : ''} data-el="2.1" onClick={() => setSp({})}>
              유저용
            </span>
            <span className={tab === 'raw' ? 'on' : ''} data-el="2.2" onClick={() => setSp({ tab: 'raw' })}>
              원본
            </span>
            <Link data-el="2.3" to={`/p/${code}/d/${docId}/history`}>
              이력
            </Link>
            {/* 원문/렌더링과 복사는 탭과 같은 줄. 아래로 내리면 본문이 한 줄 더 밀린다 */}
            {tab === 'raw' && (
              <>
                <span className="grow" />
                <span className="radios">
                  <span className={`radio${rawMode === 'text' ? ' on' : ''}`} data-el="10.3" onClick={() => pickRaw('text')}>
                    원문
                  </span>
                  <span className={`radio${rawMode === 'rendered' ? ' on' : ''}`} data-el="10.4" onClick={() => pickRaw('rendered')}>
                    렌더링
                  </span>
                </span>
                <button className="btn sm" data-el="10.2" onClick={() => navigator.clipboard.writeText(doc.body)}>
                  복사
                </button>
              </>
            )}
          </div>

          {/* 배너는 본문 열 안, 본문과 같은 폭. 유저용·원본 양쪽에 보인다 (UI-5 규칙) */}
          {doc.trashed_at && (
            <div className="banner warn" data-el="4b">
              휴지통에 있는 문서입니다 — {new Date(doc.trashed_at).toLocaleString()} · 파일은 저장소에 없고 되살리면 돌아옵니다{' '}
              <button className="btn sm" data-el="4b.1" onClick={restoreDoc}>
                되살리기
              </button>
            </div>
          )}
          {doc.has_convention_error && (
            <div className="banner" data-el="4">
              ⚠ 규약 오류: {doc.convention_error_detail} (커밋 {doc.commit_hash?.slice(0, 7)} · {doc.last_author?.user?.display_name})
            </div>
          )}
          {incomplete.length > 0 && (
            <div className="banner warn" data-el="4a">
              미완성: {incomplete.map(warnText).join(' · ')} · 완료 불가
            </div>
          )}

          {/* 문서 머리 — 킥커·제목·리드. 본문(7)은 innerHTML로 갈아 끼워서 형제로 둔다 */}
          {tab === 'user' && (
            <div className="dochead">
              <div className="kicker mono">
                [{code}] {doc.project_name} · {doc.stage ? `${doc.stage}단계 ${doc.doc_type}` : `단계 밖 ${doc.doc_type}`}
              </div>
              <h1>{view.title}</h1>
              {view.lead && <p className="lead">{view.lead}</p>}
            </div>
          )}
          {tab === 'user' ? (
            <article className="main body" ref={mainRef} />
          ) : rawMode === 'text' ? (
            <div className="editor" data-el="10.1">
              <div className="gutter">
                {lines.map((_, i) => (
                  <span key={i}>{i + 1}</span>
                ))}
              </div>
              <pre className="mdsrc">{doc.body}</pre>
            </div>
          ) : (
            // 같은 MD를 파싱해 그린 것. 사람용 뷰(7)가 아니라 원본을 읽은 결과라
            // frontmatter를 지우지 않고 회색 블록으로 남긴다
            <div className="rawview" data-el="10.1">
              <RawRendered doc={doc} />
            </div>
          )}

          <div className="docnav" data-el="9">
            {doc.prev_doc_id ? <Link className="btn" to={`/p/${code}/d/${doc.prev_doc_id}`}>← {doc.prev_doc_id}</Link> : <span className="btn dis">←</span>}
            <span className="grow" />
            {doc.next_doc_id ? <Link className="btn" to={`/p/${code}/d/${doc.next_doc_id}`}>{doc.next_doc_id} →</Link> : <span className="btn dis">→</span>}
          </div>
        </div>

        <Handle el="8.3" onDrag={(dx) => addPanelW(-dx)} />
        <aside className="panel" data-el="8">
          {(() => {
            const askTab = askOn && !doc.trashed_at // 키 없음·휴지통 문서(4b)면 탭이 없다
            const panel = askTab && panelParam === 'ask' ? 'ask' : 'refs'
            return (
              <>
                <div className="ptabs">
                  <span className={panel === 'refs' ? 'on' : ''} data-el="8.1" onClick={() => setPanel('refs')}>
                    참조
                  </span>
                  {askTab && (
                    <span className={panel === 'ask' ? 'on' : ''} data-el="8.4" onClick={() => setPanel('ask')}>
                      질문
                    </span>
                  )}
                </div>
                <div className="pbody">
                  {panel === 'ask' ? (
                    // 대화는 Shell이 프로젝트 단위로 든다 — 문서·항목을 옮겨도 남고, 프로젝트가 바뀌면 새 대화
                    <AskPanel
                      ask={ask}
                      docId={docId}
                      itemId={selected}
                      displayName={doc.items.find((i) => i.item_id === selected)?.display_name ?? ''}
                      goItem={goItem}
                    />
                  ) : !selected ? (
                    <div className="pempty">
                      항목을 선택하세요.
                      <br />
                      항목 헤더를 누르면 그 항목의 상위·하위 참조가 여기 옵니다.
                    </div>
                  ) : refs ? (
                    <Refs refs={refs} />
                  ) : (
                    <div className="lbl">선택: #{selected}</div>
                  )}
                </div>
              </>
            )
          })()}
        </aside>
      </div>

      {delOpen && (
        <div className="dialog narrow" data-el="13">
          <div className="dhead">휴지통에 넣기 — {doc.doc_id}</div>
          <div className="dbody">
            <p data-el="13.1">
              <b>{titleOf(doc.body)}</b> · 버전 {doc.current_version_no}개 · 파일이 저장소에서 지워집니다. 행과 이력은 남아 <b>되살릴 수 있습니다.</b>
            </p>
            {delInfo && (delInfo.inbound_refs as string[]).length > 0 && (
              <div className="banner warn" data-el="13.2">
                넣으면 끊어지는 것
                {(delInfo.inbound_refs as string[]).length > 0 && (
                  <>
                    <br />· 들어오는 참조 {(delInfo.inbound_refs as string[]).length}
                    {(delInfo.inbound_refs as string[]).map((r) => (
                      <span key={r}>
                        {' '}
                        — <a href={`/p/${r.split('-')[0]}/d/${r.split('#')[0]}${r.includes('#') ? '#item-' + r.split('#')[1] : ''}`} target="_blank" rel="noreferrer"><b>{r}</b></a>
                      </span>
                    ))}{' '}
                    → 그 참조가 <b>끊어진 참조</b>가 됩니다
                  </>
                )}
              </div>
            )}
            <div className="dacts">
              <button className="btn" data-el="13.4" onClick={() => setDelOpen(false)}>
                닫기
              </button>{' '}
              <button className="btn danger" data-el="13.3" disabled={delInfo === null} onClick={trashDoc}>
                휴지통에 넣기
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

/** 6.1 표시된 항목 — 가리키는 곳이 없는 참조를 가진 항목. 본문 순서를 지킨다 */
function markedItems(doc: Document): { id: string; label: string }[] {
  return doc.items.filter((it) => it.missing_refs.length).map((it) => ({ id: it.item_id, label: `끊어진 참조 ${it.missing_refs.length}` }))
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

/** 8.1 참조 — 선택 항목의 상위(근거)·하위(파생). 각 줄은 카드다 */
function Refs({ refs }: { refs: ItemReferences }) {
  const card = (r: ItemReferences['upstream'][number], i: number) =>
    r.is_missing ? (
      <div className="rcard missing" key={i}>
        <b className="mono">{r.raw_target}</b> <span className="miss">가리키는 곳 없음</span>
        <div className="lbl">항목이 삭제됐거나 아직 안 쓰였다</div>
      </div>
    ) : (
      <Link className="rcard" key={i} to={`/p/${r.doc_id?.split('-')[0]}/d/${r.doc_id}${r.item_id ? '#item-' + r.item_id : ''}`}>
        <b className="mono">
          {r.doc_id}
          {r.item_id ? '#' + r.item_id : ''}
        </b>
        <div className="lbl">{r.item_id ? r.display_name : '(문서 전체)'}</div>
      </Link>
    )
  return (
    <>
      <div className="lbl">선택</div>
      <div className="selitem">
        <ItemIdBadge>{refs.item_id}</ItemIdBadge>
      </div>
      <div className="lbl">상위 참조 (근거)</div>
      {refs.upstream.length ? refs.upstream.map(card) : <div className="pempty">없음</div>}
      <div className="lbl">하위 참조 (파생) {refs.downstream.length || ''}</div>
      {refs.downstream.length ? refs.downstream.map(card) : <div className="pempty">없음 — 고립 항목</div>}
    </>
  )
}

/** frontmatter title — Document DTO에 제목이 없어 본문에서 읽는다 (13.1) */
function titleOf(body: string): string {
  const fm = body.startsWith('---') ? body.slice(3).split('\n---', 1)[0] : ''
  return /^title:\s*(.*)$/m.exec(fm)?.[1]?.trim() ?? ''
}


/** 8.5 맥락 줄 · 8.6 질문 입력 · 8.7 대화(.qa · 본 것 .qsrc) · 8.9 진행 줄 — UC-H19, 카드 Y.
 *  POST /api/docs/{docId}/ask(SSE): note·read가 진행 줄에 차례로, answer가 답, error가 실패.
 *  항목은 힌트(item_id) — 안 골라도 문서 전체로 묻는다. 대화는 Shell이 프로젝트 단위로 든다 */
function AskPanel({
  ask,
  docId,
  itemId,
  displayName,
  goItem,
}: {
  ask: AskChat
  docId: string
  itemId: string | null
  displayName: string
  goItem: (id: string) => void
}) {
  const { turns, setTurns } = ask
  const [question, setQuestion] = useState('')
  const [pending, setPending] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  // 언마운트(문서·프로젝트 이동, 탭 전환)면 스트림을 끊는다 — 답은 오던 자리에 안 남는다
  useEffect(() => () => abortRef.current?.abort(), [])

  const patchLast = (f: (t: AskTurnView) => AskTurnView) =>
    setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? f(t) : t)))

  const send = async () => {
    const q = question.trim()
    if (!q || pending) return
    // history = 지금까지의 질문·답 전부(실패한 턴은 빼고). 서버가 LLM_MAX_TURNS에서 자른다
    const history: AskTurn[] = turns
      .filter((t) => t.a !== undefined)
      .flatMap((t) => [
        { role: 'user' as const, text: t.q },
        { role: 'assistant' as const, text: t.a as string },
      ])
    setQuestion('')
    setPending(true)
    setTurns((ts) => [...ts, { q, prog: [] }])
    const ac = new AbortController()
    abortRef.current = ac
    try {
      await api.stream(
        `/api/docs/${docId}/ask`,
        { question: q, history, item_id: itemId ?? undefined },
        (name, data) => {
          if (name === 'note') {
            const d = data as AskNote
            patchLast((t) => ({ ...t, prog: [...t.prog, { kind: 'note', text: d.text }] }))
          } else if (name === 'read') {
            const d = data as AskRead
            patchLast((t) => ({ ...t, prog: [...t.prog, { kind: 'read', text: d.target ? `${d.tool} ${d.target}` : d.tool }] }))
          } else if (name === 'answer') {
            const d = data as AskAnswer
            patchLast((t) => ({ ...t, a: d.answer, src: d.context_item_ids }))
          } else if (name === 'error') {
            const d = data as Problem
            patchLast((t) => ({ ...t, err: String(d.reason ?? d.detail ?? d.title) }))
          }
        },
        ac.signal,
      )
      // 스트림이 answer도 error도 없이 닫혔다
      patchLast((t) => (t.a === undefined && t.err === undefined ? { ...t, err: '답 없이 끊겼습니다' } : t))
    } catch (e) {
      if (ac.signal.aborted) return
      const reason = e instanceof ApiError ? String(e.problem.reason ?? e.message) : String(e)
      patchLast((t) => ({ ...t, err: reason }))
    } finally {
      if (abortRef.current === ac) abortRef.current = null
      setPending(false)
    }
  }

  const srcLink = (id: string) => {
    // 본 것의 ID → 7.2와 같음. 이 문서 안 항목이면 스크롤·선택, 남의 문서·문서 자체면 링크
    const [d, it] = id.includes('#') ? [id.split('#')[0], id.split('#')[1]] : [id, '']
    if (d === docId && it) {
      return (
        <a key={id} href={`#item-${it}`} onClick={(e) => { e.preventDefault(); goItem(it) }}>
          {it}
        </a>
      )
    }
    return (
      <Link key={id} to={`/p/${d.split('-')[0]}/d/${d}${it ? '#item-' + it : ''}`}>
        {id}
      </Link>
    )
  }

  return (
    <>
      <div className="lbl" data-el="8.5">
        {itemId ? (
          <>
            <b className="mono">{itemId}</b> {displayName} · 이 항목을 보며 묻습니다
          </>
        ) : (
          <>
            문서 전체 · <b className="mono">{docId}</b>에 대해 묻습니다
          </>
        )}
      </div>
      <div className="qa" data-el="8.7">
        {turns.map((t, i) => (
          <div key={i} className="turn">
            <div className="q">{t.q}</div>
            {t.prog.length > 0 && (
              <div className={'qprog' + (t.a !== undefined || t.err ? ' done' : '')} data-el="8.9">
                {t.prog.map((pg, k) => (
                  <div key={k} className={pg.kind}>
                    {pg.kind === 'read' ? '읽음 · ' : ''}
                    {pg.text}
                  </div>
                ))}
              </div>
            )}
            {t.a !== undefined ? (
              <>
                <div className="a">{t.a}</div>
                {t.src && t.src.length > 0 && (
                  <div className="qsrc">
                    본 것:{' '}
                    {t.src.map((id, k) => (
                      <span key={id}>
                        {k > 0 && ' · '}
                        {srcLink(id)}
                      </span>
                    ))}
                  </div>
                )}
              </>
            ) : t.err ? (
              <div className="a fail">답을 못 받았습니다 — {t.err}</div>
            ) : (
              <div className="a wait">{t.prog.length ? '읽는 중…' : '답을 기다리는 중…'}</div>
            )}
          </div>
        ))}
      </div>
      <textarea
        data-el="8.6"
        value={question}
        disabled={pending}
        placeholder={itemId ? '이 항목을 보며 묻습니다 — Enter로 보냅니다' : '이 문서에 대해 묻습니다 — Enter로 보냅니다'}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            void send()
          }
        }}
      />
    </>
  )
}
