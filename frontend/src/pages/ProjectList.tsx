/** UI-2 프로젝트 목록 — SYNC-UI-002#UI-2. 프로젝트가 행, 11단계가 열. UC-H14 1~2, 1a·1b·3a.
 *  1 헤더(1.1 초기화) · 2 현황판(2.1 행, 2.2 단계 칸, 2.3 경고, 2.4 상위 미완료) · 3 빈 상태 · 4 범례
 *
 *  표가 아니라 격자다 — 칸이 열 폭을 꽉 채워야 색이 띠로 읽힌다. */
import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { ago, STAGE_TYPES, type ProjectSummary } from '../api/client'
import { ProjectInit } from './ProjectInit'
import { ProjName, Tooltip } from '../components/ui'

/** 행 아래 요약과 경고 툴팁이 같은 목록을 쓴다 — 한쪽만 고쳐 어긋나는 일이 없게 */
const KINDS: [string, string][] = [
  ['broken_ref', '끊어진 참조'],
  ['convention_errors', '규약 오류'],
]
const CELL: Record<string, string> = { approved: 'ok', draft: 'dr' }

const breakdown = (counts: Record<string, number>) =>
  KINDS.filter(([k]) => counts[k]).map(([k, ko]) => `${ko} ${counts[k]}`)

export function ProjectList() {
  const { projects } = useOutletContext<{ projects: ProjectSummary[] }>()
  const nav = useNavigate()
  const [init, setInit] = useState(false)
  return (
    <div className="page">
      <div className="phead" data-el="1">
        <div>
          <b>프로젝트</b> <span className="lbl">{projects.length}개</span>
        </div>
        <span className="grow" />
        <button className="btn solid" type="button" data-el="1.1" onClick={() => setInit(true)}>
          + 프로젝트 초기화
        </button>
      </div>
      {projects.length > 0 && (
        <>
          <div className="heat" data-el="2">
            <div className="hrow head">
              <span />
              <span />
              {STAGE_TYPES.map((t, i) => (
                <span key={t}>
                  {i + 1} {t}
                </span>
              ))}
            </div>
            {projects.map((p) => {
              const work = breakdown(p.counts)
              const docs = p.stages.reduce((n, s) => n + s.doc_count, 0) + p.std_docs.length
              return (
                <div className="hrow" data-el="2.1" key={p.code}>
                  <span>
                    {work.length > 0 && (
                      // 규칙: 아이콘은 종류를 안 나눈다. 종류별 건수는 툴팁이 편다
                      <Tooltip text={work.join('\n')}>
                        <span className="warn" data-el="2.3">
                          ⚠
                        </span>
                      </Tooltip>
                    )}
                  </span>
                  <span className="pname" onClick={() => nav(`/p/${p.code}`)}>
                    <span>
                      <ProjName code={p.code} name={p.name} />
                    </span>
                    <span className="sub">
                      {/* 규칙: 둘째 줄은 `끊어진 참조 N · 규약 오류 M` — 0이 아닌 것만, 경고색 */}
                      {work.length > 0 && (
                        <>
                          <b className="work">{work.join(' · ')}</b>
                          <span className="mid">·</span>
                        </>
                      )}
                      {docs}문서{p.updated_at ? ` · ${ago(p.updated_at)}` : ''}
                    </span>
                  </span>
                  {p.stages.map((s) => (
                    <StageCell key={s.stage} s={s} onOpen={() => nav(`/p/${p.code}#stage-${s.stage}`)} />
                  ))}
                </div>
              )
            })}
          </div>
          <div className="legend lbl" data-el="4">
            <span>
              <i className="sw dr" /> 초안
            </span>
            <span>
              <i className="sw ok" /> 완료
            </span>
            <span>
              <i className="sw na" /> 미작성
            </span>
            <span className="warn">⚠ 끊어진 참조·규약 오류 있음</span>
            <span className="warn">▲ 상위 미완료 (막지는 않는다)</span>
          </div>
        </>
      )}
      {projects.length === 0 && (
        <div className="empty" data-el="3">
          등록된 프로젝트가 없습니다. 위의 프로젝트 초기화로 시작하세요.
        </div>
      )}
      {/* 성공하면 목록에 새 행이 보여야 한다. 목록은 셸이 들고 있으므로 다시 읽는다 */}
      {init && <ProjectInit onClose={() => setInit(false)} onDone={() => window.location.assign('/')} />}
    </div>
  )
}

/** 색은 상태, 테두리는 끊어진 참조. 두 정보가 한 칸에 겹치지 않게 나눈다 (UI-2 규칙).
 *  칸 하나에 툴팁도 하나다 — 칸과 ▲에 따로 걸면 ▲ 위에서 둘이 같이 뜬다. */
function StageCell({ s, onOpen }: { s: ProjectSummary['stages'][number]; onOpen: () => void }) {
  const lines = [
    s.status ? `${s.doc_count}문서` : '미작성',
    s.broken_count ? `끊어진 참조 ${s.broken_count}` : '',
    s.gate_warning ? '앞 단계 미완료 (막지는 않는다)' : '',
  ].filter(Boolean)
  return (
    <Tooltip text={lines.join('\n')}>
      <span
        className={`cell ${s.status ? CELL[s.status] : 'na'}${s.broken_count ? ' missing' : ''}`}
        data-el="2.2"
        onClick={onOpen}
      >
        {s.doc_count || ''}
        {s.gate_warning && <i data-el="2.4">▲</i>}
      </span>
    </Tooltip>
  )
}
