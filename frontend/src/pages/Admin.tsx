/** UI-14 관리 — SYNC-UI-002#UI-14. 저장소 동기화 상태와 인덱스 재구축. 요소 번호 = data-el.
 *  **독립 화면이 아니라 UI-13 다이얼로그 안 관리 카드(6) 영역이다.** v1.2에서 별도 페이지를 없앴다.
 *  1 헤더 · 2 저장소 표(2.1 행, 2.2 마지막 처리 커밋, 2.3 동기화 상태) · 3 인덱스 재구축 · 4 확인(4.1 재구축, 4.2 취소)
 *  5 결과(5.1 집계, 5.2 규약 오류, 5.3 버린 것) · 2.4 마지막 백업 · 6 백업에서 복원 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ago, api, ApiError, docPath, type RebuildResult, type RepoStatus, type RestoreResult } from '../api/client'
import { toast, Tooltip } from '../components/ui'

/** 버린 추적 행의 종류 → 사람 말 */
const DROPPED_KO: Record<string, string> = { propagation_decision: '전파 결정', flag: '플래그', comment: '댓글', decision_item: '전파 결정의 항목' }

export function Admin() {
  const [repos, setRepos] = useState<RepoStatus[]>([])
  const [confirm, setConfirm] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ code: string; at: string; r: RebuildResult } | null>(null)
  const [restored, setRestored] = useState<{ code: string; at: string; r: RestoreResult } | null>(null)
  // 재구축(3)과 복원(6)이 같은 확인 다이얼로그를 쓴다. 무엇을 확인 중인지만 다르다
  const [confirmKind, setConfirmKind] = useState<'rebuild' | 'restore'>('rebuild')
  const load = useCallback(() => {
    api.get<RepoStatus[]>('/api/admin/repos').then(setRepos)
  }, [])
  useEffect(load, [load])
  async function rebuild(code: string) {
    setBusy(true)
    try {
      const r = await api.post<RebuildResult>(`/api/admin/repos/${code}/rebuild`, {})
      setResult({ code, at: new Date().toISOString(), r })
      setConfirm(null)
      load()
      toast(`${code} 인덱스를 다시 세웠습니다 — 문서 ${r.docs} · 항목 ${r.items} · 참조 ${r.references}`)
    } catch (e) {
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    } finally {
      setBusy(false)
    }
  }
  async function restore(code: string) {
    setBusy(true)
    try {
      const r = await api.post<RestoreResult>(`/api/admin/repos/${code}/restore`, {})
      setRestored({ code, at: new Date().toISOString(), r })
      setConfirm(null)
      load()
      toast(`${code} 백업에서 복원 — 플래그 ${r.flags} · 전파결정 ${r.decisions} · 댓글 ${r.comments}`)
    } catch (e) {
      alert(e instanceof ApiError ? `${e.kind}: ${e.message}` : String(e))
    } finally {
      setBusy(false)
    }
  }
  const badge = (r: RepoStatus) =>
    r.error ? (
      <Tooltip text={r.error}>
        <span className="st dr">조회 실패</span>
      </Tooltip>
    ) : r.behind_by == null ? (
      <span className="st na">문서 없음</span>
    ) : r.behind_by === 0 ? (
      <span className="st ok">최신</span>
    ) : (
      <span className="st rv">밀림 {r.behind_by}</span>
    )
  return (
    <div className="adminbody">
      <div className="adminh" data-el="1">
        <span className="lbl">위험한 동작이 있습니다</span>
      </div>
        <table className="vers" data-el="2">
          <thead>
            <tr>
              <th>프로젝트</th>
              <th>저장소</th>
              <th>마지막 처리 커밋</th>
              <th>동기화</th>
              <th>마지막 백업</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {repos.map((r, i) => (
              <tr key={r.code} data-el={i === 0 ? '2.1' : undefined}>
                <td>
                  <b>{r.code}</b>
                </td>
                <td className="lbl">{r.remote_url.replace(/^https?:\/\/(www\.)?github\.com\//, '').replace(/\.git$/, '')}</td>
                <td>
                  <a className="mono" data-el={i === 0 ? '2.2' : undefined} href={r.remote_url.startsWith('http') && r.last_processed_commit ? `${r.remote_url.replace(/\.git$/, '')}/commit/${r.last_processed_commit}` : undefined} target="_blank" rel="noreferrer">
                    {r.last_processed_commit?.slice(0, 7) ?? '—'}
                  </a>{' '}
                  {r.synced_at && <span className="lbl">{ago(r.synced_at)}</span>}
                </td>
                <td data-el={i === 0 ? '2.3' : undefined}>{badge(r)}</td>
                {/* 백업이 조용히 멈춘 것을 여기서 알아챈다 (INFRA 6.1) */}
                <td data-el={i === 0 ? '2.4' : undefined}>
                  {r.backed_up_at ? <span className={r.backup_stale ? 'warn' : 'lbl'}>{ago(r.backed_up_at)}</span> : <span className="lbl">없음</span>}
                </td>
                <td>
                  <span className="btn sm" data-el={i === 0 ? '3' : undefined} onClick={() => { setConfirmKind('rebuild'); setConfirm(r.code) }}>
                    인덱스 재구축
                  </span>{' '}
                  <span className="btn sm" data-el={i === 0 ? '6' : undefined} onClick={() => { setConfirmKind('restore'); setConfirm(r.code) }}>
                    백업에서 복원
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {confirm && (
          <>
            <div className="backdrop" style={{ '--depth': 1 } as React.CSSProperties} onClick={() => !busy && setConfirm(null)} />
            {/* UI-13 위에 한 겹 더 뜬다. 열린 깊이만큼 겹침 순서를 올린다(UI-001 3.3) */}
            <div className="dialog" data-el="4" style={{ '--depth': 1 } as React.CSSProperties}>
              <div className="dhead">{confirm} {confirmKind === 'rebuild' ? '인덱스 재구축' : '백업에서 복원'}</div>
              <div className="dbody">
                {confirmKind === 'rebuild' ? (
                  <>
                    저장소의 모든 MD를 다시 읽어 참조 관계와 버전 목록을 처음부터 만듭니다. <b>플래그·전파 결정·댓글은 건드리지 않습니다.</b> 문서가 많으면 몇 분 걸립니다.
                  </>
                ) : (
                  <>
                    <b>backup/tracking.json</b>의 플래그·전파 결정·댓글을 되붙입니다. 이미 있는 행은 건너뜁니다. <b>댓글 본문은 돌아오지 않습니다</b> — 공개 저장소라 백업에 싣지 않았습니다. 인덱스 재구축을 먼저 하세요.
                  </>
                )}
                <div className="dacts">
                  <button className="btn" data-el="4.2" disabled={busy} onClick={() => setConfirm(null)}>
                    취소
                  </button>
                  <button
                    className="btn"
                    data-el="4.1"
                    style={{ fontWeight: 600 }}
                    disabled={busy}
                    onClick={() => (confirmKind === 'rebuild' ? rebuild(confirm) : restore(confirm))}
                  >
                    {busy ? '도는 중…' : confirmKind === 'rebuild' ? '재구축' : '복원'}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
        {result && (
          <section className="grp" data-el="5">
            <h4>
              재구축 결과 <span className="lbl">{result.code} · {ago(result.at)}</span>
            </h4>
            <div className="row">
              <span data-el="5.1">
                문서 {result.r.docs} · 항목 {result.r.items} · 참조 {result.r.references} · 버전 {result.r.versions}
              </span>
            </div>
            <div className="row">
              <span data-el="5.2">
                규약 오류 {result.r.convention_errors.length}
                {result.r.convention_errors.map((e) => (
                  <span key={e.doc_id}>
                    {' '}
                    — <Link to={docPath(e.doc_id)}>{e.doc_id}</Link> {e.detail.split('\n')[0]}
                  </span>
                ))}
              </span>
            </div>
            {result.r.dropped.length > 0 && (
              <div className="row">
                {/* 확인 문구가 "건드리지 않습니다"라고 약속하므로 예외는 말해야 한다 (#38) */}
                <span className="warn" data-el="5.3">
                  버린 것 {result.r.dropped.reduce((n, d) => n + d.count, 0)} —{' '}
                  {result.r.dropped.map((d) => `${DROPPED_KO[d.kind] ?? d.kind} ${d.count}건 · ${d.reason}`).join(' / ')}
                </span>
              </div>
            )}
          </section>
        )}
        {restored && (
          <section className="grp">
            <h4>
              복원 결과 <span className="lbl">{restored.code} · {ago(restored.at)}</span>
            </h4>
            <div className="row">
              <span>
                플래그 {restored.r.flags} · 전파결정 {restored.r.decisions} · 댓글 {restored.r.comments}
                {restored.r.skipped > 0 && <span className="lbl"> · 이미 있어서 건너뜀 {restored.r.skipped}</span>}
              </span>
            </div>
            {restored.r.dropped.length > 0 && (
              <div className="row">
                <span className="warn">
                  버린 것 {restored.r.dropped.reduce((n, d) => n + d.count, 0)} —{' '}
                  {restored.r.dropped.map((d) => `${DROPPED_KO[d.kind] ?? d.kind} ${d.count}건 · ${d.reason}`).join(' / ')}
                </span>
              </div>
            )}
          </section>
        )}
    </div>
  )
}
