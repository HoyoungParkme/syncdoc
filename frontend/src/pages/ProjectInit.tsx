/** UI-3 프로젝트 초기화 — SYNC-UI-002#UI-3. **UI-2 위의 다이얼로그**. UC-A1 사람 경로.
 *  1 헤더 · 2 입력 폼(2.7 저장 방식, 2.1 주소, 2.2 코드, 2.3 이름, 2.4 코드 오류, 2.5 커밋될 것)
 *  3.1 초기화 · 3.2 취소 · 3.3 닫기(✕) · 4 기존 명세 발견(4.1 가져와서 등록, 4.2 취소) · 5 push 실패
 *  화면은 검사하지 않는다 — 서버가 코드 형식·중복 → 저장소 접근 → docs/specs 존재 순으로 판정한다. */
import { useState } from 'react'
import { api, ApiError, type Storage } from '../api/client'
import { useEscape } from '../components/ui'

export function ProjectInit({
  onClose,
  onDone,
  storageModes,
  repoPrivate,
}: {
  onClose: () => void
  onDone: () => void
  /** 이 서버가 켠 저장 방식(/api/me). 하나면 고를 것이 없다 */
  storageModes: Storage[]
  /** 새 GitHub 저장소가 비공개인가(/api/me의 repo_private) — 2.6 문구 */
  repoPrivate: boolean
}) {
  // 2.7 저장 방식 — 둘 다 켰을 때만 고른다. **기본값이 없다** — 고를 때까지 초기화(3.1)가 꺼져 있다.
  // MCP가 사람에게 먼저 묻는 것과 같은 이유다(PRD R14, 카드 BA)
  const choose = storageModes.length > 1
  const [storage, setStorage] = useState<Storage | null>(choose ? null : (storageModes[0] ?? 'github'))
  const server = storage === 'server'
  const [remote, setRemote] = useState('')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [codeErr, setCodeErr] = useState('')
  // 4 — 기존 명세 발견. 서버 저장의 보관본이면 보관한 때(archivedAt)가 붙는다(UC-A1 3b)
  const [existing, setExisting] = useState<{ n: number; archivedAt: string | null } | null>(null)
  // 1.1 — Esc는 바깥 클릭과 같다. 기존 명세 발견(4)이 떠 있으면 그것만 닫는다 (#117)
  useEscape(onClose)
  useEscape(existing !== null ? () => setExisting(null) : null)
  const [banner, setBanner] = useState('')
  // 카드 F — 끄면 지금과 같다(없는 저장소면 push-failed). 켜면 저장소를 만들어 준다 — 비공개가 기본(#310).
  // 기본값을 거짓으로 두는 이유는 주소 오타가 조용히 새 저장소를 만들지 않게 하려는 것
  const [createRepo, setCreateRepo] = useState(false)

  async function submit(importExisting = false) {
    setCodeErr('')
    setBanner('')
    try {
      await api.post('/api/projects', {
        storage,
        remote_url: server ? null : remote,
        code,
        name,
        import_existing: importExisting,
        create_repo: server ? false : createRepo,
      })
      onDone()
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      const k = e.kind
      if (k === 'project-code-conflict') setCodeErr('이미 쓰이는 코드입니다')
      else if (k === 'storage-unavailable') setBanner('이 서버에서 켜지 않은 저장 방식입니다')
      else if (k === 'invalid-request' && JSON.stringify(e.problem.errors ?? '').includes('remote_url')) setBanner('GitHub 저장은 저장소 주소가 필요합니다')
      else if (k === 'project-code-invalid' || e.problem.status === 422) setCodeErr('영문 대문자 4자 이내여야 합니다')
      else if (k === 'repository-already-registered') setBanner(`이미 ${String(e.problem.code ?? '')} 프로젝트가 쓰는 저장소입니다`)
      else if (k === 'existing-specs')
        setExisting({ n: Number(e.problem.doc_count ?? 0), archivedAt: e.problem.archived_at ? String(e.problem.archived_at) : null })
      else if (k === 'push-failed') setBanner(`push 실패: ${String(e.problem.reason ?? '')}. 만들던 작업물은 버렸습니다. 저장소 권한을 확인하세요.`)
      // 저장소는 만들어졌을 수도 있다 — 앱이 남의 저장소를 지우지 않는다(카드 F)
      else if (k === 'repo-create-failed') setBanner(`저장소를 만들지 못했습니다: ${String(e.problem.reason ?? '')}`)
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
        {choose && (
          <>
            <label>저장 방식</label>
            <div className="seg" data-el="2.7">
              <label className="chk">
                <input type="radio" name="storage" checked={storage === 'github'} onChange={() => setStorage('github')} /> GitHub 저장소
              </label>
              <label className="chk">
                <input type="radio" name="storage" checked={storage === 'server'} onChange={() => setStorage('server')} /> 서버 저장소{' '}
                <span className="lbl">(GitHub 없이 이 서버에)</span>
              </label>
            </div>
          </>
        )}
        {!server && (
          <>
            <label>저장소 주소</label>
            <input className="inp wide mono" data-el="2.1" value={remote} onChange={(e) => setRemote(e.target.value)} placeholder="https://github.com/owner/repo" />
            <div className="lbl">싱크독이 이 저장소에 쓰기 권한이 있어야 합니다</div>
          </>
        )}
        <label>프로젝트 코드</label>
        <input className="inp mono" data-el="2.2" value={code} onChange={(e) => setCode(e.target.value)} placeholder="DEMO" style={{ width: 140 }} />
        <div className="lbl">
          영문 대문자 4자 이내. 문서 ID 앞부분이 됩니다 — 예: <code>DEMO-PRD-001</code>
        </div>
        {codeErr && (
          <div className="ferr" data-el="2.4">
            {codeErr}
          </div>
        )}
        <label>이름</label>
        <input className="inp wide" data-el="2.3" value={name} onChange={(e) => setName(e.target.value)} placeholder="데모 프로젝트" />
        {!server && (
          <label className="chk">
            <input type="checkbox" data-el="2.6" checked={createRepo} onChange={(e) => setCreateRepo(e.target.checked)} />{' '}
            저장소가 없으면 새로 만든다 <span className="lbl">({repoPrivate ? '비공개' : '공개'}로 만들어집니다)</span>
          </label>
        )}
        {/* 등록하면 저장소에 무엇이 생기는지. 기존 명세가 발견되면(빈 저장소가 아니면) 감춘다.
            배치(UI-002 UI-3 2.5)와 같은 글 — 빈 단계 디렉터리와 README뿐, 템플릿 사본은 안 넣는다(카드 AB, #199) */}
        {existing === null && (
          <div className="willcommit" data-el="2.5">
            <b>커밋될 것</b>
            {server && <div>이 서버 안에 저장소를 새로 만든다</div>}
            <div className="mono">docs/specs/{'{01-RFQ, 02-PRD, … , 11-CODE}'}/ · STD/</div>
            <div className="mono">docs/specs/assets/</div>
            <div className="mono">docs/specs/README.md — 규약 링크</div>
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
          <button className="btn solid" data-el="3.1" disabled={storage === null} onClick={() => submit(false)}>
            초기화
          </button>
        </div>
      </div>
      {existing !== null && (
        <>
          {/* 초기화(1) 위에 겹친다 — 자기 배경이 없으면 바깥 클릭이 아래 초기화까지 닫았다 */}
          <div className="backdrop" style={{ '--depth': 1 } as React.CSSProperties} onClick={() => setExisting(null)} />
          <div className="dialog" data-el="4" style={{ '--depth': 1 } as React.CSSProperties}>
            <div className="dhead">{existing.archivedAt ? '보관된 저장소' : '기존 명세 발견'}</div>
            <div className="dbody">
              {existing.archivedAt ? (
                <>
                  코드 <code>{code}</code>의 서버 저장소가 보관돼 있습니다. {existing.archivedAt.slice(0, 10)}에 보관, 문서 {existing.n}개. 되살려
                  가져와 등록할까요?
                </>
              ) : (
                <>
                  이 저장소에 이미 <code>docs/specs/</code>가 있습니다. 문서 {existing.n}개. 덮어쓰지 않고 그대로 가져와 등록할까요?
                </>
              )}
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
        </>
      )}
    </>
  )
}
