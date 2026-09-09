/** UI-4 프로젝트 상세 — SYNC-UI-002#UI-4. 11단계 표 + 문서 행, 요약 수치, 표준 묶음, 최근 변경(status 커밋 포함).
 *  GET /api/projects/{code}(ProjectDetail) 하나로 그린다. 요소 번호 = data-el.
 *  1 헤더(1.1·1.2·1.3) · 2.1·2.2 그래프·순서(B4) · 3 요약 수치(3.1~3.5 → 다이얼로그 6) · 4 표(4.1 단계, 4.2 문서, 4.3 상위 미승인, 4.4 표준) · 5 최근 변경 · 6 목록 다이얼로그 */
import { useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import { ago, api, authorLabel, docPath, refKey, STAGE_NAMES, STAGE_TYPES, STATUS_KO, type CommentSummary, type DocumentSummary, type FlagSummary, type ProjectDetail as Detail, type ProjectSummary, type Version } from '../api/client'

const ST: Record<string, string> = { approved: 'ok', review: 'rv', draft: 'dr' }

export function ProjectDetail() {
  const { code = '' } = useParams()
  const { projects } = useOutletContext<{ projects: ProjectSummary[] }>()
  const p = projects.find((x) => x.code === code)
  const [docs, setDocs] = useState<DocumentSummary[]>([])
  const [recent, setRecent] = useState<Version[]>([])
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [dialog, setDialog] = useState<{ kind: string; label: string; items: unknown[] } | null>(null)
  useEffect(() => {
    api.get<Detail>(`/api/projects/${code}`).then((d) => {
      setDocs(d.docs)
      setRecent(d.recent_changes)
    })
  }, [code])
  if (!p) return <div className="page lbl">프로젝트를 찾을 수 없습니다.</div>
  const openList = (kind: string, label: string) => {
    api.get<unknown[]>(`/api/projects/${code}/flags?kind=${kind}`).then((items) => setDialog({ kind, label, items }))
  }
  const byType = (t: string) => docs.filter((d) => d.doc_type === t)
  const toggle = (k: string) => setOpen((o) => ({ ...o, [k]: !(o[k] ?? true) }))
  const row = (d: DocumentSummary) => (
    <tr className="doc" data-el="4.2" key={d.doc_id}>
      <td />
      <td colSpan={3}>
        <Link to={`/p/${code}/d/${d.doc_id}`}>{d.doc_id}</Link> · {STATUS_KO[d.status]} · v{d.current_version_no} · {ago(d.updated_at)} · {authorLabel(d.last_author)}
        {d.counts.needs_check > 0 && <span className="flag"> 확인 필요 {d.counts.needs_check}</span>}
        {d.counts.broken_ref > 0 && <span className="flag"> 끊어진 참조 {d.counts.broken_ref}</span>}
        {d.counts.unresolved_comments > 0 && <span className="cm"> 댓글 {d.counts.unresolved_comments}</span>}
        {d.has_convention_error && <span className="err"> 규약 오류</span>}
        {d.incomplete_warnings.length > 0 && <span className="warnx"> 미완성</span>}
      </td>
    </tr>
  )
  return (
    <div className="page">
      <div className="phead" data-el="1">
        <div>
          <b data-el="1.1">{p.code}</b> <span data-el="1.2">{p.name}</span>
        </div>
        <a className="lbl" data-el="1.3" href={p.remote_url} target="_blank" rel="noreferrer">
          {p.remote_url.replace(/^https?:\/\//, '')}
        </a>
        <span className="grow" />
        <Link className="btn" data-el="2.1" to={`/p/${code}/graph`}>
          참조 그래프
        </Link>
        <Link className="btn" data-el="2.2" to={`/p/${code}/read`}>
          순서대로 읽기
        </Link>
      </div>
      <div className="stats" data-el="3">
        {[
          { el: '3.1', k: 'needs_check', kind: 'needs_check', label: '확인 필요' },
          { el: '3.2', k: 'broken_ref', kind: 'broken_ref', label: '끊어진 참조' },
          { el: '3.3', k: 'unresolved_comments', kind: 'comments', label: '미해결 댓글' },
          { el: '3.4', k: 'convention_errors', kind: 'convention_errors', label: '규약 오류' },
          { el: '3.5', k: 'incomplete', kind: 'incomplete', label: '미완성' },
        ].map(({ el, k, kind, label }) => (
          <span className={`stat link${p.counts[k] ? '' : ' dim'}`} data-el={el} key={k} onClick={() => openList(kind, label)}>
            <b>{p.counts[k] ?? 0}</b> {label}
          </span>
        ))}
      </div>
      <div className="body2">
        <table className="stages" data-el="4">
          <tbody>
            {p.stages.map((s) => {
              const ds = byType(s.doc_type)
              const isOpen = open[s.doc_type] ?? true
              return [
                <tr className="stg" data-el="4.1" key={s.doc_type} id={`stage-${s.stage}`} onClick={() => toggle(s.doc_type)}>
                  <td className="no">{s.stage}</td>
                  <td>{STAGE_NAMES[s.doc_type]}</td>
                  <td>
                    <span className={`st ${s.status ? ST[s.status] : 'na'}`}>{s.status ? STATUS_KO[s.status] : '미작성'}</span>
                    {s.gate_warning && (
                      <span className="gate" data-el="4.3">
                        상위 미승인
                      </span>
                    )}
                  </td>
                  <td className="lbl">{s.doc_count ? `${s.doc_count}개` : '—'}</td>
                </tr>,
                ...(isOpen ? ds.map(row) : []),
              ]
            })}
            {p.std_docs.length > 0 && [
              <tr className="stg" data-el="4.4" key="std" onClick={() => toggle('STD')}>
                <td className="no">—</td>
                <td>표준 (STD)</td>
                <td>
                  <span className={`st ${ST[lowest(p.std_docs)] ?? 'dr'}`}>{STATUS_KO[lowest(p.std_docs)]}</span>
                </td>
                <td className="lbl">{p.std_docs.length}개</td>
              </tr>,
              ...((open.STD ?? true) ? byType('STD').map(row) : []),
            ]}
          </tbody>
        </table>
        <aside className="panel" data-el="5">
          <div className="pbody">
            <h4>최근 변경</h4>
            {recent.length === 0 && <p className="lbl">아직 변경이 없습니다.</p>}
            <ul className="recent">
              {recent.map((v) => (
                <li key={v.commit_hash + (v.version_no ?? 's')}>
                  <Link to={`/p/${code}/d/${v.doc_id}`}>
                    <b>{v.doc_id}</b>
                  </Link>
                  {v.version_no != null && <> v{v.version_no}</>} · {ago(v.created_at)} · {authorLabel(v.author)}
                  <br />
                  <span className="lbl">{v.message.split('\n')[0]}</span>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
      {STAGE_TYPES.length === 0 && null}
      {dialog && (
        <>
          <div className="backdrop" onClick={() => setDialog(null)} />
          <div className="dialog" data-el="6">
            <div className="dhead">
              {dialog.label} {dialog.items.length}건
              <span className="grow" />
              <span className="x" onClick={() => setDialog(null)}>
                ✕
              </span>
            </div>
            <div className="dbody">
              {dialog.items.length === 0 && <p className="lbl">없습니다.</p>}
              <ul className="chk">{dialog.items.map((it) => listItem(dialog.kind, it))}</ul>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

/** 다이얼로그 6의 행 — kind에 따라 FlagSummary · CommentSummary · DocumentSummary. 항목 클릭 → 그 문서의 UI-5 */
function listItem(kind: string, it: unknown) {
  if (kind === 'comments') {
    const c = it as CommentSummary
    return (
      <li key={c.id}>
        <Link to={`${docPath(c.doc_id)}?panel=comments#line-${c.line_no}`}>
          <b>{c.doc_id}</b>
        </Link>{' '}
        {c.line_no}행 · {c.author?.display_name}: {c.excerpt} · {ago(c.created_at)}
      </li>
    )
  }
  if (kind === 'convention_errors' || kind === 'incomplete') {
    const d = it as DocumentSummary
    return (
      <li key={d.doc_id}>
        <Link to={docPath(d.doc_id)}>
          <b>{d.doc_id}</b>
        </Link>{' '}
        v{d.current_version_no} · {kind === 'incomplete' ? d.incomplete_warnings.join(' · ') : '규약 오류'} · {ago(d.updated_at)}
      </li>
    )
  }
  const f = it as FlagSummary
  return (
    <li key={f.id}>
      <Link to={docPath(f.target.doc_id, f.target.item_id)}>
        <b>{refKey(f.target)}</b>
      </Link>{' '}
      · 원인 {refKey(f.cause)}{f.cause_version_no ? ` v${f.cause_version_no}` : ''} · {ago(f.raised_at)} · 담당 {f.assignee?.display_name ?? '미지정'}
    </li>
  )
}

function lowest(ds: DocumentSummary[]): string {
  const order: Record<string, number> = { draft: 0, review: 1, approved: 2 }
  return ds.map((d) => d.status).sort((a, b) => order[a] - order[b])[0] ?? 'draft'
}
