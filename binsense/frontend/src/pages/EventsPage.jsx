import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { EVENT_ICONS, EVENT_TITLES, formatDateTime } from '../lib/format'
import { useApp } from '../lib/store'

const FILTERS = [
  { key: 'all', title: 'Все' },
  { key: 'open', title: 'Неподтверждённые' },
  { key: 'critical', title: 'Критичные' },
]

export default function EventsPage() {
  const { events, ackEvent, toast } = useApp()
  const [filter, setFilter] = useState('all')

  const rows = useMemo(() => {
    if (filter === 'open') return events.filter((e) => e.needs_ack && !e.acked_at)
    if (filter === 'critical') return events.filter((e) => e.severity === 'critical')
    return events
  }, [events, filter])

  const ack = async (event) => {
    try {
      await ackEvent(event.id)
      toast('Событие подтверждено')
    } catch (err) {
      toast(err.message, 'warning')
    }
  }

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
          <span className="event-icon">{EVENT_ICONS[event.type] || 'ℹ️'}</span>
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
              {event.acked_at
                ? ` · подтверждено ${event.acked_by_name || ''} ${formatDateTime(event.acked_at)}`
                : ''}
              {event.resolved_at ? ' · закрыто' : ''}
            </div>
          </div>
          {event.needs_ack && !event.acked_at && (
            <button className="small" onClick={() => ack(event)}>
              Принято
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

function severityClass(severity) {
  if (severity === 'critical') return 'danger'
  if (severity === 'warning') return 'warn'
  return 'info'
}
