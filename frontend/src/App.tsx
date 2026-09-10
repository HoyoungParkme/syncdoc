/** 화면 흐름 — SYNC-UI-001 4장. 경로는 SYNC-UI-002 각 화면의 `경로`. */
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { Admin } from './pages/Admin'
import { DocView } from './pages/DocView'
import { Graph } from './pages/Graph'
import { History } from './pages/History'
import { ReadOrder } from './pages/ReadOrder'
import { FlagView } from './pages/FlagView'
import { Login } from './pages/Login'
import { ProjectDetail } from './pages/ProjectDetail'
import { ProjectInit } from './pages/ProjectInit'
import { ProjectList } from './pages/ProjectList'
import { Settings } from './pages/Settings'
import { Todo } from './pages/Todo'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Shell />}>
          <Route path="/" element={<ProjectList />} />
          <Route path="/projects/new" element={<ProjectInit />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/todo" element={<Todo />} />
          <Route path="/todo/flags/:flagId" element={<FlagView />} />
          <Route path="/p/:code" element={<ProjectDetail />} />
          <Route path="/p/:code/d/:docId" element={<DocView />} />
          <Route path="/p/:code/d/:docId/history" element={<History />} />
          <Route path="/p/:code/graph" element={<Graph />} />
          <Route path="/p/:code/read" element={<ReadOrder />} />
          <Route path="/settings/admin" element={<Admin />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
