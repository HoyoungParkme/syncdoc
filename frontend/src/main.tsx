import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
// 순서가 중요하다 — 두 파일이 클래스를 여럿 공유하고 앱이 이기는 근거가 로드 순서뿐이다
import './styles.view.css'
import './styles.css'

// 배포 전에 열어 둔 탭은 옛 코드가 돈다. 그 탭이 나중에 불러오는 조각(그림 등)을 못 찾으면
// 한 번 새로고침해 새 판이 된다 (SYNC-INFRA-001 4.1, #124). 30초 안에 또 나면 새로고침하지
// 않는다 — 서버가 정말 고장 났을 때 무한 새로고침을 막는다
const RELOADED = 'syncdoc.preloadReloadAt'
window.addEventListener('vite:preloadError', (ev) => {
  let last = 0
  try {
    last = Number(sessionStorage.getItem(RELOADED) ?? 0)
  } catch {
    // 저장소를 못 쓰는 창이면 새로고침하지 않는다 — 반복을 막을 길이 없다
    return
  }
  if (Date.now() - last < 30_000) return
  try {
    sessionStorage.setItem(RELOADED, String(Date.now()))
  } catch {
    return
  }
  ev.preventDefault()
  location.reload()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
