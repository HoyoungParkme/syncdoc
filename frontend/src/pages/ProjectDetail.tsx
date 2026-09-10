/** UI-4 프로젝트 상세 — SYNC-UI-002#UI-4. 11단계 표 + 문서 행, 요약 수치, 표준 묶음, 최근 변경(status 커밋 포함).
 *  GET /api/projects/{code}(ProjectDetail) 하나로 그린다. 요소 번호 = data-el.
 *  1 헤더(1.1·1.2·1.3) · 2.1·2.2 그래프·순서 · 3 요약 수치 여섯(3.1·3.2·3.6·3.3·3.4·3.5 → 다이얼로그 6)
 *  4 표(4.1 단계, 4.2 문서, 4.3 상위 미승인, 4.4 표준) · 5 최근 변경 · 6 목록 다이얼로그 · 7 동기화 상태(7.1 커밋, 7.2 밀림) */
import { useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams } from 'react-router-dom'
import { StatusPill } from '../components/ui'
import { ago, api, authorLabel, docPath, refKey, STAGE_NAMES, STATUS_KO, type CommentSummary, type DocumentSummary, type FlagSummary, type ProjectDetail as Detail, type ProjectSummary } from '../api/client'


/** 미니 히트맵과 문서 행 점이 쓰는 상태 → 클래스 */
const ST: Record<string, string> = { approved: 'ok', review: 'rv', draft: 'dr' }

export function ProjectDetail() {
  const { code = '' } = useParams()
  const nav = useNavigate()
  const { projects } = useOutletContext<{ projects: ProjectSummary[] }>()
  const p = projects.find((x) => x.code === code)
  const [d, setD] = useState<Detail | null>(null)
  // 기본은 접힘. 열두 줄이 다 펼쳐지면 화면 하나에 11단계가 안 들어온다.
  // UI-2 칸에서 #stage-N으로 들어오면 그 단계만 펼친 채로 연다
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [dialog, setDialog] = useState<{ kind: string; label: string; items: unknown[] } | null>(null)
  useEffect(() => {
    setD(null)
    api.get<Detail>(`/api/projects/${code}`).then(setD)
  }, [code])
  // UI-2 칸 클릭으로 들어온 경우 — 그 단계만 펼친다
  useEffect(() => {
    const m = /^#stage-(\d+)$/.exec(window.location.hash)
    if (!m || !d) return
    const st = d.stages.find((x) => x.stage === Number(m[1]))
    if (st) setOpen((o) => ({ ...o, [st.doc_type]: true }))
  }, [d])
  if (!p && !d) return <div className="page lbl">프로젝트를 찾을 수 없습니다.</div>
  // 상세가 오기 전에는 목록이 들고 있던 요약으로 그린다. 화면이 비었다 다시 차지 않게
  const sum = d ?? (p as ProjectSummary)
  const docs = d?.docs ?? []
  const recent = d?.recent_changes ?? []
  const openList = (kind: string, label: string) => {
    api.get<unknown[]>(`/api/projects/${code}/flags?kind=${kind}`).then((items) => setDialog({ kind, label, items }))
  }
  const byType = (t: string) => docs.filter((d) => d.doc_type === t)
  const toggle = (k: string) => setOpen((o) => ({ ...o, [k]: !o[k] }))
  const row = (d: DocumentSummary) => (
    <div className="doc" data-el="4.2" key={d.doc_id} onClick={() => nav(`/p/${code}/d/${d.doc_id}`)}>
      <span className="mono">{d.doc_id}</span>
      <span className={`dot ${ST[d.status]}`} />
      <span className="lbl">
        {STATUS_KO[d.status]} · v{d.current_version_no} · {ago(d.updated_at)} · {authorLabel(d.last_author)}
      </span>
      <span className="grow" />
      {d.counts.needs_check > 0 && <span className="flag">확인 필요 {d.counts.needs_check}</span>}
      {d.counts.broken_ref > 0 && <span className="flag">끊어진 참조 {d.counts.broken_ref}</span>}
      {d.counts.unresolved_comments > 0 && <span className="cm">댓글 {d.counts.unresolved_comments}</span>}
      {d.has_convention_error && <span className="err">규약 오류</span>}
      {d.incomplete_warnings.length > 0 && <span className="warnx">미완성</span>}
    </div>
  )
  return (
    <div className="page">
      <div className="phead" data-el="1">
        <div>
          <div>
            <b className="mono" data-el="1.1">
              {sum.code}
            </b>{' '}
            <span data-el="1.2">{sum.name}</span>
          </div>
          <a className="repo mono" data-el="1.3" href={sum.remote_url} target="_blank" rel="noreferrer">
            {sum.remote_url.replace(/^https?:\/\//, '').replace(/\.git$/, '')}
          </a>
        </div>
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
          // 3.6은 명세의 자리 순서를 따른다 — 플래그 셋을 붙여 놓고 그 뒤가 댓글·오류다
          { el: '3.6', k: 'upstream_impact', kind: 'upstream_impact', label: '하위 불일치' },
          { el: '3.3', k: 'unresolved_comments', kind: 'comments', label: '미해결 댓글' },
          { el: '3.4', k: 'convention_errors', kind: 'convention_errors', label: '규약 오류' },
          { el: '3.5', k: 'incomplete', kind: 'incomplete', label: '미완성' },
        ].map(({ el, k, kind, label }) => (
          <span
            className={`stat link${sum.counts[k] ? '' : ' dim'}`}
            data-el={el}
            key={k}
            onClick={() => openList(kind, label)}
          >
            <b>{sum.counts[k] ?? 0}</b> {label}
          </span>
        ))}
      </div>
      <div className="body2">
        <div className="stages" data-el="4">
          {/* 머리의 미니 히트맵 — UI-2에서 본 그 프로젝트 행이 여기 다시 있다 */}
          <div className="stgh">
            <b>11단계</b>
            <span className="grow" />
            {sum.stages.map((s) => (
              <i key={s.stage} className={`sw ${s.status ? ST[s.status] : 'na'}`} title={STAGE_NAMES[s.doc_type]} />
            ))}
          </div>
          {sum.stages.map((s) => {
            const isOpen = open[s.doc_type] ?? false
            return (
              <div key={s.doc_type}>
                <div className="stg" data-el="4.1" id={`stage-${s.stage}`} onClick={() => toggle(s.doc_type)}>
                  <span className="no mono">{s.stage}</span>
                  <span className="nm">{STAGE_NAMES[s.doc_type]}</span>
                  <StatusPill status={s.status} />
                  {s.gate_warning && (
                    <span className="gate" data-el="4.3">
                      상위 미승인
                    </span>
                  )}
                  <span className="grow" />
                  <span className="lbl">{s.doc_count ? `${s.doc_count}개` : '—'}</span>
                  <span className="caret">{s.doc_count ? (isOpen ? '▾' : '▸') : ''}</span>
                </div>
                {isOpen && byType(s.doc_type).map(row)}
              </div>
            )
          })}
          {sum.std_docs.length > 0 && (
            <div>
              <div className="stg" data-el="4.4" onClick={() => toggle('STD')}>
                <span className="no mono">—</span>
                <span className="nm">표준 (STD)</span>
                <StatusPill status={lowest(sum.std_docs)} />
                <span className="grow" />
                <span className="lbl">{sum.std_docs.length}개</span>
                <span className="caret">{open.STD ? '▾' : '▸'}</span>
              </div>
              {open.STD && byType('STD').map(row)}
            </div>
          )}
        </div>
        <aside className="panel" data-el="5">
          <div className="pbody">
            <h4>최근 변경</h4>
            {recent.length === 0 && <p className="lbl">아직 변경이 없습니다.</p>}
            {recent.map((v) => (
              <div className="rc" key={v.commit_hash + (v.version_no ?? 's')} onClick={() => nav(`/p/${code}/d/${v.doc_id}`)}>
                <div>
                  <span className="mono">{v.doc_id}</span>{' '}
                  <span className="mono lbl">{v.version_no != null ? `v${v.version_no}` : 'status'}</span>
                  <span className="grow" />
                  <span className="lbl">{ago(v.created_at)}</span>
                </div>
                <div className="msg">{v.message.split('\n')[0]}</div>
                <div className="lbl">{authorLabel(v.author)}</div>
              </div>
            ))}
            {d && (
              // 폴링이 DB에 적어 둔 값을 그대로 읽는다. 이 화면에 들어올 때마다 fetch가 돌지 않는다.
              // 재구축 같은 조작은 여기 없고 UI-14에 있다
              <div className="sync lbl" data-el="7">
                마지막 처리 커밋{' '}
                {d.last_processed_commit ? (
                  <a
                    className="mono"
                    data-el="7.1"
                    href={`${sum.remote_url.replace(/\.git$/, '')}/commit/${d.last_processed_commit}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {d.last_processed_commit.slice(0, 7)}
                  </a>
                ) : (
                  <span className="mono" data-el="7.1">
                    —
                  </span>
                )}
                <br />
                밀린 커밋{' '}
                <span data-el="7.2" className={d.behind_by ? 'behind' : undefined}>
                  {d.behind_by ?? '—'}
                </span>
              </div>
            )}
          </div>
        </aside>
      </div>
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
