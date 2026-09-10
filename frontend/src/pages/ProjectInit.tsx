/** UI-3 프로젝트 초기화 — SYNC-UI-002#UI-3. **UI-2 위의 다이얼로그**. UC-A1 사람 경로.
 *  1 헤더 · 2 입력 폼(2.1 주소, 2.2 코드, 2.3 이름, 2.4 코드 오류, 2.5 커밋될 것)
 *  3.1 초기화 · 3.2 취소 · 3.3 닫기(✕) · 4 기존 명세 발견(4.1 가져와서 등록, 4.2 취소) · 5 push 실패
 *  화면은 검사하지 않는다 — 서버가 코드 형식·중복 → 저장소 접근 → docs/specs 존재 순으로 판정한다. */
import { useState } from 'react'
import { api, ApiError } from '../api/client'

export function ProjectInit({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
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
      onDone()
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      const k = e.kind
      if (k === 'project-code-conflict') setCodeErr('이미 쓰이는 코드입니다')
      else if (k === 'project-code-invalid' || e.problem.status === 422) setCodeErr('영문 대문자 4자 이내여야 합니다')
      else if (k === 'repository-already-registered') setBanner(`이미 ${String(e.problem.code ?? '')} 프로젝트가 쓰는 저장소입니다`)
      else if (k === 'existing-specs') setExisting(Number(e.problem.doc_count ?? 0))
      else if (k === 'push-failed') setBanner(`push 실패: ${String(e.problem.reason ?? '')}. 만들던 작업물은 버렸습니다. 저장소 권한을 확인하세요.`)
      else if (k === 'not-implemented') setBanner('기존 명세 가져오기는 아직 구현되지 않았습니다(B4).')
      else setBanner(e.message)
      setExisting((x) => (k === 'existing-specs' ? x : null))
    }
  }

  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="dialog narrow initdlg" data-el="1">
        <div className="dhead">
          <b>프로젝트 초기화</b>
          <span className="grow" />
          <span className="x" data-el="3.3" onClick={onClose}>
            ✕
          </span>
        </div>
        <div className="dbody">
          <div className="form" data-el="2">
        <label>저장소 주소</label>
        <input className="inp wide mono" data-el="2.1" value={remote} onChange={(e) => setRemote(e.target.value)} placeholder="https://github.com/owner/repo" />
        <div className="lbl">싱크독이 이 저장소에 쓰기 권한이 있어야 합니다</div>
        <label>프로젝트 코드</label>
        <input className="inp mono" data-el="2.2" value={code} onChange={(e) => setCode(e.target.value)} placeholder="AIRD" style={{ width: 140 }} />
        <div className="lbl">
          영문 대문자 4자 이내. 문서 ID 앞부분이 됩니다 — 예: <code>AIRD-PRD-001</code>
        </div>
        {codeErr && (
          <div className="ferr" data-el="2.4">
            {codeErr}
          </div>
        )}
        <label>이름</label>
        <input className="inp wide" data-el="2.3" value={name} onChange={(e) => setName(e.target.value)} placeholder="에어데이터" />
        {/* 등록하면 저장소에 무엇이 생기는지. 기존 명세가 발견되면(빈 저장소가 아니면) 감춘다 */}
        {existing === null && (
          <div className="willcommit" data-el="2.5">
            <b>커밋될 것</b>
            <div className="mono">docs/specs/_templates/ · 12개</div>
            <div className="mono">docs/specs/{'{01-RFQ, 02-PRD, … , 11-CODE}'}/</div>
            <div className="mono">docs/specs/assets/</div>
          </div>
        )}
        {banner && (
          <div className="banner err" data-el="5">
            {banner}
          </div>
        )}
          </div>
        </div>
        <div className="dfoot">
          <span className="grow" />
          <button className="btn" data-el="3.2" onClick={onClose}>
            취소
          </button>
          {/* 주 동작. 취소와 같은 모양이면 어느 쪽이 진행인지 눈이 못 고른다 */}
          <button className="btn solid" data-el="3.1" onClick={() => submit(false)}>
            초기화
          </button>
        </div>
      </div>
      {existing !== null && (
        <div className="dialog" data-el="4" style={{ '--depth': 1 } as React.CSSProperties}>
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
    </>
  )
}
