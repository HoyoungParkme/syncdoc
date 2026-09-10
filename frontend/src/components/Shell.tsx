/** 공통 틀 — SYNC-UI-001 4장. 상단 바: 싱크독 · 사용 방법 · 내 할 일 n · 설정 · 로그아웃.
 *  UI-1만 예외. 프로젝트 전환 경로는 로고 하나다 — 목록 화면 자체가 고르는 화면이라 선택기가 겹친다. */
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api, ApiError, type ProjectSummary, type Todo, type User } from '../api/client'
import { HowTo } from './HowTo'

export function Shell() {
  const nav = useNavigate()
  const loc = useLocation()
  const [user, setUser] = useState<User | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [todoCount, setTodoCount] = useState(0)
  const [howTo, setHowTo] = useState(false)
  useEffect(() => {
    api.get<Todo>('/api/todo').then((t) => setTodoCount(t.total)).catch(() => undefined)
    api
      .get<User>('/api/me')
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
        <Link className="nav todo" to="/todo">
          내 할 일{todoCount > 0 && <span className="badge">{todoCount}</span>}
        </Link>
        <Link className="nav" to="/settings">
          설정
        </Link>
        <button className="nav out" type="button" onClick={logout}>
          로그아웃
        </button>
      </div>
      <main className="screen">
        <Outlet context={{ user, projects }} />
      </main>
      {howTo && <HowTo onClose={() => setHowTo(false)} />}
    </div>
  )
}
