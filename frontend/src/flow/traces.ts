/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 실행 기록 목록 읽기(5.3, 2초마다)와 갈래 색 (카드 CG·CK). */
import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type TraceBrief } from '../api/client'
import type { Branch } from './TracePanel'

const POLL_MS = 2000
export const BRANCH_COLORS = ['#a3e635', '#c084fc', '#2dd4bf', '#fbbf24', '#f472b6', '#60a5fa', '#fb923c']

/** 기록 목록을 주기적으로 읽는다. 새 기록이 들어오면 onNew(가장 최근)를 부른다 — 처음 읽은 것은 빼고 */
export function useTraces(code: string, onNew: (t: TraceBrief) => void) {
  const [items, setItems] = useState<TraceBrief[]>([])
  const [ok, setOk] = useState(true)
  const seen = useRef<Set<number> | null>(null)
  const cb = useRef(onNew)
  useEffect(() => {
    cb.current = onNew
  }, [onNew])
  useEffect(() => {
    let alive = true
    let timer = 0
    const tick = async () => {
      if (document.visibilityState === 'visible') {
        try {
          const list = await api.get<TraceBrief[]>(`/api/projects/${code}/traces`)
          if (!alive) return
          setOk(true)
          const before = seen.current
          seen.current = new Set(list.map((t) => t.id))
          setItems((prev) => (prev.length === list.length && prev[0]?.id === list[0]?.id ? prev : list))
          const fresh = before ? list.find((t) => !before.has(t.id)) : undefined
          if (fresh) cb.current(fresh)
        } catch (e) {
          if (!alive) return
          setOk(false)
          // 기록 API가 없는 서버(옛 판) — 더 묻지 않는다
          if (e instanceof ApiError && e.problem.status === 404) return
        }
      }
      if (alive) timer = window.setTimeout(tick, POLL_MS)
    }
    tick()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [code])
  const clear = async () => {
    await api.del(`/api/projects/${code}/traces`)
    setItems([])
  }
  return { items, ok, clear }
}

/** 같은 API(방법·경로)의 기록이 실제로 간 길(사건 수·상태)로 갈래 색 — 먼저 들어온 갈래부터 */
export function branches(items: TraceBrief[]): Map<number, Branch> {
  const sigs = new Map<string, string[]>()
  const out = new Map<number, Branch>()
  for (const t of [...items].reverse()) {
    const key = `${t.kind} ${t.method} ${t.path.replace(/\/\d+(?=\/|$)/g, '/{n}')}`
    const sig = `${t.status}:${t.event_count}:${t.error ?? ''}`
    const list = sigs.get(key) ?? []
    if (!list.includes(sig)) list.push(sig)
    sigs.set(key, list)
    const n = list.indexOf(sig) + 1
    out.set(t.id, { n, of: 0, color: BRANCH_COLORS[(n - 1) % BRANCH_COLORS.length] })
  }
  for (const t of items) {
    const b = out.get(t.id)
    const key = `${t.kind} ${t.method} ${t.path.replace(/\/\d+(?=\/|$)/g, '/{n}')}`
    if (b) b.of = sigs.get(key)!.length
  }
  return out
}

