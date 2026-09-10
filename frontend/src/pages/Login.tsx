/** UI-1 로그인 — SYNC-UI-002#UI-1. GitHub OAuth로. 유일하게 상단 바가 없다.
 *  1 로그인 영역(1.1 한 줄 설명) · 2 GitHub로 로그인 · 3 복귀 안내.
 *  **서버에서 아무것도 안 읽는다** — v1.2의 11단계 색 띠는 뺐다(UI-001 7장 5). */
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
        개발자가 PM 없이 11단계 명세 체인을 쓰고,
        <br />
        에이전트가 그 명세를 따르게 하는 플랫폼
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
