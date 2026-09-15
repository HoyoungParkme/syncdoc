/** UI-10 내 할 일 — SYNC-UI-002#UI-10. 일곱 묶음, 경과일순. 요소 번호 = data-el.
 *  1 헤더(1.1 총 건수) · 2 확인 필요(2.1 행) · 3 끊어진 참조(3.1) · 9 하위 불일치(9.1) · 4 전파 미결정(4.1)
 *  · 5 규약 오류(5.1) · 6 미해결 댓글(6.1) · 7 담당 미지정(7.1) · 8 빈 상태. 4.1은 UI-12 다이얼로그.
 *  10 프로젝트 칩(10.1) · 11 프로젝트 묶음(11.1 머리) — **프로젝트가 둘 이상일 때만.** 하나면 예전 화면 그대로. */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { age, api, docPath, FLAG_KO, refKey, type FlagSummary, type ProjectSummary, type Todo as TodoData } from '../api/client'
import { DecisionDialog } from '../components/DecisionDialog'
import { ProjName } from '../components/ui'

type Part = { code: string; name: string; total: number; oldest: number; d: TodoData }
/** 문서 ID 접두가 프로젝트 코드다. 플래그 대상은 doc_id가 비고 raw_target만 있을 수 있다(미존재 참조) */
const codeOf = (docId: string | null | undefined, raw?: string) => (docId ?? raw ?? '').split('-')[0] || '?'
const ts = (s: string) => new Date(s).getTime()

/** 일곱 묶음을 프로젝트별로 가른다. 코드는 문서 ID 접두에서 — API는 그대로다.
 *  순서는 그 안 **가장 오래된 일** 순 — 경과일순이 묶음 사이에도 성립한다(UI-10 규칙) */
function partition(t: TodoData, projects: ProjectSummary[]): Part[] {
  const map = new Map<string, Part>()
  const at = (code: string) => {
    let p = map.get(code)
    if (!p) {
      p = {
        code,
        name: projects.find((x) => x.code === code)?.name ?? '',
        total: 0,
        oldest: Infinity,
        d: { needs_check: [], broken_ref: [], upstream_impact: [], pending_decisions: [], convention_errors: [], unresolved_comments: [], unassigned: [], total: 0 },
      }
      map.set(code, p)
    }
    return p
  }
  const seen = (p: Part, when: string | null, counts: boolean) => {
    if (when) p.oldest = Math.min(p.oldest, ts(when))
    if (counts) p.total += 1
  }
  for (const k of ['needs_check', 'broken_ref', 'upstream_impact'] as const)
    for (const f of t[k]) {
      const p = at(codeOf(f.target.doc_id, f.target.raw_target))
      p.d[k].push(f)
      seen(p, f.raised_at, true)
    }
  for (const x of t.pending_decisions) {
    const p = at(codeOf(x.doc_id))
    p.d.pending_decisions.push(x)
    seen(p, x.created_at, true)
  }
  for (const x of t.convention_errors) {
    const p = at(codeOf(x.doc_id))
    p.d.convention_errors.push(x)
    seen(p, x.updated_at, true)
  }
  for (const x of t.unresolved_comments) {
    const p = at(codeOf(x.doc_id))
    p.d.unresolved_comments.push(x)
    seen(p, x.created_at, true)
  }
  for (const f of t.unassigned) {
    const p = at(codeOf(f.target.doc_id, f.target.raw_target))
    p.d.unassigned.push(f)
    seen(p, f.raised_at, false) // 담당 미지정은 건수에 안 들어간다(1.1) — 순서에는 든다
  }
  for (const p of map.values()) p.d.total = p.total
  return [...map.values()].sort((a, b) => a.oldest - b.oldest)
}

export function Todo() {
  const nav = useNavigate()
  const { projects } = useOutletContext<{ projects: ProjectSummary[] }>()
  const [t, setT] = useState<TodoData | null>(null)
  const [decision, setDecision] = useState<number | null>(null)
  const [filter, setFilter] = useState<string | null>(null) // 10.1 — null이 전체
  const load = useCallback(() => {
    api.get<TodoData>('/api/todo').then(setT)
  }, [])
  useEffect(load, [load])
  const parts = useMemo(() => (t ? partition(t, projects) : []), [t, projects])
  if (!t) return null

  const openFlag = (f: FlagSummary) => {
    if (f.kind === 'broken_ref') nav(docPath(f.target.doc_id, f.target.item_id)) // 3.1 → UI-5 해당 항목, 패널에 플래그 정보
    else nav(`/todo/flags/${f.id}`) // 2.1 · 9.1 → UI-11
  }
  // 카드 하나가 할 일 하나다. 첫 줄은 무엇인지, 둘째 줄은 왜 왔는지
  const flagRow = (f: FlagSummary, el?: string) => (
    <div className="tcard" data-el={el} key={f.id} onClick={() => openFlag(f)}>
      <div className="th">
        <span className="k">{refKey(f.target)}</span>
        <span className="tt">{f.target.display_name}</span>
        <span className="grow" />
        <span className="age">{age(f.raised_at)}</span>
      </div>
      <div className="why">
        {f.kind === 'needs_check' && `원인 ${refKey(f.cause)} v${f.cause_version_no ?? '?'}`}
        {f.kind === 'broken_ref' && `→ ${refKey(f.cause)} (삭제됨)`}
        {f.kind === 'upstream_impact' && `← ${f.cause ? refKey(f.cause) : '하위 문서'} 이(가) 어긋남 지목`}
        {el === '7.1' && ` · ${FLAG_KO[f.kind]}`}
      </div>
    </div>
  )
  /** 종류 묶음 일곱. 번호는 첫 프로젝트 묶음(또는 프로젝트 하나일 때)에만 — 배치 HTML과 같게 */
  const groups = (d: TodoData, first: boolean) => (
    <>
      <Group el="2" elRow="2.1" first={first} title="확인 필요" rows={d.needs_check} row={flagRow} />
      <Group el="3" elRow="3.1" first={first} title="끊어진 참조" rows={d.broken_ref} row={flagRow} />
      <Group el="9" elRow="9.1" first={first} title="하위 불일치" rows={d.upstream_impact} row={flagRow} />
      {d.pending_decisions.length > 0 && (
        <section className="tgroup" data-el={first ? '4' : undefined}>
          <GroupHead title="전파 미결정" n={d.pending_decisions.length} />
          {d.pending_decisions.map((p, i) => (
            <div className="tcard" data-el={first && i === 0 ? '4.1' : undefined} key={p.version_id} onClick={() => setDecision(p.version_id)}>
              <div className="th">
                <span className="k">{p.doc_id}</span>
                <span className="tt">v{p.version_no}</span>
                <span className="grow" />
                <span className="age">{age(p.created_at)}</span>
              </div>
              <div className="why">
                {p.message.split('\n')[0]} · 하위 {p.affected_count}건
              </div>
            </div>
          ))}
        </section>
      )}
      {d.convention_errors.length > 0 && (
        <section className="tgroup" data-el={first ? '5' : undefined}>
          <GroupHead title="규약 오류" n={d.convention_errors.length} />
          {d.convention_errors.map((x, i) => (
            <div className="tcard" data-el={first && i === 0 ? '5.1' : undefined} key={x.doc_id} onClick={() => nav(docPath(x.doc_id))}>
              <div className="th">
                <span className="k">{x.doc_id}</span>
                <span className="tt">v{x.current_version_no}</span>
                <span className="grow" />
                <span className="age">{age(x.updated_at)}</span>
              </div>
              <div className="why">규약 오류 · 문서 배너에 상세</div>
            </div>
          ))}
        </section>
      )}
      {d.unresolved_comments.length > 0 && (
        <section className="tgroup" data-el={first ? '6' : undefined}>
          <GroupHead title="미해결 댓글" n={d.unresolved_comments.length} />
          {d.unresolved_comments.map((c, i) => (
            <div className="tcard" data-el={first && i === 0 ? '6.1' : undefined} key={c.id} onClick={() => nav(`${docPath(c.doc_id)}?panel=comments#line-${c.line_no}`)}>
              <div className="th">
                <span className="k">{c.doc_id}</span>
                <span className="tt">{c.line_no}행</span>
                <span className="grow" />
                <span className="age">{age(c.created_at)}</span>
              </div>
              <div className="why">
                {c.author?.display_name}: {c.excerpt}
              </div>
            </div>
          ))}
        </section>
      )}
      <Group el="7" elRow="7.1" first={first} title="담당 미지정" rows={d.unassigned} row={flagRow} dim note="누구 것도 아니라 모두에게 보인다 · 배지에는 안 들어간다" />
    </>
  )
  const empty = t.total === 0 && t.unassigned.length === 0
  const multi = parts.length > 1 // 규칙: 프로젝트가 둘 이상일 때만 칩(10)과 묶음(11)
  const shown = filter ? parts.filter((p) => p.code === filter) : parts
  return (
    <div className="page todopage">
      <div className="thead" data-el="1">
        <b>
          내 할 일 <span className="cnt">{t.total}</span>
        </b>
        {/* 알림을 따로 두지 않는다는 결정이 이 줄에 적혀 있어야 한다 */}
        <div className="lbl" data-el="1.1">
          {t.total}건 · 경과일순 · 알림은 없다. 이 화면이 알림이다.
        </div>
      </div>
      {multi && (
        // 10 — 필터일 뿐이다. 순서도 부제 건수도 안 바꾼다
        <div className="tchips" data-el="10">
          <button className={`btn sm${filter === null ? ' on' : ''}`} type="button" data-el="10.1" onClick={() => setFilter(null)}>
            전체 <span className="cnt">{t.total}</span>
          </button>
          {parts.map((p) => (
            <button className={`btn sm${filter === p.code ? ' on' : ''}`} type="button" key={p.code} onClick={() => setFilter(filter === p.code ? null : p.code)}>
              <ProjName code={p.code} name={p.name} /> <span className="cnt">{p.total}</span>
            </button>
          ))}
        </div>
      )}
      <div className="todo">
        {!multi && groups(t, true)}
        {multi &&
          shown.map((p, i) => (
            <section className="tproj" data-el={i === 0 ? '11' : undefined} key={p.code}>
              <h3 className="tph" data-el={i === 0 ? '11.1' : undefined}>
                <ProjName code={p.code} name={p.name} /> <span className="cnt">{p.total}</span>
                <span className="rule" />
              </h3>
              {groups(p.d, i === 0)}
            </section>
          ))}
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
  first: boolean
  title: string
  rows: FlagSummary[]
  row: (f: FlagSummary, el?: string) => React.ReactNode
  dim?: boolean
  note?: string
}) {
  const { el, elRow, first, title, rows, row, dim, note } = props
  if (rows.length === 0) return null
  return (
    <section className={`tgroup${dim ? ' dim' : ''}`} data-el={first ? el : undefined}>
      <GroupHead title={title} n={rows.length} note={note} />
      {rows.map((f, i) => row(f, first && i === 0 ? elRow : undefined))}
    </section>
  )
}

/** 묶음 머리 — 이름·건수·열 끝까지 가는 실선·오른쪽 부연. 카드가 아니라 맨 텍스트다 */
function GroupHead({ title, n, note }: { title: string; n: number; note?: string }) {
  return (
    <h4>
      {title} <span className="cnt">{n}</span>
      <span className="rule" />
      {note && <span className="note">{note}</span>}
    </h4>
  )
}
