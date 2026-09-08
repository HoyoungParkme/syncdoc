/** UI-1 로그인 — SYNC-UI-002#UI-1. GitHub OAuth로. 유일하게 상단 바가 없다. */
import { useSearchParams } from 'react-router-dom'

export function Login() {
  const [sp] = useSearchParams()
  const next = sp.get('next') ?? '/'
  return (
    <div className="login" data-el="1">
      <div className="logo">
        <b>싱크독</b> <span className="lbl">SyncDoc</span>
      </div>
      <p className="lbl" data-el="1.1">
        같이 일하는 사람만 들어옵니다. 저장소 접근 권한이 곧 접근 권한입니다.
      </p>
      <a className="btn big" data-el="2" href={`/auth/github?next=${encodeURIComponent(next)}`}>
        GitHub로 로그인
      </a>
      <p className="lbl" data-el="3">
        로그인 후 원래 가려던 화면으로 돌아갑니다
      </p>
    </div>
  )
}
