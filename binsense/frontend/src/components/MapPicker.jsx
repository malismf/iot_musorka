import L from 'leaflet'
import { useEffect, useState } from 'react'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { TILE_ATTRIBUTION, TILE_URL } from '../lib/tiles'

const pinIcon = L.divIcon({
  className: '',
  html: '<div class="bin-marker" style="background:#16a34a">📍</div>',
  iconSize: [38, 38],
  iconAnchor: [19, 19],
})

function ClickHandler({ onPick }) {
  useMapEvents({
    click(event) {
      onPick([event.latlng.lat, event.latlng.lng])
    },
  })
  return null
}

function Recenter({ position }) {
  const map = useMap()
  useEffect(() => {
    if (position) map.setView(position, Math.max(map.getZoom(), 16))
  }, [position, map])
  return null
}

/** Выбор места установки контейнера: клик по карте, перетаскивание метки или геолокация. */
export default function MapPicker({ value, onChange, center, zoom = 15, height = 280 }) {
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState('')
  const start = value || center || [55.7558, 37.6173]

  const locate = () => {
    if (!navigator.geolocation) {
      setError('Браузер не поддерживает геолокацию')
      return
    }
    setLocating(true)
    setError('')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        onChange([
          Number(position.coords.latitude.toFixed(6)),
          Number(position.coords.longitude.toFixed(6)),
        ])
        setLocating(false)
      },
      (err) => {
        setError(
          err.code === 1
            ? 'Доступ к геолокации запрещён (нужен https и разрешение в браузере)'
            : 'Не удалось определить координаты',
        )
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <button type="button" onClick={locate} disabled={locating}>
          {locating ? 'Определяю…' : '📍 Моё местоположение'}
        </button>
        <span className="small muted">
          {value ? `${value[0].toFixed(5)}, ${value[1].toFixed(5)}` : 'кликните по карте'}
        </span>
      </div>
      {error && <div className="error small">{error}</div>}
      <div style={{ height, borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border)' }}>
        <MapContainer center={start} zoom={zoom} style={{ height: '100%', width: '100%' }}>
          <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} />
          <ClickHandler onPick={onChange} />
          <Recenter position={value} />
          {value && (
            <Marker
              position={value}
              icon={pinIcon}
              draggable
              eventHandlers={{
                dragend: (event) => {
                  const { lat, lng } = event.target.getLatLng()
                  onChange([Number(lat.toFixed(6)), Number(lng.toFixed(6))])
                },
              }}
            />
          )}
        </MapContainer>
      </div>
    </div>
  )
}
