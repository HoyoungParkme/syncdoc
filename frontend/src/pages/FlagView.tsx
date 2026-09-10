/** UI-11 플래그 처리 — SYNC-UI-002#UI-11. 위가 원인, 아래가 내 항목. 요소 번호 = data-el.
 *  1 헤더(1.1 대상, 1.2 담당·부여) · 2 원인 영역(2.1 항목, 2.2 버전 범위, 2.3 diff/본문, 2.4 문서에서 보기)
 *  · 3 내 항목 영역(3.1, 3.2 버전·변경 여부, 3.3 본문, 3.4) · 4 처리(4.1 확인함, 4.2 안내) · 5 내 할 일로 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ago, api, ApiError, docPath, FLAG_KO, refKey, type FlagDetail } from '../api/client'
import { DiffBox } from '../components/DiffBox'
import { ItemIdBadge } from '../components/ui'
import { renderBlocks, type RenderCtx } from '../view/md'

export function FlagView() {
  const { flagId = '' } = useParams()
  const nav = useNavigate()
  const [f, setF] = useState<FlagDetail | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api
      .get<FlagDetail>(`/api/flags/${flagId}`)
      .then(setF)
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)))
  }, [flagId])
  const ctx = useMemo<RenderCtx>(
    () => ({ selfId: f?.target.doc_id ?? '', href: (d, it) => docPath(d, it), exists: () => true }),
    [f?.target.doc_id],
  )
  if (err) return <div className="page banner err">{err}</div>
  if (!f) return null
  const causeTo = (f.cause_version_no ?? 0) + f.cause_change_count
  async function resolve() {
    try {
      await api.post(`/api/flags/${flagId}/resolve`, {})
      nav('/todo')
    } catch (e) {
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    }
  }
  return (
    <div className="page flagpage">
      <div className="fhead" data-el="1">
        <div>
          <div className="t1">
            <span className="flag">{FLAG_KO[f.kind]}</span>
            <span className="fid" data-el="1.1">{refKey(f.target)}</span>
            <span className="ftitle">{f.target.display_name}</span>
          </div>
          <div className="lbl" data-el="1.2">
            담당 {f.assignee?.display_name ?? '미지정'} · {ago(f.raised_at)} 부여
            {f.resolved_at && ` · 확인됨 ${ago(f.resolved_at)}`}
          </div>
        </div>
        <span className="grow" />
        <Link className="btn" data-el="5" to="/todo">
          ← 내 할 일
        </Link>
      </div>
      <div className="stack">
        <section className="cause" data-el="2">
          <div className="sech">
            <b>원인</b> <span className="mono" data-el="2.1">{f.cause ? refKey(f.cause) : '(하위 문서)'}</span>{' '}
            <span className="lbl">{f.cause?.display_name}</span>
            <span className="lbl" data-el="2.2">
              {f.kind === 'needs_check' && `v${f.cause_version_no} → v${causeTo}${f.cause_change_count > 0 ? ` · 그 사이 ${f.cause_change_count}번 바뀜` : ''}`}
              {f.kind === 'broken_ref' && `${f.cause_deleted_at ? ago(f.cause_deleted_at) : ''} 삭제됨`}
              {f.kind === 'upstream_impact' && '지목한 하위 항목의 현재 본문'}
            </span>
            <span className="grow" />
            {f.cause?.doc_id && (
              <Link className="btn sm" data-el="2.4" to={docPath(f.cause.doc_id, f.cause.item_id)}>
                문서에서 보기
              </Link>
            )}
          </div>
          {f.kind === 'needs_check' && f.cause_diff && <DiffBox diff={f.cause_diff} el="2.3" />}
          {f.kind === 'broken_ref' && (
            <div className="mybody lbl" data-el="2.3">
              상위 항목 {refKey(f.cause)}이(가) 사라졌습니다. 대체할 항목으로 참조를 고치거나(UC-H12) 참조를 지우세요.
            </div>
          )}
          {f.kind === 'upstream_impact' && (
            <div className="mybody body" data-el="2.3" dangerouslySetInnerHTML={{ __html: f.cause_body?.startsWith('#') ? renderBlocks(f.cause_body, ctx) : `<p>${f.cause_body ?? ''}</p>` }} />
          )}
        </section>
        <section className="mine" data-el="3">
          <div className="sech">
            <b>내 항목</b> <span className="mono" data-el="3.1">{refKey(f.target)}</span>
            <span className="lbl" data-el="3.2">
              v{f.target_version_no} · 플래그 부여 후 변경 {f.target_changed_since_raise ? '있음' : '없음'}
            </span>
            <span className="grow" />
            <Link className="btn sm" data-el="3.4" to={docPath(f.target.doc_id, f.target.item_id)}>
              문서에서 보기
            </Link>
          </div>
          <div className="mybody">
            {/* 항목 ID는 뱃지로 — 카드 안에서 색을 쓰는 유일한 자리다 */}
            <div className="mineh">
              <ItemIdBadge>{f.target.item_id ?? f.target.doc_id}</ItemIdBadge>
              <b>{f.target.display_name}</b>
            </div>
            {/* 항목 헤딩은 위 뱃지 줄이 이미 말한다 — 본문에서 걷어내지 않으면 제목이 두 번 나온다 */}
            <div className="body" data-el="3.3" dangerouslySetInnerHTML={{ __html: renderBlocks(bodyWithoutHeading(f.target_body), ctx) }} />
          </div>
        </section>
        <div className="acts" data-el="4">
          {/* 규칙: 확인 버튼은 하나다. 수정 동반 여부를 사람에게 묻지 않는다 —
              시스템이 이미 아는 것을 두 번 물으면 답이 어긋난다. 대신 어느 쪽으로 기록될지 미리 보여준다 */}
          <span className="lbl" data-el="4.2">
            영향이 있으면 에이전트에게 수정을 시킨 뒤 돌아와 확인하세요 · 지금 누르면{' '}
            <b>{f.target_changed_since_raise ? '수정 동반' : '수정 없음'}</b>으로 기록됩니다
          </span>
          <span className="grow" />
          <button className="btn solid" data-el="4.1" disabled={!!f.resolved_at} onClick={resolve}>
            {f.resolved_at ? '확인됨' : '확인함'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** 항목 본문에서 맨 앞 항목 헤딩 한 줄을 걷어낸다. 화면이 제목을 따로 그리기 때문이다 */
function bodyWithoutHeading(body: string): string {
  const lines = body.split('\n')
  return lines[0]?.startsWith('#') ? lines.slice(1).join('\n').replace(/^\n+/, '') : body
}
