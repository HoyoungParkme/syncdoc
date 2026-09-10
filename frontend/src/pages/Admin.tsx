/** UI-14 관리 — SYNC-UI-002#UI-14. 저장소 동기화 상태와 인덱스 재구축. 요소 번호 = data-el.
 *  **독립 화면이 아니라 UI-13 다이얼로그 안 관리 카드(6) 영역이다.** v1.2에서 별도 페이지를 없앴다.
 *  1 헤더 · 2 저장소 표(2.1 행, 2.2 마지막 처리 커밋, 2.3 동기화 상태) · 3 인덱스 재구축 · 4 확인(4.1 재구축, 4.2 취소) · 5 결과(5.1 집계, 5.2 규약 오류) */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ago, api, ApiError, docPath, type RebuildResult, type RepoStatus } from '../api/client'
import { toast, Tooltip } from '../components/ui'

export function Admin() {
  const [repos, setRepos] = useState<RepoStatus[]>([])
  const [confirm, setConfirm] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ code: string; at: string; r: RebuildResult } | null>(null)
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
                <td>
                  <span className="btn sm" data-el={i === 0 ? '3' : undefined} onClick={() => setConfirm(r.code)}>
                    인덱스 재구축
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
              <div className="dhead">{confirm} 인덱스 재구축</div>
              <div className="dbody">
                저장소의 모든 MD를 다시 읽어 참조 관계와 버전 목록을 처음부터 만듭니다. <b>플래그·전파 결정·댓글은 건드리지 않습니다.</b> 문서가 많으면 몇 분 걸립니다.
                <div className="dacts">
                  <button className="btn" data-el="4.2" disabled={busy} onClick={() => setConfirm(null)}>
                    취소
                  </button>
                  <button className="btn" data-el="4.1" style={{ fontWeight: 600 }} disabled={busy} onClick={() => rebuild(confirm)}>
                    {busy ? '재구축 중…' : '재구축'}
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
          </section>
        )}
    </div>
  )
}
