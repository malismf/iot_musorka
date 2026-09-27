import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { formatDateTime, timeAgo } from '../lib/format'
import { useApp } from '../lib/store'

const TABS = [
  { key: 'devices', title: 'Устройства' },
  { key: 'users', title: 'Пользователи' },
  { key: 'audit', title: 'Журнал действий' },
]

export default function AdminPage() {
  const { user, toast } = useApp()
  const [tab, setTab] = useState('devices')

  if (user?.role !== 'admin') {
    return <div className="card">Раздел доступен только администратору.</div>
  }

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="tabs">
        {TABS.map((item) => (
          <button
            key={item.key}
            className={tab === item.key ? 'active' : ''}
            onClick={() => setTab(item.key)}
          >
            {item.title}
          </button>
        ))}
      </div>
      {tab === 'devices' && <DevicesTab toast={toast} />}
      {tab === 'users' && <UsersTab toast={toast} me={user} />}
      {tab === 'audit' && <AuditTab />}
    </div>
  )
}

function DevicesTab({ toast }) {
  const [devices, setDevices] = useState([])
  const [newId, setNewId] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setDevices(await api('/devices', { params: { include_unclaimed: true } }))
  }, [])

  useEffect(() => {
    load().catch((err) => setError(err.message))
  }, [load])

  const provision = async (event) => {
    event.preventDefault()
    setError('')
    setResult(null)
    try {
      const data = await api('/admin/devices', {
        method: 'POST',
        body: { device_id: newId.trim().toLowerCase(), hw: 'manual', reset_claim_code: true },
      })
      setResult(data)
      setNewId('')
      await load()
      toast('Устройство подготовлено')
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (id) => {
    if (!window.confirm(`Удалить ${id} вместе с историей?`)) return
    await api(`/admin/devices/${id}`, { method: 'DELETE' })
    await load()
    toast('Устройство удалено')
  }

  return (
    <>
      <form className="card" onSubmit={provision}>
        <h2>Подготовить устройство</h2>
        <p className="muted small">
          Обычно это делает скрипт <code>tools/provision.py</code> при подключённой плате. Здесь
          можно выдать учётные данные вручную — например, для эмулятора.
        </p>
        <div className="row">
          <input
            placeholder="bin-a1b2c3"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            style={{ maxWidth: 240 }}
            required
          />
          <button className="primary" type="submit">
            Выдать учётные данные
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        {result && (
          <pre
            className="small"
            style={{ background: '#f8fafc', padding: 10, borderRadius: 10, overflowX: 'auto' }}
          >
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </form>

      <div className="card">
        <h2>Все устройства</h2>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Название</th>
                <th>Статус</th>
                <th>Владелец</th>
                <th>Прошивка</th>
                <th>Данные</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {devices.map((device) => (
                <tr key={device.id}>
                  <td>
                    <Link to={`/devices/${device.id}`}>{device.id}</Link>
                  </td>
                  <td>{device.name || '—'}</td>
                  <td>
                    <span className={`badge ${device.status === 'active' ? 'ok' : ''}`}>
                      {device.status === 'active' ? 'привязано' : 'не привязано'}
                    </span>
                  </td>
                  <td>{device.owner_name || '—'}</td>
                  <td>{device.fw || '—'}</td>
                  <td>{timeAgo(device.last_seen)}</td>
                  <td>
                    <button className="small danger" onClick={() => remove(device.id)}>
                      Удалить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

function UsersTab({ toast, me }) {
  const [users, setUsers] = useState([])

  const load = useCallback(async () => setUsers(await api('/admin/users')), [])
  useEffect(() => {
    load().catch(() => {})
  }, [load])

  const changeRole = async (id, role) => {
    await api(`/admin/users/${id}`, { method: 'PATCH', body: { role } })
    await load()
    toast('Роль изменена')
  }

  return (
    <div className="card">
      <h2>Пользователи</h2>
      <table>
        <thead>
          <tr>
            <th>Почта</th>
            <th>Имя</th>
            <th>Роль</th>
            <th>Telegram</th>
            <th>Последний вход</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.email}</td>
              <td>{user.name}</td>
              <td>
                <select
                  value={user.role}
                  onChange={(e) => changeRole(user.id, e.target.value)}
                  disabled={user.id === me.id}
                  style={{ maxWidth: 160 }}
                >
                  <option value="admin">администратор</option>
                  <option value="dispatcher">диспетчер</option>
                  <option value="driver">водитель</option>
                </select>
              </td>
              <td>{user.telegram_linked ? '✅' : '—'}</td>
              <td>{formatDateTime(user.last_login_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AuditTab() {
  const [rows, setRows] = useState([])
  useEffect(() => {
    api('/admin/audit', { params: { limit: 200 } })
      .then(setRows)
      .catch(() => {})
  }, [])

  return (
    <div className="card">
      <h2>Журнал действий</h2>
      <table>
        <thead>
          <tr>
            <th>Время</th>
            <th>Пользователь</th>
            <th>Действие</th>
            <th>Устройство</th>
            <th>Детали</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{formatDateTime(row.created_at)}</td>
              <td>{row.user_email || '—'}</td>
              <td>{row.action}</td>
              <td>{row.device_id || '—'}</td>
              <td className="small muted">
                {Object.keys(row.details || {}).length ? JSON.stringify(row.details) : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
