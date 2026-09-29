/** 공통 틀 — SYNC-UI-001 4장. 상단 바: 싱크독 · 사용 방법 · 설정 · 로그아웃.
 *  사용 방법(UI-16)과 설정(UI-13)은 경로가 없는 다이얼로그다 — 닫으면 보던 화면 그대로.
 *  UI-1만 예외. 프로젝트 전환 경로는 로고 하나다 — 목록 화면 자체가 고르는 화면이라 선택기가 겹친다. */
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type ProjectSummary, type Me } from '../api/client'

/** 질문 탭의 한 턴 — 질문, 진행 줄(8.9), 답, 본 것, 실패. 서버의 Turn을 화면 상태로 편 것 */
export interface AskTurnView {
  q: string
  prog: { kind: 'note' | 'read'; text: string }[]
  a?: string
  src?: string[]
  err?: string
}
/** 프로젝트 안에서 고른 대화(카드 AQ) — 문서·항목을 옮겨도 그대로다. 턴은 서버에 있어 DocView가 읽는다 */
export interface AskChat {
  code: string
  convId: number | null
  setConvId: (id: number | null) => void
}
import { HowTo } from './HowTo'
import { SettingsDialog } from './SettingsDialog'
import { ToastHost } from './ui'

export function Shell() {
  const nav = useNavigate()
  const loc = useLocation()
  const [user, setUser] = useState<Me | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [howTo, setHowTo] = useState(false)
  const [settings, setSettings] = useState(false)
  // UI-5 질문 탭 — 프로젝트 단위로 고른 대화(카드 AQ). 같은 프로젝트 안에서 문서·항목을 옮겨도 그대로고,
  // 프로젝트가 바뀌면 그 프로젝트의 목록이다. 턴은 서버에 있다 — 새로고침해도 남는다
  const askCode = loc.pathname.match(/^\/p\/([^/]+)/)?.[1] ?? ''
  const [askConv, setAskConv] = useState<{ code: string; id: number | null }>({ code: '', id: null })
  const setConvId = useCallback((id: number | null) => setAskConv({ code: askCode, id }), [askCode])
  const ask: AskChat = { code: askCode, convId: askConv.code === askCode ? askConv.id : null, setConvId }
  useEffect(() => {
    api
      .get<Me>('/api/me')
      .then(setUser)
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.problem.status === 401) nav(`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`)
      })
    api.get<ProjectSummary[]>('/api/projects').then(setProjects).catch(() => undefined)
  }, [nav, loc.pathname, loc.search])
  const logout = () => {
    api.post('/auth/logout', {}).finally(() => nav('/login'))
  }
  if (!user) return null
  return (
    <div className="app">
      <div className="topbar">
        <strong>
          <Link to="/">싱크독</Link>
        </strong>
        <span className="grow" />
        <button className="nav" type="button" onClick={() => setHowTo(true)}>
          사용 방법
        </button>
        <button className="nav" type="button" onClick={() => setSettings(true)}>
          설정
        </button>
        <button className="nav out" type="button" onClick={logout}>
          로그아웃
        </button>
      </div>
      <main className="screen">
        <Outlet context={{ user, projects, ask }} />
      </main>
      {howTo && <HowTo onClose={() => setHowTo(false)} />}
      {settings && <SettingsDialog user={user} onClose={() => setSettings(false)} />}
      <ToastHost />
    </div>
  )
}
