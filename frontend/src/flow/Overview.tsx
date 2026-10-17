/** UI-19 흐름 보기 — SYNC-UI-002#UI-19. 5.1 개요 · 5.2 실행 기록 켜기 · 5.3 기록 목록 · 5.11 기록 지우기 (카드 CG·CK).
 *  기록은 서버가 띄우지 않는다 — 사람의 PC에서 기록 도구(싱크독_로컬 실행 파일의 하위 명령)가 띄우고 올린다(INFRA C12).
 *  명령의 `--to`는 이 화면을 연 서버 주소다. 목록은 이 화면이 보일 때 2초마다 다시 읽는다. */
import { useState } from 'react'
import type { FlowUnit, TraceBrief } from '../api/client'
import type { CodeGraph } from './types'
import type { Branch } from './TracePanel'

const TRACEABLE = new Set(['python', 'typescript', 'javascript', 'rust'])

/** 5.2 — 실행 단위마다 기록 도구 명령 */
function command(unit: FlowUnit, code: string, to: string): string | null {
  if (unit.kind === 'web') return `syncdoc-local trace-web --to ${to} --project ${code} --target http://localhost:${unit.port ?? 5173}`
  if (!unit.command) return null
  const cwd = unit.dir ? ` --cwd ${unit.dir}` : ''
  return `syncdoc-local trace --to ${to} --project ${code}${unit.kind === 'job' ? ' --job' : ''}${cwd} -- ${unit.command}`
}

export function Overview({
  code,
  graph,
  units,
  traces,
  tracesOk,
  branchOf,
  live,
  onLive,
  onPlay,
  onClear,
}: {
  code: string
  graph: CodeGraph
  units: FlowUnit[]
  traces: TraceBrief[]
  tracesOk: boolean
  branchOf: Map<number, Branch>
  live: boolean
  onLive: (v: boolean) => void
  onPlay: (t: TraceBrief) => void
  onClear: () => void
}) {
  const s = graph.stats
  const to = window.location.origin
  const [copied, setCopied] = useState<string | null>(null)
  const copy = (text: string) => {
    navigator.clipboard?.writeText(text)
    setCopied(text)
  }
  return (
    <>
      <div className="fvstat" data-el="5.1">
        <div>
          <b>{s.files ?? 0}</b>파일
        </div>
        <div>
          <b>{s.functions ?? 0}</b>함수
        </div>
        <div>
          <b>{s.routes ?? 0}</b>라우트
        </div>
        <div>
          <b>{graph.infra?.nodes.filter((n) => n.kind !== 'browser' && n.kind !== 'backend').length ?? 0}</b>장비
        </div>
      </div>
      <div className="k">
        실행 기록
        <label className="live">
          <input type="checkbox" checked={live} onChange={(e) => onLive(e.target.checked)} /> 실시간
        </label>
      </div>
      {traces.length === 0 && (
        <div data-el="5.2">
          <div className="meta">
            {tracesOk ? '아직 기록이 없습니다. 이 PC에서 띄우세요 — 싱크독_로컬 실행 파일이 있어야 합니다(개인 토큰을 묻습니다).' : '이 서버는 아직 실행 기록을 받지 않습니다.'}
          </div>
          {units.length === 0 && <div className="meta">실행 단위를 찾지 못했습니다 — 다음 코드 push에 생깁니다.</div>}
          {units.map((u) => {
            const cmd = command(u, code, to)
            const ready = TRACEABLE.has(u.lang)
            return (
              <div className="unit" key={`${u.dir}:${u.name}`}>
                <div className="meta">
                  {u.dir || '루트'} · {u.framework ?? u.kind} · {ready ? '기록 가능' : '이 언어는 아직 기록하지 못합니다'}
                  {u.kind === 'job' && ' · 작업은 실제로 돈다 — 모의 환경에서'}
                </div>
                {cmd && ready && (
                  <>
                    <pre className="cmd">{cmd}</pre>
                    <span className="btn sm" onClick={() => copy(cmd)}>
                      {copied === cmd ? '복사됨' : '복사'}
                    </span>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
      <div data-el="5.3">
        {traces.map((t) => {
          const b = branchOf.get(t.id)
          return (
            <div className="row trace" key={t.id} onClick={() => onPlay(t)} title={t.error ?? ''}>
              {b && <i className="dot" style={{ background: b.color }} />}
              <span className="m">{t.kind === 'job' ? '작업' : t.kind === 'front' ? '화면' : t.method}</span>
              <span className="lb">{t.path}</span>
              {t.truncated && <span className="chip">잘림</span>}
              <span className={`st ${t.status && t.status < 400 ? 'same' : 'code_only'}`}>{t.status ?? 'ERR'}</span>
              <span className="st">{t.ms}ms</span>
            </div>
          )
        })}
      </div>
      {traces.length > 0 && (
        <span
          className="btn sm"
          data-el="5.11"
          onClick={() => {
            if (confirm('이 프로젝트의 실행 기록을 다 지울까요?')) onClear()
          }}
        >
          기록 지우기
        </span>
      )}
    </>
  )
}
