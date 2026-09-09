/** UI-10 내 할 일 — SYNC-UI-002#UI-10. 일곱 묶음, 경과일순. 요소 번호 = data-el.
 *  1 헤더(1.1 총 건수) · 2 확인 필요(2.1 행) · 3 끊어진 참조(3.1) · 9 하위 불일치(9.1) · 4 전파 미결정(4.1)
 *  · 5 규약 오류(5.1) · 6 미해결 댓글(6.1) · 7 담당 미지정(7.1) · 8 빈 상태. 4.1은 UI-12 다이얼로그. */
import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { age, api, docPath, FLAG_KO, refKey, type FlagSummary, type Todo as TodoData } from '../api/client'
import { DecisionDialog } from '../components/DecisionDialog'

export function Todo() {
  const nav = useNavigate()
  const [t, setT] = useState<TodoData | null>(null)
  const [decision, setDecision] = useState<number | null>(null)
  const load = useCallback(() => {
    api.get<TodoData>('/api/todo').then(setT)
  }, [])
  useEffect(load, [load])
  if (!t) return null

  const openFlag = (f: FlagSummary) => {
    if (f.kind === 'broken_ref') nav(docPath(f.target.doc_id, f.target.item_id)) // 3.1 → UI-5 해당 항목, 패널에 플래그 정보
    else nav(`/todo/flags/${f.id}`) // 2.1 · 9.1 → UI-11
  }
  const flagRow = (f: FlagSummary, el?: string) => (
    <div className="row link" data-el={el} key={f.id} onClick={() => openFlag(f)}>
      <span className="k">{refKey(f.target)}</span> {f.target.display_name}
      <span className="lbl">
        {f.kind === 'needs_check' && `원인 ${refKey(f.cause)} v${f.cause_version_no ?? '?'}`}
        {f.kind === 'broken_ref' && `→ ${refKey(f.cause)} (삭제됨)`}
        {f.kind === 'upstream_impact' && `← ${f.cause ? refKey(f.cause) : '하위 문서'} 이(가) 어긋남 지목`}
        {el === '7.1' && ` · ${FLAG_KO[f.kind]}`}
      </span>
      <span className="grow" />
      <span className="age">{age(f.raised_at)}</span>
    </div>
  )
  const empty = t.total === 0 && t.unassigned.length === 0
  return (
    <div className="page">
      <div className="phead" data-el="1">
        <div>
          <b>내 할 일</b>{' '}
          <span className="lbl" data-el="1.1">
            {t.total}건 · 경과일순
          </span>
        </div>
      </div>
      <div className="todo">
        <Group el="2" elRow="2.1" title="확인 필요" rows={t.needs_check} row={flagRow} />
        <Group el="3" elRow="3.1" title="끊어진 참조" rows={t.broken_ref} row={flagRow} />
        <Group el="9" elRow="9.1" title="하위 불일치" rows={t.upstream_impact} row={flagRow} />
        {t.pending_decisions.length > 0 && (
          <section className="grp" data-el="4">
            <h4>
              전파 미결정 <span className="cnt">{t.pending_decisions.length}</span>
            </h4>
            {t.pending_decisions.map((p, i) => (
              <div className="row link" data-el={i === 0 ? '4.1' : undefined} key={p.version_id} onClick={() => setDecision(p.version_id)}>
                <span className="k">{p.doc_id}</span> v{p.version_no}
                <span className="lbl">
                  {p.message.split('\n')[0]} · 하위 {p.affected_count}건
                </span>
                <span className="grow" />
                <span className="age">{age(p.created_at)}</span>
              </div>
            ))}
          </section>
        )}
        {t.convention_errors.length > 0 && (
          <section className="grp" data-el="5">
            <h4>
              규약 오류 <span className="cnt">{t.convention_errors.length}</span>
            </h4>
            {t.convention_errors.map((d, i) => (
              <div className="row link" data-el={i === 0 ? '5.1' : undefined} key={d.doc_id} onClick={() => nav(docPath(d.doc_id))}>
                <span className="k">{d.doc_id}</span>
                <span className="lbl">v{d.current_version_no} · 규약 오류 (배너에 상세)</span>
                <span className="grow" />
                <span className="age">{age(d.updated_at)}</span>
              </div>
            ))}
          </section>
        )}
        {t.unresolved_comments.length > 0 && (
          <section className="grp" data-el="6">
            <h4>
              미해결 댓글 <span className="cnt">{t.unresolved_comments.length}</span>
            </h4>
            {t.unresolved_comments.map((c, i) => (
              <div className="row link" data-el={i === 0 ? '6.1' : undefined} key={c.id} onClick={() => nav(`${docPath(c.doc_id)}?panel=comments#line-${c.line_no}`)}>
                <span className="k">{c.doc_id}</span> {c.line_no}행
                <span className="lbl">
                  {c.author?.display_name}: {c.excerpt}
                </span>
                <span className="grow" />
                <span className="age">{age(c.created_at)}</span>
              </div>
            ))}
          </section>
        )}
        <Group el="7" elRow="7.1" title="담당 미지정" rows={t.unassigned} row={flagRow} dim />
        {empty && (
          <div className="empty" data-el="8">
            처리할 일이 없습니다
          </div>
        )}
      </div>
      {decision !== null && (
        <DecisionDialog
          versionId={decision}
          onClose={(decided) => {
            setDecision(null)
            if (decided) load()
          }}
        />
      )}
    </div>
  )
}

/** 플래그 묶음 (2·3·9·7). 0건이면 제목까지 숨긴다. 번호는 첫 행에만 — 배치 HTML과 같게 */
function Group(props: {
  el: string
  elRow: string
  title: string
  rows: FlagSummary[]
  row: (f: FlagSummary, el?: string) => React.ReactNode
  dim?: boolean
}) {
  const { el, elRow, title, rows, row, dim } = props
  if (rows.length === 0) return null
  return (
    <section className={`grp${dim ? ' dim' : ''}`} data-el={el}>
      <h4>
        {title} <span className="cnt">{rows.length}</span>
      </h4>
      {rows.map((f, i) => row(f, i === 0 ? elRow : undefined))}
    </section>
  )
}
