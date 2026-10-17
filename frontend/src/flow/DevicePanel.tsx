/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 5.8 장비 상세 · 5.9 찾은 근거 · 5.10 쓰는 함수 — view_arc device-panel을 옮겼다(카드 CG).
 *  주소는 호스트·포트만 온다(INFRA C13) — 화면이 더 가리지 않는다. */
import { useMemo } from 'react'
import type { InfraNode } from './types'
import { type Model, displayName } from './model'

const KIND: Record<string, string> = {
  browser: '브라우저',
  backend: '백엔드 서버',
  db: '데이터베이스',
  cache: '캐시',
  storage: '파일 저장소',
  queue: '메시지 큐',
  search: '검색 엔진',
  api: '외부 API',
}
const WHERE: Record<string, string> = { local: '이 PC', container: '이 PC · 컨테이너', external: '외부 · 다른 컴퓨터나 클라우드' }

export function DevicePanel({ model, device, onOpen }: { model: Model; device: InfraNode; onOpen: (id: string) => void }) {
  const callers = useMemo(() => {
    const out: Array<{ id: string; calls: string[] }> = []
    for (const n of model.graph.nodes) {
      const calls = (n.steps ?? []).filter((s) => s.kind === 'call' && s.infra === device.id).map((s) => s.label)
      if (calls.length) out.push({ id: n.id, calls: [...new Set(calls)] })
    }
    return out
  }, [model, device])
  return (
    <>
      <div className="k">장비</div>
      <div data-el="5.8">
        <div className="nm">{device.name}</div>
        <div className="meta">
          {KIND[device.kind] ?? '장비'} · {WHERE[device.where]}
          {device.host && ` · ${device.host}`}
        </div>
      </div>
      <div className="k">찾은 근거</div>
      <div data-el="5.9">
        {device.evidence.map((e) => (
          <div className="row" key={e}>
            {e}
          </div>
        ))}
      </div>
      <div className="k">쓰는 함수 {callers.length}</div>
      <div data-el="5.10">
        {callers.length === 0 && <div className="meta">이 장비로 가는 호출을 코드에서 찾지 못했습니다</div>}
        {callers.map(({ id, calls }) => {
          const n = model.byId.get(id)!
          return (
            <div className="row" key={id} onClick={() => onOpen(id)} title={calls.join(' · ')}>
              {displayName(n)}
              <span className="sub">{calls.slice(0, 3).join(' · ')}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}
