/** UI-19 흐름 보기 — SYNC-UI-002#UI-19 (카드 CG). 경로 `/p/:code/flow`.
 *  흐름(GET /api/projects/{code}/flow)과 판(GET /api/local — 싱크독_로컬만 200)을 받고, 장면은 three.js와 함께
 *  이 화면을 열 때만 불러온다(flow/FlowScreen — 동적 import). 불러오는 동안 장면 자리에 「장면을 불러오는 중」. */
import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import { api, ApiError, type FlowView, type Me, type ProjectSummary } from '../api/client'
import { ProjName } from '../components/ui'

const FlowScreen = lazy(() => import('../flow/FlowScreen'))

export function Flow() {
  const { code = '' } = useParams()
  const { projects } = useOutletContext<{ user: Me; projects: ProjectSummary[] }>()
  const projName = projects.find((p) => p.code === code)?.name
  const [view, setView] = useState<FlowView | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [local, setLocal] = useState(false)
  useEffect(() => {
    let alive = true
    api
      .get<FlowView>(`/api/projects/${code}/flow`)
      .then((v) => alive && setView(v))
      .catch((e) => alive && setErr(e instanceof ApiError ? (e.problem.detail ?? e.problem.title) : String(e)))
    api
      .get('/api/local')
      .then(() => alive && setLocal(true))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [code])
  if (!view)
    return (
      <div className="docscreen fvscreen">
        <div className="docbar">
          <Link className="crumb" to={`/p/${code}`}>
            <ProjName code={code} name={projName} />
          </Link>
          <span className="sep">›</span>
          <b>흐름 보기</b>
          <span className="grow" />
          <span className="lbl">{err ?? '불러오는 중…'}</span>
        </div>
      </div>
    )
  return (
    <Suspense
      fallback={
        <div className="docscreen fvscreen">
          <div className="fvloading">장면을 불러오는 중</div>
        </div>
      }
    >
      <FlowScreen code={code} projName={projName} view={view} local={local} />
    </Suspense>
  )
}
