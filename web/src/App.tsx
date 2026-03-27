import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { ForgePage } from './pages/ForgePage'
import { DashboardPage } from './pages/DashboardPage'
import { LibraryPage } from './pages/LibraryPage'
import { PendingPage } from './pages/LibraryPage/PendingPage'
import { EnsemblesPage } from './pages/EnsemblesPage'

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex flex-col h-screen overflow-hidden">
        <NavBar />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Navigate to="/forge" replace />} />
            <Route path="/forge" element={<ForgePage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/library/pending" element={<PendingPage />} />
            <Route path="/ensembles" element={<EnsemblesPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
