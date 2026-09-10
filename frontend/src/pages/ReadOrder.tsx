/** UI-9 순서대로 읽기 — SYNC-UI-002#UI-9. 승인 문서만, 없으면 배너(3)와 초안 보기(3.1). 요소 번호 = data-el.
 *  1 헤더 · 2 단계 표시(칩마다 대표 상태 점, 현재는 채워서) · 3 미확정 배너(3.1)
 *  4 본문(4.1 위치) · 5 이동(5.1 이전, 5.2 다음, 5.3 이 문서 열기) */
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import mermaid from 'mermaid'
import { api, docPath, STAGE_NAMES, STAGE_TYPES, STATUS_KO, type Document, type DocumentSummary } from '../api/client'
import { extraCss, renderView } from '../view'
import { splitRef } from '../view/md'

const ORDER: Record<string, number> = { draft: 0, review: 1, approved: 2 }

export function ReadOrder() {
  const { code = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const stage = Number(sp.get('stage') ?? '1')
  const [docs, setDocs] = useState<DocumentSummary[]>([])
  const [showDraft, setShowDraft] = useState(false)
  const [bodies, setBodies] = useState<Document[]>([])
  const mainRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    api.get<DocumentSummary[]>(`/api/projects/${code}/docs`).then(setDocs)
  }, [code])
  const inStage = docs.filter((d) => d.stage === stage).sort((a, b) => (a.doc_id < b.doc_id ? -1 : 1))
  const approved = inStage.filter((d) => d.status === 'approved')
  const shown = approved.length ? approved : showDraft ? inStage : []
  const key = shown.map((d) => d.doc_id).join(',')
  useEffect(() => {
    setShowDraft(false)
  }, [stage])
  useEffect(() => {
    if (!key) {
      setBodies([])
      return
    }
    Promise.all(key.split(',').map((id) => api.get<Document>(`/api/docs/${id}`))).then(setBodies)
  }, [key])
  useEffect(() => {
    const root = mainRef.current
    if (!root) return
    root.innerHTML = bodies.map((d) => `<div class="lbl" data-el="4.1">${stage} / 11 · ${STAGE_NAMES[STAGE_TYPES[stage - 1]] ?? ''} · ${d.doc_id} · ${STATUS_KO[d.status]} v${d.current_version_no}</div>` + renderView(d, code).html).join('<hr/>')
    mermaid.initialize({ startOnLoad: false, theme: 'neutral' })
    mermaid.run({ nodes: root.querySelectorAll<HTMLElement>('pre.mermaid') }).catch(() => undefined)
    const onClick = (ev: MouseEvent) => {
      const a = (ev.target as HTMLElement).closest<HTMLAnchorElement>('a[data-ref]')
      if (!a) return
      ev.preventDefault()
      const [d, it] = splitRef(a.dataset.ref ?? '')
      nav(docPath(d, it || undefined)) // 규칙: 안에서 점프하지 않고 UI-5로
    }
    root.addEventListener('click', onClick)
    return () => root.removeEventListener('click', onClick)
  }, [bodies, code, nav, stage])
  const hasDocs = (s: number) => docs.some((d) => d.stage === s)
  /** 그 단계 문서들 중 가장 낮은 상태. 승인 2 + 초안 1이면 초안 (UC-H14 1a와 같은 기준) */
  const stageStatus = (s: number) =>
    docs
      .filter((d) => d.stage === s)
      .map((d) => d.status)
      .sort((a, b) => ORDER[a] - ORDER[b])[0] ?? null
  /** 문서 없는 단계는 건너뛴다. 갈 곳이 없으면 null — 버튼을 비활성으로 둔다 */
  const target = (dir: 1 | -1): number | null => {
    let s = stage + dir
    while (s >= 1 && s <= 11 && !hasDocs(s)) s += dir
    return s >= 1 && s <= 11 ? s : null
  }
  const prev = target(-1)
  const nextStage = target(1)
  const go = (s: number | null) => s !== null && setSp({ stage: String(s) })
  const label = (s: number | null) => (s === null ? '' : `${s} ${STAGE_TYPES[s - 1]}`)
  return (
    <div className="page">
      <div className="phead" data-el="1">
        <div>
          <b>순서대로 읽기</b> <span className="lbl">{code}</span>
        </div>
        <span className="grow" />
        <div className="steps" data-el="2">
          {STAGE_TYPES.map((t, i) => {
            const s = i + 1
            const st = stageStatus(s)
            // 번호와 타입 코드는 늘 보인다. 상태는 점 하나로 — 칩 색을 상태에 쓰면
            // '현재 단계'와 '상태'가 같은 색을 두고 다툰다
            return (
              <span
                key={t}
                className={`stp${st ? '' : ' na'}${s === stage ? ' cur' : ''}`}
                onClick={() => hasDocs(s) && setSp({ stage: String(s) })}
              >
                <i className={`dot dot-${st ?? 'none'}`} />
                {s} {t}
              </span>
            )
          })}
        </div>
      </div>
      <div className="readbody">
        {approved.length === 0 && inStage.length > 0 && (
          <div className="banner warn" data-el="3">
            이 단계에 승인된 문서가 없습니다. {inStage.map((d) => `${d.doc_id}은(는) ${STATUS_KO[d.status]}`).join(', ')}입니다.{' '}
            {!showDraft && (
              <span className="btn sm" data-el="3.1" onClick={() => setShowDraft(true)}>
                초안 보기
              </span>
            )}
          </div>
        )}
        {inStage.length === 0 && <div className="banner warn">이 단계에는 문서가 없습니다.</div>}
        <style>{extraCss}</style>
        <article className="main body" data-el="4">
          <div ref={mainRef} />
          <div className="docnav" data-el="5">
            <span className={`btn${prev === null ? ' dis' : ''}`} data-el="5.1" onClick={() => go(prev)}>
              ← {prev === null ? '처음' : label(prev)}
            </span>
            {shown[0] && (
              <span className="btn" data-el="5.3" onClick={() => nav(docPath(shown[0].doc_id))}>
                이 문서 열기
              </span>
            )}
            <span className={`btn${nextStage === null ? ' dis' : ''}`} data-el="5.2" onClick={() => go(nextStage)}>
              {nextStage === null ? '끝' : label(nextStage)} →
            </span>
          </div>
        </article>
      </div>
    </div>
  )
}
