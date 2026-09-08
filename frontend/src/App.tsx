/** 화면 흐름 — SYNC-UI-001 4장. 경로는 SYNC-UI-002 각 화면의 `경로`. */
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { DocView } from './pages/DocView'
import { Login } from './pages/Login'
import { ProjectDetail } from './pages/ProjectDetail'
import { ProjectInit } from './pages/ProjectInit'
import { ProjectList } from './pages/ProjectList'
import { Settings } from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Shell />}>
          <Route path="/" element={<ProjectList />} />
          <Route path="/projects/new" element={<ProjectInit />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/p/:code" element={<ProjectDetail />} />
          <Route path="/p/:code/d/:docId" element={<DocView />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
