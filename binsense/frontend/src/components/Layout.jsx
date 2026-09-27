import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp } from '../lib/store'

export default function Layout() {
  const { user, logout, stats } = useApp()
  const location = useLocation()
  const wideMap = location.pathname === '/'

  return (
    <div className="app">
      <header className="header">
        <div className="logo">🗑️ BinSense</div>
        <nav className="nav">
          <NavLink to="/" end>
            Карта
          </NavLink>
          <NavLink to="/list">Список</NavLink>
          <NavLink to="/events">
            События
            {stats && stats.open_events > 0 ? ` (${stats.open_events})` : ''}
          </NavLink>
          <NavLink to="/claim">Добавить</NavLink>
          {user?.role === 'admin' && <NavLink to="/admin">Админ</NavLink>}
        </nav>
        <NavLink to="/profile" className="small muted">
          {user?.name || user?.email} · {roleLabel(user?.role)}
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

export function roleLabel(role) {
  return { admin: 'администратор', dispatcher: 'диспетчер', driver: 'водитель' }[role] || role
}
