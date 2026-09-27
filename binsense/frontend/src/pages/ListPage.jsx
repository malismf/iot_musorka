import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import FillBar from '../components/FillBar'
import { statusLabel, timeAgo } from '../lib/format'
import { useApp } from '../lib/store'

const COLUMNS = [
  { key: 'name', title: 'Контейнер' },
  { key: 'fill', title: 'Заполненность' },
  { key: 'rssi', title: 'Wi-Fi' },
  { key: 'last_seen', title: 'Данные' },
  { key: 'status', title: 'Состояние' },
]

export default function ListPage() {
  const { devices } = useApp()
  const [sort, setSort] = useState({ key: 'fill', desc: true })
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    const text = query.trim().toLowerCase()
    const filtered = devices.filter(
      (d) =>
        !text ||
        (d.name || '').toLowerCase().includes(text) ||
        (d.address || '').toLowerCase().includes(text) ||
        d.id.includes(text),
    )
    const factor = sort.desc ? -1 : 1
    return [...filtered].sort((a, b) => {
      const va = a[sort.key] ?? (typeof a[sort.key] === 'string' ? '' : -1)
      const vb = b[sort.key] ?? (typeof b[sort.key] === 'string' ? '' : -1)
      if (va === vb) return 0
      return va > vb ? factor : -factor
    })
  }, [devices, sort, query])

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>Контейнеры</h1>
        <span className="muted small">{rows.length} шт.</span>
        <div className="spacer" />
        <input
          placeholder="Поиск по названию или адресу"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ maxWidth: 280 }}
        />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  onClick={() =>
                    setSort((prev) => ({ key: column.key, desc: prev.key === column.key ? !prev.desc : true }))
                  }
                >
                  {column.title}
                  {sort.key === column.key ? (sort.desc ? ' ↓' : ' ↑') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((device) => (
              <tr key={device.id}>
                <td>
                  <Link to={`/devices/${device.id}`}>{device.name || device.id}</Link>
                  <div className="small muted">{device.address}</div>
                </td>
                <td style={{ minWidth: 150 }}>
                  <FillBar device={device} />
                </td>
                <td>{device.rssi !== null && device.rssi !== undefined ? `${device.rssi} dBm` : '—'}</td>
                <td>{timeAgo(device.last_seen)}</td>
                <td>
                  <span className={`badge ${badgeClass(device)}`}>{statusLabel(device)}</span>
                  {device.open_events > 0 && (
                    <span className="badge danger" style={{ marginLeft: 6 }}>
                      {device.open_events}
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="muted">
                  Ничего не найдено
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function badgeClass(device) {
  if (!device.online) return ''
  if (!device.calibrated) return 'info'
  if (device.fill >= (device.full_pct ?? 80)) return 'danger'
  return 'ok'
}
