/** UI-3 프로젝트 초기화 — SYNC-UI-002#UI-3. UC-A1 사람 경로. 화면은 검사하지 않는다 — 서버가 판정. */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'

export function ProjectInit() {
  const nav = useNavigate()
  const [remote, setRemote] = useState('')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [codeErr, setCodeErr] = useState('')
  const [existing, setExisting] = useState<number | null>(null)
  const [banner, setBanner] = useState('')

  async function submit(importExisting = false) {
    setCodeErr('')
    setBanner('')
    try {
      await api.post('/api/projects', { remote_url: remote, code, name, import_existing: importExisting })
      nav('/')
      window.location.reload()
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      const k = e.kind
      if (k === 'project-code-conflict') setCodeErr('이미 쓰이는 코드입니다')
      else if (k === 'project-code-invalid' || e.problem.status === 422) setCodeErr('영문 대문자 4자 이내여야 합니다')
      else if (k === 'existing-specs') setExisting(Number(e.problem.doc_count ?? 0))
      else if (k === 'push-failed') setBanner(`push 실패: ${String(e.problem.reason ?? '')}. 만들던 작업물은 버렸습니다. 저장소 권한을 확인하세요.`)
      else if (k === 'not-implemented') setBanner('기존 명세 가져오기는 아직 구현되지 않았습니다(B4).')
      else setBanner(e.message)
      setExisting((x) => (k === 'existing-specs' ? x : null))
    }
  }

  return (
    <div className="page">
      <div className="phead" data-el="1">
        <b>프로젝트 초기화</b>
      </div>
      <div className="form" data-el="2">
        <label>저장소 주소</label>
        <input className="inp wide" data-el="2.1" value={remote} onChange={(e) => setRemote(e.target.value)} placeholder="https://github.com/org/repo" />
        <div className="lbl">싱크독이 이 저장소에 쓰기 권한이 있어야 합니다</div>
        <label>프로젝트 코드</label>
        <input className="inp" data-el="2.2" value={code} onChange={(e) => setCode(e.target.value)} style={{ width: 100 }} />
        <div className="lbl">영문 대문자 4자 이내. 문서 ID 앞부분이 됩니다 — 예: AIRD-PRD-001</div>
        {codeErr && (
          <div className="ferr" data-el="2.4">
            {codeErr}
          </div>
        )}
        <label>이름</label>
        <input className="inp wide" data-el="2.3" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="facts">
          <button className="btn" data-el="3.2" onClick={() => nav('/')}>
            취소
          </button>
          <button className="btn" data-el="3.1" style={{ fontWeight: 600 }} onClick={() => submit(false)}>
            초기화
          </button>
        </div>
      </div>
      {existing !== null && (
        <div className="dialog" data-el="4">
          <div className="dhead">기존 명세 발견</div>
          <div className="dbody">
            이 저장소에 이미 <code>docs/specs/</code>가 있습니다. 문서 {existing}개. 덮어쓰지 않고 그대로 가져와 등록할까요?
            <div className="dacts">
              <button className="btn" data-el="4.2" onClick={() => setExisting(null)}>
                취소
              </button>{' '}
              <button className="btn" data-el="4.1" style={{ fontWeight: 600 }} onClick={() => submit(true)}>
                가져와서 등록
              </button>
            </div>
          </div>
        </div>
      )}
      {banner && (
        <div className="banner err" data-el="5">
          {banner}
        </div>
      )}
    </div>
  )
}
