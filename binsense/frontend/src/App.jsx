import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import Toasts from './components/Toasts'
import { useApp } from './lib/store'
import ClaimPage from './pages/ClaimPage'
import DevicePage from './pages/DevicePage'
import EventsPage from './pages/EventsPage'
import ListPage from './pages/ListPage'
import LoginPage from './pages/LoginPage'
import MapPage from './pages/MapPage'
import ProfilePage from './pages/ProfilePage'

function Protected({ children }) {
  const { user, ready } = useApp()
  const location = useLocation()
  if (!ready) return <div className="content muted">Загрузка…</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <Toasts />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <Protected>
              <Layout />
            </Protected>
          }
        >
          <Route index element={<MapPage />} />
          <Route path="list" element={<ListPage />} />
          <Route path="devices/:id" element={<DevicePage />} />
          <Route path="claim" element={<ClaimPage />} />
          <Route path="events" element={<EventsPage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
