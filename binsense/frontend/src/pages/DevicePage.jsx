import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Line } from 'react-chartjs-2'
import { useNavigate, useParams } from 'react-router-dom'
import MapPicker from '../components/MapPicker'
import { api } from '../lib/api'
import {
  EVENT_ICONS,
  fillColor,
  fillLabel,
  formatDateTime,
  formatDuration,
  statusLabel,
  timeAgo,
} from '../lib/format'
import { useApp } from '../lib/store'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler)

const RANGES = [
  { key: 24, bucket: '5m', title: 'Сутки' },
  { key: 24 * 7, bucket: '1h', title: 'Неделя' },
  { key: 24 * 30, bucket: '1d', title: 'Месяц' },
]

export default function DevicePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { devices, publicConfig, toast, refreshAll, user } = useApp()
  const [device, setDevice] = useState(null)
  const [points, setPoints] = useState([])
  const [events, setEvents] = useState([])
  const [forecast, setForecast] = useState(null)
  const [range, setRange] = useState(RANGES[0])
  const [error, setError] = useState('')

  const live = devices.find((d) => d.id === id)

  const load = useCallback(async () => {
    try {
      const [deviceData, eventsData, forecastData] = await Promise.all([
        api(`/devices/${id}`),
        api(`/devices/${id}/events`, { params: { limit: 30 } }),
        api(`/devices/${id}/forecast`),
      ])
      setDevice(deviceData)
      setEvents(eventsData)
      setForecast(forecastData)
    } catch (err) {
      setError(err.message)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    api(`/devices/${id}/telemetry`, { params: { hours: range.key, bucket: range.bucket } })
      .then(setPoints)
      .catch((err) => setError(err.message))
  }, [id, range])

  // живые данные из WebSocket подмешиваем в карточку
  useEffect(() => {
    if (live) setDevice((prev) => (prev ? { ...prev, ...live } : prev))
  }, [live])

  if (error) return <div className="card error">{error}</div>
  if (!device) return <div className="card muted">Загрузка…</div>

  const labels = points.map((p) => formatDateTime(p.ts))
  // при небольшом числе точек показываем их явно, иначе линия «теряется»
  const pointRadius = points.length <= 40 ? 3 : 0
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { display: true, position: 'bottom' } },
    scales: { x: { ticks: { maxTicksLimit: 8 } } },
  }

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="card">
        <div className="row">
          <div>
            <h1 style={{ marginBottom: 4 }}>{device.name || device.id}</h1>
            <div className="muted small">
              {device.address || 'адрес не указан'} · {device.id} · прошивка {device.fw || '—'}
            </div>
          </div>
          <div className="spacer" />
          <span className={`badge ${device.online ? 'ok' : ''}`}>{statusLabel(device)}</span>
          <button onClick={load}>Обновить</button>
          <button onClick={() => navigate('/')}>На карту</button>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Сейчас</h2>
          <div className="gauge" style={{ marginBottom: 10 }}>
            <span className="value" style={{ color: fillColor(device) }}>
              {fillLabel(device)}
            </span>
            <span className="muted">заполненность</span>
          </div>
          <table>
            <tbody>
              <Row label="Расстояние до мусора">
                {device.dist_mm ? `${(device.dist_mm / 10).toFixed(0)} см` : '—'}
              </Row>
              <Row label="Глубина контейнера (калибровка)">
                {device.empty_mm ? `${(device.empty_mm / 10).toFixed(0)} см` : 'не откалиброван'}
              </Row>
              <Row label="Wi-Fi">{device.rssi ? `${device.rssi} dBm` : '—'}</Row>
              <Row label="Последние данные">
                {timeAgo(device.last_seen)} ({formatDateTime(device.last_seen)})
              </Row>
              <Row label="Объём">{device.volume_l ? `${device.volume_l} л` : '—'}</Row>
              <Row label="Настройки">
                {device.config_applied_version === device.config_version ? (
                  <span className="badge ok">применены (v{device.config_version})</span>
                ) : (
                  <span className="badge warn">
                    ожидают применения (v{device.config_version}, на устройстве v
                    {device.config_applied_version ?? '—'})
                  </span>
                )}
              </Row>
            </tbody>
          </table>
          {forecast && (
            <p className="small" style={{ marginTop: 10 }}>
              <b>Прогноз:</b>{' '}
              {forecast.hours_to_full !== null && forecast.hours_to_full !== undefined
                ? `заполнится через ${formatDuration(forecast.hours_to_full)} (${formatDateTime(
                    forecast.eta,
                  )})`
                : forecast.note || 'недостаточно данных'}
              {forecast.rate_pct_per_day ? ` · скорость ${forecast.rate_pct_per_day}%/сутки` : ''}
            </p>
          )}
        </div>

        <div className="card">
          <div className="row" style={{ marginBottom: 8 }}>
            <h2 style={{ margin: 0 }}>История</h2>
            <div className="spacer" />
            <div className="tabs" style={{ margin: 0 }}>
              {RANGES.map((item) => (
                <button
                  key={item.key}
                  className={range.key === item.key ? 'active small' : 'small'}
                  onClick={() => setRange(item)}
                >
                  {item.title}
                </button>
              ))}
            </div>
          </div>
          <div className="chart-box">
            <Line
              options={chartOptions}
              data={{
                labels,
                datasets: [
                  {
                    label: 'Заполненность, %',
                    data: points.map((p) => p.fill),
                    borderColor: '#16a34a',
                    backgroundColor: 'rgba(22,163,74,0.15)',
                    fill: true,
                    tension: 0.25,
                    pointRadius,
                  },
                ],
              }}
            />
          </div>
          <div className="chart-box" style={{ height: 160, marginTop: 10 }}>
            <Line
              options={{
                ...chartOptions,
                scales: {
                  ...chartOptions.scales,
                  y: { position: 'left', title: { display: true, text: 'dBm' } },
                },
              }}
              data={{
                labels,
                datasets: [
                  {
                    label: 'Уровень Wi-Fi, dBm',
                    data: points.map((p) => p.rssi),
                    borderColor: '#0ea5e9',
                    tension: 0.25,
                    pointRadius,
                  },
                ],
              }}
            />
          </div>
        </div>
      </div>

      <SettingsCard
        device={device}
        canEdit={user?.role !== 'driver'}
        center={publicConfig?.map_center}
        onSaved={(updated) => {
          setDevice(updated)
          toast('Настройки сохранены и отправлены устройству')
          refreshAll().catch(() => {})
        }}
        onUnclaimed={() => {
          toast('Устройство отвязано')
          navigate('/')
        }}
      />

      <div className="card">
        <h2>События</h2>
        {events.length === 0 && <p className="muted small">Событий пока нет</p>}
        {events.map((event) => (
          <div key={event.id} className="event-row">
            <span className="event-icon">{EVENT_ICONS[event.type] || 'ℹ️'}</span>
            <div>
              <div>{event.message}</div>
              <div className="small muted">
                {formatDateTime(event.created_at)}
                {event.acked_at ? ` · принято ${event.acked_by_name || ''}` : ''}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Row({ label, children }) {
  return (
    <tr>
      <td className="muted" style={{ width: '55%' }}>
        {label}
      </td>
      <td>{children}</td>
    </tr>
  )
}

function SettingsCard({ device, center, canEdit, onSaved, onUnclaimed }) {
  const [form, setForm] = useState(() => ({
    name: device.name || '',
    address: device.address || '',
    volume_l: device.volume_l || '',
    empty_cm: device.empty_mm ? Math.round(device.empty_mm / 10) : '',
    full_cm: device.full_mm ? Math.round(device.full_mm / 10) : '',
    full_pct: device.config.full_pct,
    delta_pct: device.config.delta_pct,
    interval_s: device.config.interval_s,
    heartbeat_s: device.config.heartbeat_s,
    full_interval_s: device.config.full_interval_s,
    night_interval_s: device.config.night_interval_s,
    night_start: device.config.night_start,
    night_end: device.config.night_end,
  }))
  const [position, setPosition] = useState(
    device.lat !== null && device.lat !== undefined ? [device.lat, device.lon] : null,
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const change = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  const save = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const body = {
        name: form.name,
        address: form.address,
        volume_l: form.volume_l ? Number(form.volume_l) : null,
        empty_mm: form.empty_cm ? Math.round(Number(form.empty_cm) * 10) : null,
        full_mm: form.full_cm ? Math.round(Number(form.full_cm) * 10) : null,
        full_pct: Number(form.full_pct),
        delta_pct: Number(form.delta_pct),
        interval_s: Number(form.interval_s),
        heartbeat_s: Number(form.heartbeat_s),
        full_interval_s: Number(form.full_interval_s),
        night_interval_s: Number(form.night_interval_s),
        night_start: Number(form.night_start),
        night_end: Number(form.night_end),
      }
      if (position) {
        body.lat = position[0]
        body.lon = position[1]
      }
      const updated = await api(`/devices/${device.id}`, { method: 'PATCH', body })
      onSaved(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const unclaim = async () => {
    if (!window.confirm('Отвязать устройство? Историю это не удалит.')) return
    await api(`/devices/${device.id}/claim`, { method: 'DELETE' })
    onUnclaimed()
  }

  return (
    <form className="card" onSubmit={save}>
      <h2>Настройки</h2>
      <div className="grid cols-2">
        <div>
          <label className="field">
            <span>Название</span>
            <input value={form.name} onChange={change('name')} disabled={!canEdit} />
          </label>
          <label className="field">
            <span>Адрес</span>
            <input value={form.address} onChange={change('address')} disabled={!canEdit} />
          </label>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Объём, л</span>
              <input type="number" value={form.volume_l} onChange={change('volume_l')} disabled={!canEdit} />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Глубина (0%), см</span>
              <input type="number" value={form.empty_cm} onChange={change('empty_cm')} disabled={!canEdit} />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Порог 100%, см</span>
              <input type="number" value={form.full_cm} onChange={change('full_cm')} disabled={!canEdit} />
            </label>
          </div>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Порог «заполнен», %</span>
              <input type="number" value={form.full_pct} onChange={change('full_pct')} disabled={!canEdit} />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Порог отправки, %</span>
              <input type="number" value={form.delta_pct} onChange={change('delta_pct')} disabled={!canEdit} />
            </label>
          </div>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Интервал, с</span>
              <input type="number" value={form.interval_s} onChange={change('interval_s')} disabled={!canEdit} />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Когда заполнен, с</span>
              <input
                type="number"
                value={form.full_interval_s}
                onChange={change('full_interval_s')}
                disabled={!canEdit}
              />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Heartbeat, с</span>
              <input
                type="number"
                value={form.heartbeat_s}
                onChange={change('heartbeat_s')}
                disabled={!canEdit}
              />
            </label>
          </div>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Ночью, с</span>
              <input
                type="number"
                value={form.night_interval_s}
                onChange={change('night_interval_s')}
                disabled={!canEdit}
              />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Ночь с, ч</span>
              <input type="number" value={form.night_start} onChange={change('night_start')} disabled={!canEdit} />
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>Ночь до, ч</span>
              <input type="number" value={form.night_end} onChange={change('night_end')} disabled={!canEdit} />
            </label>
          </div>
        </div>
        <div>
          <span className="small muted">Место установки</span>
          <MapPicker value={position} onChange={setPosition} center={center} height={260} />
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="primary" type="submit" disabled={busy || !canEdit}>
          {busy ? 'Сохраняю…' : 'Сохранить и отправить устройству'}
        </button>
        <div className="spacer" />
        {canEdit && (
          <button type="button" className="danger" onClick={unclaim}>
            Отвязать устройство
          </button>
        )}
      </div>
      <p className="small muted" style={{ marginTop: 6 }}>
        Настройки публикуются в MQTT как retained-сообщение: спящее устройство применит их при
        следующем пробуждении и подтвердит номером версии.
      </p>
    </form>
  )
}
