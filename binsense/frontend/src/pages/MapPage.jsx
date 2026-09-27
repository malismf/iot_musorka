import L from 'leaflet'
import { WifiOff } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import FillBar from '../components/FillBar'
import { fillColor, fillLabel, statusLabel, timeAgo } from '../lib/format'
import { useApp } from '../lib/store'
import { DEFAULT_MAP_CENTER, TILE_ATTRIBUTION, TILE_URL } from '../lib/tiles'

// Leaflet принимает разметку метки строкой, поэтому иконку рендерим в HTML
const OFFLINE_BADGE = `<div class="marker-badge">${renderToStaticMarkup(
  <WifiOff size={11} strokeWidth={2.5} />,
)}</div>`

function markerIcon(device) {
  const label = device.fill === null || device.fill === undefined ? '?' : `${device.fill}`
  return L.divIcon({
    className: '',
    html:
      `<div class="bin-marker" style="background:${fillColor(device)}">${label}</div>` +
      (device.online ? '' : OFFLINE_BADGE),
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    popupAnchor: [0, -18],
  })
}

function FitBounds({ devices, selected }) {
  const map = useMap()
  useEffect(() => {
    if (selected) {
      const device = devices.find((d) => d.id === selected)
      if (device?.lat) map.setView([device.lat, device.lon], Math.max(map.getZoom(), 16))
      return
    }
    const points = devices.filter((d) => d.lat && d.lon).map((d) => [d.lat, d.lon])
    if (points.length > 1) map.fitBounds(points, { padding: [40, 40] })
    else if (points.length === 1) map.setView(points[0], 15)
  }, [devices, selected, map])
  return null
}

export default function MapPage() {
  const { devices, publicConfig, stats } = useApp()
  const navigate = useNavigate()
  const [selected, setSelected] = useState(null)
  const [filter, setFilter] = useState('all')

  const center = publicConfig?.map_center || DEFAULT_MAP_CENTER
  const zoom = publicConfig?.map_zoom || 12

  const visible = useMemo(() => {
    const list = devices.filter((d) => d.lat !== null && d.lon !== null)
    if (filter === 'full') return list.filter((d) => d.fill >= (d.full_pct ?? 80))
    if (filter === 'problem')
      return list.filter((d) => !d.online || !d.calibrated)
    return list
  }, [devices, filter])

  const sorted = useMemo(
    () => [...visible].sort((a, b) => (b.fill ?? -1) - (a.fill ?? -1)),
    [visible],
  )

  return (
    <div className="map-wrap">
      <MapContainer center={center} zoom={zoom} style={{ flex: 1 }}>
        <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} />
        <FitBounds devices={visible} selected={selected} />
        {visible.map((device) => (
          <Marker key={device.id} position={[device.lat, device.lon]} icon={markerIcon(device)}>
            <Popup>
              <b>{device.name || device.id}</b>
              <br />
              {device.address}
              <div style={{ marginTop: 6 }}>
                Заполненность: <b>{fillLabel(device)}</b>
                <br />
                Данные: {timeAgo(device.last_seen)}
              </div>
              <button
                className="small"
                style={{ marginTop: 8 }}
                onClick={() => navigate(`/devices/${device.id}`)}
              >
                Открыть карточку
              </button>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      <aside className="map-side">
        {stats && (
          <div className="grid cols-3" style={{ marginBottom: 12, gap: 8 }}>
            <Stat value={stats.active} label="контейнеров" />
            <Stat value={stats.full} label="заполнено" color="var(--danger)" />
            <Stat value={stats.offline} label="нет связи" color="var(--muted)" />
          </div>
        )}
        <div className="tabs">
          <button className={filter === 'all' ? 'active small' : 'small'} onClick={() => setFilter('all')}>
            Все
          </button>
          <button className={filter === 'full' ? 'active small' : 'small'} onClick={() => setFilter('full')}>
            Заполненные
          </button>
          <button
            className={filter === 'problem' ? 'active small' : 'small'}
            onClick={() => setFilter('problem')}
          >
            Проблемные
          </button>
        </div>

        {sorted.length === 0 && (
          <p className="muted small">
            Нет контейнеров для показа. Добавьте устройство на вкладке «Добавить» или запустите
            эмулятор.
          </p>
        )}

        {sorted.map((device) => (
          <div
            key={device.id}
            className="device-mini"
            onClick={() => setSelected(device.id)}
            onDoubleClick={() => navigate(`/devices/${device.id}`)}
            title="Клик — показать на карте, двойной клик — открыть карточку"
          >
            <div>
              <div style={{ fontWeight: 600 }}>{device.name || device.id}</div>
              <div className="small muted">{device.address || statusLabel(device)}</div>
              <FillBar device={device} />
            </div>
          </div>
        ))}
      </aside>
    </div>
  )
}

function Stat({ value, label, color }) {
  return (
    <div className="stat">
      <span className="value" style={{ color }}>
        {value ?? '—'}
      </span>
      <span className="label">{label}</span>
    </div>
  )
}
