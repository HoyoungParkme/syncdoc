/** UI-4 프로젝트 상세 — SYNC-UI-002#UI-4. 11단계 표 + 문서 행, 요약 수치, 표준 묶음.
 *  최근 변경(요소 5)은 GET /api/projects/{code}(ProjectDetail·recent_changes)가 versions.message 없이는 못 만든다(보고). */
import { useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import { ago, api, authorLabel, STAGE_NAMES, STAGE_TYPES, STATUS_KO, type DocumentSummary, type ProjectSummary } from '../api/client'

const ST: Record<string, string> = { approved: 'ok', review: 'rv', draft: 'dr' }

export function ProjectDetail() {
  const { code = '' } = useParams()
  const { projects } = useOutletContext<{ projects: ProjectSummary[] }>()
  const p = projects.find((x) => x.code === code)
  const [docs, setDocs] = useState<DocumentSummary[]>([])
  const [open, setOpen] = useState<Record<string, boolean>>({})
  useEffect(() => {
    api.get<DocumentSummary[]>(`/api/projects/${code}/docs`).then(setDocs)
  }, [code])
  if (!p) return <div className="page lbl">프로젝트를 찾을 수 없습니다.</div>
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
        <span className="btn" data-el="2.1" title="UI-8 — B4">
          참조 그래프
        </span>
        <span className="btn" data-el="2.2" title="UI-9 — B4">
          순서대로 읽기
        </span>
      </div>
      <div className="stats" data-el="3">
        {[
          ['3.1', 'needs_check', '확인 필요'],
          ['3.2', 'broken_ref', '끊어진 참조'],
          ['3.3', 'unresolved_comments', '미해결 댓글'],
          ['3.4', 'convention_errors', '규약 오류'],
          ['3.5', 'incomplete', '미완성'],
        ].map(([el, k, label]) => (
          <span className={`stat${p.counts[k] ? '' : ' dim'}`} data-el={el} key={k}>
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
            <p className="lbl">GET /api/projects/{'{code}'}의 recent_changes는 versions.message가 없어 아직 못 만든다(명세 결함 보고).</p>
          </div>
        </aside>
      </div>
      {STAGE_TYPES.length === 0 && null}
    </div>
  )
}

function lowest(ds: DocumentSummary[]): string {
  const order: Record<string, number> = { draft: 0, review: 1, approved: 2 }
  return ds.map((d) => d.status).sort((a, b) => order[a] - order[b])[0] ?? 'draft'
}
