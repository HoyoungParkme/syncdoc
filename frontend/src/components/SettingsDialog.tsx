/** UI-13 설정 — SYNC-UI-002#UI-13. 어느 화면 위에서든 뜨는 다이얼로그. 닫으면 보던 화면 그대로.
 *  1 다이얼로그 · 2 내 계정(2.1 로그인 ID, 2.2 로그아웃) · 3 MCP 토큰(3.1 행, 3.2 폐기, 3.3 이름, 3.4 발급, 3.5 마지막 사용)
 *  4 토큰 원문 상자(4.1 원문, 4.2 복사) · 5 관리 카드(5.1 열기) · 6 관리 영역(UI-14) · 7 닫기(✕) · 8 클라이언트 설정(8.1 스니펫) · 9 닫기 */
import { useEffect, useState } from 'react'
import { ago, api, type AccessToken, type User } from '../api/client'
import { Admin } from '../pages/Admin'

const day = (iso: string) => iso.slice(5, 10)

export function SettingsDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const [tokens, setTokens] = useState<AccessToken[]>([])
  const [label, setLabel] = useState('')
  const [issued, setIssued] = useState<AccessToken | null>(null)
  // 규칙: 관리는 접힌 채로 연다. 인덱스 재구축이 위험한 동작이라 한 번 더 눌러야 보인다
  const [adminOpen, setAdminOpen] = useState(false)
  const load = () => api.get<AccessToken[]>('/api/me/tokens').then(setTokens)
  useEffect(() => {
    load()
  }, [])
  async function issue() {
    const t = await api.post<AccessToken>('/api/me/tokens', { label })
    setIssued(t)
    setLabel('')
    load()
  }
  async function revoke(t: AccessToken) {
    // 규칙: 폐기는 확인을 받는다. 되돌릴 수 없고 그 토큰을 쓰던 에이전트가 즉시 끊긴다
    if (!confirm(`'${t.label}' 토큰을 폐기할까요? 그 토큰으로 오는 MCP 요청이 거부됩니다.`)) return
    await api.del(`/api/me/tokens/${t.id}`)
    load()
  }
  const logout = () => {
    api.post('/auth/logout', {}).finally(() => (window.location.href = '/login'))
  }
  const snippet = `{
  "mcpServers": {
    "syncdoc": {
      "url": "${window.location.origin}/mcp",
      "headers": { "Authorization": "Bearer syncdoc_pat_…" }
    }
  }
}`
  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog setdlg" data-el="1">
        <div className="dhead">
          <span>설정</span>
          <span className="grow" />
          <span className="x" data-el="7" onClick={onClose}>
            ✕
          </span>
        </div>
        <div className="dbody">
          <section className="card" data-el="2">
            <div className="cardh">
              <b>내 계정</b>
            </div>
            <div className="row">
              <span data-el="2.1">{user.github_login}</span> <span className="lbl">GitHub · {user.display_name}</span>
              <span className="grow" />
              <button className="btn sm" type="button" data-el="2.2" onClick={logout}>
                로그아웃
              </button>
            </div>
          </section>

          <section className="card" data-el="3">
            <div className="cardh">
              <b>MCP 토큰</b>{' '}
              <span className="lbl">에이전트가 싱크독에 붙을 때 씁니다. 남에게 주면 그 사람 작업이 내 이름으로 남습니다</span>
            </div>
            {/* 원문은 발급 직후 여기서만 보인다. 서버는 해시만 저장해 다시 보여줄 수 없다 */}
            {issued?.token && (
              <div className="tokbox" data-el="4">
                <b>한 번만 보입니다. 지금 복사하세요.</b>
                <div className="tok" data-el="4.1">
                  {issued.token}
                </div>
                <button className="btn sm" type="button" data-el="4.2" onClick={() => navigator.clipboard.writeText(issued.token ?? '')}>
                  복사
                </button>
              </div>
            )}
            {tokens.map((t) => (
              <div className={`row${t.revoked_at ? ' dimrow' : ''}`} data-el="3.1" key={t.id}>
                <b>{t.label}</b>{' '}
                <span className="lbl">
                  발급 {day(t.issued_at)}
                  {t.revoked_at && <s> · 폐기됨 {day(t.revoked_at)}</s>}
                </span>
                <span className="grow" />
                {/* 만료가 없어 안 쓰는 토큰을 찾는 단서가 이것뿐이다 */}
                <span className="lbl" data-el="3.5">
                  마지막 사용 {t.last_used_at ? ago(t.last_used_at) : '없음'}
                </span>
                {!t.revoked_at && (
                  <button className="btn sm" type="button" data-el="3.2" onClick={() => revoke(t)}>
                    폐기
                  </button>
                )}
              </div>
            ))}
            <div className="row">
              <input
                className="inp"
                data-el="3.3"
                placeholder="이름 — 예: Gemini 노트북"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
              <button className="btn sm" type="button" data-el="3.4" disabled={!label.trim()} onClick={issue}>
                + 발급
              </button>
            </div>
          </section>

          <section className="card" data-el="8">
            <div className="cardh">
              <b>클라이언트 설정</b>
            </div>
            <p className="lbl">Claude Code · Codex · Gemini CLI가 같은 엔드포인트를 씁니다.</p>
            <pre className="snippet" data-el="8.1">{snippet}</pre>
          </section>

          <section className="card" data-el="5">
            <div className="cardh">
              <b>관리</b> <span className="lbl">인덱스 재구축 · 저장소 동기화</span>
              <span className="grow" />
              <button className="btn sm" type="button" data-el="5.1" onClick={() => setAdminOpen((o) => !o)}>
                {adminOpen ? '접기' : '열기'}
              </button>
            </div>
            {adminOpen && (
              <div className="admin" data-el="6">
                <Admin />
              </div>
            )}
          </section>
        </div>
        <div className="dfoot">
          <span className="grow" />
          <button className="btn" type="button" data-el="9" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    </>
  )
}
