/** UI-13 설정 — SYNC-UI-002#UI-13. 내 계정 · MCP 토큰 발급·폐기(원문은 발급 직후 한 번만) · 관리 입구. */
import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { api, type AccessToken, type User } from '../api/client'

const day = (iso: string) => iso.slice(5, 10).replace('-', '-')

export function Settings() {
  const { user } = useOutletContext<{ user: User }>()
  const [tokens, setTokens] = useState<AccessToken[]>([])
  const [label, setLabel] = useState('')
  const [issued, setIssued] = useState<AccessToken | null>(null)
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
    if (!confirm(`'${t.label}' 토큰을 폐기할까요? 그 토큰으로 오는 MCP 요청이 거부됩니다.`)) return
    await api.del(`/api/me/tokens/${t.id}`)
    load()
  }
  async function logout() {
    await api.post('/auth/logout')
    window.location.href = '/login'
  }
  return (
    <div className="page">
      <div className="phead" data-el="1">
        <b>설정</b>
      </div>
      <div className="form">
        <section className="grp" data-el="2">
          <h4>내 계정</h4>
          <div className="row">
            <span data-el="2.1">{user.github_login}</span> <span className="lbl">GitHub · {user.display_name}</span>
            <span className="grow" />
            <button className="btn sm" data-el="2.2" onClick={logout}>
              로그아웃
            </button>
          </div>
        </section>
        <section className="grp" data-el="3">
          <h4>
            MCP 토큰 <span className="lbl">에이전트가 싱크독에 붙을 때 씁니다. 남에게 주면 그 사람 작업이 내 이름으로 남습니다</span>
          </h4>
          {tokens.map((t) => (
            <div className={`row${t.revoked_at ? ' dimrow' : ''}`} data-el="3.1" key={t.id}>
              <b>{t.label}</b>{' '}
              <span className="lbl">
                발급 {day(t.issued_at)} · {t.expires_at ? `만료 ${day(t.expires_at)}` : '만료 없음'}
                {t.revoked_at && <s> · 폐기됨 {day(t.revoked_at)}</s>}
              </span>
              <span className="grow" />
              {!t.revoked_at && (
                <button className="btn sm" data-el="3.2" onClick={() => revoke(t)}>
                  폐기
                </button>
              )}
            </div>
          ))}
          <div className="row">
            <input className="inp" data-el="3.3" placeholder="이름 — 예: Gemini 노트북" value={label} onChange={(e) => setLabel(e.target.value)} />
            <button className="btn" data-el="3.4" disabled={!label.trim()} onClick={issue}>
              새 토큰 발급
            </button>
          </div>
        </section>
        {issued && (
          <div className="dialog" data-el="4">
            <div className="dhead">토큰 발급됨</div>
            <div className="dbody">
              <b>지금만 보입니다.</b> 닫으면 다시 볼 수 없습니다. 에이전트 설정에 붙여넣으세요.
              <div className="tokbox" data-el="4.1">
                {issued.token}
              </div>
              <div className="dacts">
                <button className="btn" data-el="4.2" onClick={() => navigator.clipboard.writeText(issued.token ?? '')}>
                  복사
                </button>{' '}
                <button className="btn" data-el="4.3" onClick={() => setIssued(null)}>
                  닫기
                </button>
              </div>
            </div>
          </div>
        )}
        <section className="grp" data-el="5">
          <h4>관리</h4>
          <div className="row">
            <span className="lbl">인덱스 재구축, 저장소 동기화 상태</span>
            <span className="grow" />
            <span className="btn sm" data-el="5.1" title="UI-14 — B4">
              관리로 →
            </span>
          </div>
        </section>
      </div>
    </div>
  )
}
