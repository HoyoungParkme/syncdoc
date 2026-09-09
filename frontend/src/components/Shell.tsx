/** 공통 틀 — SYNC-UI-001 3장. 상단 바: 싱크독 · [프로젝트 ▾] · [내 할 일 ●n] · [설정]. UI-1만 예외. */
import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api, ApiError, type ProjectSummary, type Todo, type User } from '../api/client'

export function Shell() {
  const nav = useNavigate()
  const loc = useLocation()
  const { code } = useParams()
  const [user, setUser] = useState<User | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [todoCount, setTodoCount] = useState(0)
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
  if (!user) return null
  return (
    <div className="app">
      <div className="topbar">
        <strong>
          <Link to="/">싱크독</Link>
        </strong>
        <select className="btn" value={code ?? ''} onChange={(e) => e.target.value && nav(`/p/${e.target.value}`)} aria-label="프로젝트">
          <option value="">프로젝트 ▾</option>
          {projects.map((p) => (
            <option key={p.code} value={p.code}>
              {p.code} {p.name}
            </option>
          ))}
        </select>
        <span className="grow" />
        <Link className="btn" to="/todo">
          내 할 일{todoCount > 0 && <span className="badge">{todoCount}</span>}
        </Link>
        <Link className="btn" to="/settings">
          설정
        </Link>
      </div>
      <Outlet context={{ user, projects }} />
    </div>
  )
}
