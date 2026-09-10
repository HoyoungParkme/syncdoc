import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
// 순서가 중요하다 — 두 파일이 클래스를 여럿 공유하고 앱이 이기는 근거가 로드 순서뿐이다
import './styles.view.css'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
