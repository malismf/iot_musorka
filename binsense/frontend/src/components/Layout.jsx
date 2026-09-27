import { Trash2 } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp } from '../lib/store'

export default function Layout() {
  const { user, logout } = useApp()
  const location = useLocation()
  const wideMap = location.pathname === '/'

  return (
    <div className="app">
      <header className="header">
        <div className="logo">
          <Trash2 className="logo-icon" size={22} aria-hidden="true" />
          BinSense
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Карта
          </NavLink>
          <NavLink to="/list">Список</NavLink>
          <NavLink to="/events">События</NavLink>
          <NavLink to="/claim">Добавить</NavLink>
        </nav>
        <NavLink to="/profile" className="small muted">
          {user?.name || user?.email}
        </NavLink>
        <button className="small" onClick={logout}>
          Выйти
        </button>
      </header>
      <main className={wideMap ? 'content no-padding' : 'content'}>
        <Outlet />
      </main>
    </div>
  )
}
