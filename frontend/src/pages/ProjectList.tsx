/** UI-2 프로젝트 목록 — SYNC-UI-002#UI-2. 프로젝트가 행, 11단계가 열. UC-H14 1~2, 1a·1b·3a.
 *  1 헤더(1.1 초기화) · 2 현황판(2.1 행, 2.2 단계 칸, 2.3 경고, 2.4 상위 미승인) · 3 빈 상태 · 4 범례 */
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { STAGE_TYPES, type ProjectSummary } from '../api/client'
import { Tooltip } from '../components/ui'

/** 행 아래 요약과 경고 툴팁이 같은 목록을 쓴다 — 한쪽만 고쳐 어긋나는 일이 없게 */
const KINDS: [string, string][] = [
  ['needs_check', '확인 필요'],
  ['broken_ref', '끊어진 참조'],
  ['upstream_impact', '하위 불일치'],
  ['convention_errors', '규약 오류'],
]

const breakdown = (counts: Record<string, number>) =>
  KINDS.filter(([k]) => counts[k]).map(([k, ko]) => `${ko} ${counts[k]}`)

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
        <>
          <table className="grid heat" data-el="2">
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
                const summary = breakdown(p.counts)
                return (
                  <tr className="prj" data-el="2.1" key={p.code} onClick={() => nav(`/p/${p.code}`)}>
                    <td>
                      {summary.length > 0 && (
                        // 규칙: 아이콘은 종류를 안 나눈다. 종류별 건수는 툴팁이 편다
                        <Tooltip text={summary.join('\n')}>
                          <span className="warn" data-el="2.3">
                            ⚠
                          </span>
                        </Tooltip>
                      )}
                    </td>
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
                        <StageCell s={s} />
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="legend lbl" data-el="4">
            <span>
              <i className="sw sw-approved" /> 승인
            </span>
            <span>
              <i className="sw sw-review" /> 검토중
            </span>
            <span>
              <i className="sw sw-draft" /> 초안
            </span>
            <span>
              <i className="sw sw-none" /> 미작성
            </span>
            <span>
              <i className="sw flagged" /> 플래그 있음
            </span>
            <span>
              <span className="warn">⚠</span> 플래그·규약 오류 있음
            </span>
            <span>
              <i className="warn">▲</i> 상위 미승인 (막지는 않는다)
            </span>
          </div>
        </>
      )}
      {projects.length === 0 && (
        <div className="empty" data-el="3">
          등록된 프로젝트가 없습니다. 위의 프로젝트 초기화로 시작하세요.
        </div>
      )}
    </div>
  )
}

/** 색은 상태, 테두리는 플래그. 두 정보가 한 칸에 겹치지 않게 나눈다 (UI-2 규칙).
 *  칸 하나에 툴팁도 하나다 — 칸과 ▲에 따로 걸면 ▲ 위에서 둘이 같이 뜬다. */
function StageCell({ s }: { s: ProjectSummary['stages'][number] }) {
  const lines = [
    s.flag_count ? `플래그 ${s.flag_count}` : '',
    s.gate_warning ? '앞 단계 미승인 (막지는 않는다)' : '',
  ].filter(Boolean)
  const cell = (
    <span
      className={`cell cell-${s.status ?? 'none'}${s.flag_count ? ' flagged' : ''}`}
      data-el="2.2"
    >
      {s.doc_count || ''}
      {s.gate_warning && <i data-el="2.4">▲</i>}
    </span>
  )
  return lines.length ? <Tooltip text={lines.join('\n')}>{cell}</Tooltip> : cell
}
