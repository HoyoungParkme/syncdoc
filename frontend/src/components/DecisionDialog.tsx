/** UI-12 전파 선택 — SYNC-UI-002#UI-12. UI-10 위의 다이얼로그. 요소 번호 = data-el.
 *  1 다이얼로그(1.1 제목, 1.2 저장 주체) · 2 변경 영역(2.1 diff) · 3 영향 영역(3.1 목록) · 4 예 · 5 전파 안 함(5.1 버튼, 5.2 사유) · 6 닫기 */
import { useEffect, useState } from 'react'
import { ago, api, ApiError, authorLabel, docPath, refKey, type DecisionDetail } from '../api/client'
import { DiffBox } from './DiffBox'

export function DecisionDialog({ versionId, onClose }: { versionId: number; onClose: (decided: boolean) => void }) {
  const [d, setD] = useState<DecisionDetail | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    api.get<DecisionDetail>(`/api/decisions/${versionId}`).then(setD).catch(() => onClose(false))
  }, [versionId, onClose])
  async function decide(choice: 'propagate' | 'skip') {
    setBusy(true)
    try {
      await api.post(`/api/decisions/${versionId}`, { choice, reason: choice === 'skip' ? reason : null })
      onClose(true)
    } catch (e) {
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
      setBusy(false)
    }
  }
  if (!d) return null
  const n = d.affected.length
  const changed = d.change_diff.hunks.filter((h) => h.item_id).length
  return (
    <>
      <div className="backdrop" onClick={() => onClose(false)} />
      <div className="dialog mid" data-el="1">
        <div className="dhead">
          <span data-el="1.1">
            전파 선택 — {d.doc_id} v{d.version.version_no}
          </span>
          <span className="grow" />
          <span className="lbl" data-el="1.2">
            저장: {authorLabel(d.version.author)} · {ago(d.version.created_at)}
          </span>
          <span className="x" data-el="6" onClick={() => onClose(false)}>
            ✕
          </span>
        </div>
        <div className="dbody">
          {/* 규칙 셋을 먼저 말한다 — 전부냐 아니냐, 닫으면 어떻게 되나 */}
          <p className="dlead">
            이 버전에서 바뀐 것과 영향받는 하위 항목입니다. 전파하면 전부에 확인 필요가 붙습니다 — 일부만 고를 수 없습니다. 닫으면 미결정이 그대로 남습니다.
          </p>
          <div className="sech" data-el="2">
            <b>이 버전에서 바뀐 것</b>{' '}
            <span className="lbl">
              v{d.change_diff.from_version} → v{d.change_diff.to_version} · 항목 {changed}개
            </span>
          </div>
          <DiffBox diff={d.change_diff} el="2.1" />
          {/* 표다 — 어느 변경·담당이 행마다 같은 자리에서 끝나야 훑을 수 있다 */}
          <div className="atable" data-el="3">
            <div className="arow ahead">
              <span>영향받는 하위 항목 {n}건</span>
              <span>어느 변경</span>
              <span>담당</span>
            </div>
            {d.affected.map((a, i) => (
              <a className="arow" data-el={i === 0 ? '3.1' : undefined} key={refKey(a)} href={docPath(a.doc_id, a.item_id)} target="_blank" rel="noreferrer">
                <span>
                  <b className="mono">{refKey(a)}</b> {a.display_name}
                </span>
                <span className="lbl mono">← {a.caused_by_items.map((c) => '#' + c).join(', ')}</span>
                <span className="lbl">{a.assignee?.display_name ?? '담당 미지정'}</span>
              </a>
            ))}
          </div>
          {d.choice === 'undecided' && (
            <div className="skipbox" data-el="5">
              <b>전파하지 않으려면</b>
              <div className="skiprow">
                <input className="inp wide" data-el="5.2" placeholder="사유 (필수) — 예: 오탈자 수정" value={reason} onChange={(e) => setReason(e.target.value)} />
                <button className="btn" data-el="5.1" disabled={!reason.trim() || busy} onClick={() => decide('skip')}>
                  하위 전파 안 함
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="dfoot">
          {d.choice !== 'undecided' ? (
            <span>이미 결정됨: {d.choice}</span>
          ) : (
            <>
              <span>결정은 셋 중 하나이며 한 번 하면 바꿀 수 없다</span>
              <span className="grow" />
              <button className="btn" data-el="6" onClick={() => onClose(false)}>
                닫기 (미결정 유지)
              </button>
              <button className="btn solid" data-el="4" disabled={busy} onClick={() => decide('propagate')}>
                예 — {n}건에 확인 필요 붙이기
              </button>
            </>
          )}
        </div>
      </div>
    </>
  )
}
