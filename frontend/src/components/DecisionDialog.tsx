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
      <div className="dialog wide" data-el="1">
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
          <div className="sech" data-el="2">
            <b>이 버전에서 바뀐 것</b>{' '}
            <span className="lbl">
              v{d.change_diff.from_version} → v{d.change_diff.to_version} · 항목 {changed}개
            </span>
          </div>
          <DiffBox diff={d.change_diff} el="2.1" />
          <div className="sech" data-el="3">
            <b>영향받는 하위 항목</b> <span className="lbl">{n}건</span>
          </div>
          <ul className="chk" data-el="3.1">
            {d.affected.map((a) => (
              <li key={refKey(a)}>
                <a href={docPath(a.doc_id, a.item_id)} target="_blank" rel="noreferrer">
                  <b>{refKey(a)}</b>
                </a>{' '}
                {a.display_name}{' '}
                <span className="lbl">
                  ← {a.caused_by_items.map((c) => '#' + c).join(', ')} · 담당 {a.assignee?.display_name ?? '미지정'}
                </span>
              </li>
            ))}
          </ul>
          {d.choice !== 'undecided' ? (
            <p className="lbl">이미 결정됨: {d.choice}</p>
          ) : (
            <div className="propacts">
              <div className="skipbox" data-el="5">
                <button className="btn" data-el="5.1" disabled={!reason.trim() || busy} onClick={() => decide('skip')}>
                  하위 전파 안 함
                </button>
                <input className="inp" data-el="5.2" placeholder="사유 (필수) — 예: 오탈자 수정" value={reason} onChange={(e) => setReason(e.target.value)} />
              </div>
              <span className="grow" />
              <button className="btn" data-el="4" style={{ fontWeight: 600 }} disabled={busy} onClick={() => decide('propagate')}>
                예 — {n}건에 확인 필요 붙이기
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
