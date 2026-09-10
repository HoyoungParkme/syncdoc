/** UI-2 프로젝트 목록 — SYNC-UI-002#UI-2. 프로젝트가 행, 11단계가 열. UC-H14 1~2, 1a·1b·3a. */
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { STAGE_TYPES, type ProjectSummary } from '../api/client'
import { Tooltip } from '../components/ui'

const CELL: Record<string, string> = { approved: 'ok', review: 'rv', draft: 'dr' }

export function ProjectList() {
  const { projects } = useOutletContext<{ projects: ProjectSummary[] }>()
  const nav = useNavigate()
  return (
    <div className="page">
      <div className="phead" data-el="1">
        <div>
          <b>프로젝트</b> <span className="lbl">{projects.length}개</span>
        </div>
        <span className="grow" />
        <Link className="btn" data-el="1.1" to="/projects/new">
          + 프로젝트 초기화
        </Link>
      </div>
      {projects.length > 0 && (
        <table className="grid" data-el="2">
          <thead>
            <tr className="hd">
              <th />
              <th>프로젝트</th>
              {STAGE_TYPES.map((t) => (
                <th key={t}>{t}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => {
              const flags = p.counts.needs_check + p.counts.broken_ref + p.counts.convention_errors
              const summary = [
                p.counts.needs_check ? `확인 필요 ${p.counts.needs_check}` : '',
                p.counts.broken_ref ? `끊어진 참조 ${p.counts.broken_ref}` : '',
                p.counts.convention_errors ? `규약 오류 ${p.counts.convention_errors}` : '',
              ].filter(Boolean)
              return (
                <tr className="prj" data-el="2.1" key={p.code} onClick={() => nav(`/p/${p.code}`)}>
                  <td>{flags > 0 && <Tooltip text="플래그·규약 오류 있음"><span className="warn" data-el="2.3">⚠</span></Tooltip>}</td>
                  <td>
                    <b>{p.code}</b> {p.name}
                    {summary.length > 0 && (
                      <>
                        <br />
                        <span className="lbl">{summary.join(' · ')}</span>
                      </>
                    )}
                  </td>
                  {p.stages.map((s) => (
                    <td
                      key={s.stage}
                      onClick={(e) => {
                        e.stopPropagation()
                        nav(`/p/${p.code}#stage-${s.stage}`)
                      }}
                    >
                      <span className={`cell ${s.status ? CELL[s.status] : 'na'}`} data-el="2.2">
                        {s.doc_count || ''}
                        {s.gate_warning && (
                          <Tooltip text="앞 단계 미승인">
                            <i data-el="2.4">▲</i>
                          </Tooltip>
                        )}
                      </span>
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {projects.length === 0 && (
        <div className="empty" data-el="3">
          등록된 프로젝트가 없습니다. 위의 프로젝트 초기화로 시작하세요.
        </div>
      )}
    </div>
  )
}
