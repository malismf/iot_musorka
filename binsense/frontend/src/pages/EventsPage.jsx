import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import EventIcon from '../components/EventIcon'
import { EVENT_TITLES, formatDateTime } from '../lib/format'
import { useApp } from '../lib/store'

const FILTERS = [
  { key: 'all', title: 'Все' },
  { key: 'full', title: EVENT_TITLES.full },
]

export default function EventsPage() {
  const { events } = useApp()
  const [filter, setFilter] = useState('all')

  const rows = useMemo(() => {
    if (filter === 'all') return events
    return events.filter((e) => e.type === filter)
  }, [events, filter])

  return (
    <div className="card">
      <div className="row">
        <h1 style={{ margin: 0 }}>События</h1>
        <div className="spacer" />
        <div className="tabs" style={{ margin: 0 }}>
          {FILTERS.map((item) => (
            <button
              key={item.key}
              className={filter === item.key ? 'active small' : 'small'}
              onClick={() => setFilter(item.key)}
            >
              {item.title}
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 && <p className="muted small">Событий нет</p>}

      {rows.map((event) => (
        <div key={event.id} className="event-row">
          <EventIcon type={event.type} />
          <div style={{ flex: 1 }}>
            <div className="row" style={{ gap: 8 }}>
              <b>{EVENT_TITLES[event.type] || event.type}</b>
              <span className={`badge ${severityClass(event.severity)}`}>{event.severity}</span>
              {event.device_id && (
                <Link className="small" to={`/devices/${event.device_id}`}>
                  {event.device_name || event.device_id}
                </Link>
              )}
            </div>
            <div className="small">{event.message}</div>
            <div className="small muted">
              {formatDateTime(event.created_at)}
              {event.resolved_at ? ' · закрыто' : ''}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function severityClass(severity) {
  if (severity === 'warning') return 'warn'
  return 'info'
}
