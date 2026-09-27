import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import MapPicker from '../components/MapPicker'
import { api } from '../lib/api'
import { useApp } from '../lib/store'

export default function ClaimPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { publicConfig, toast, refreshAll } = useApp()
  const [deviceId, setDeviceId] = useState(params.get('id') || '')
  const [code, setCode] = useState((params.get('code') || '').toUpperCase())
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [volume, setVolume] = useState('1100')
  const [position, setPosition] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // ссылка привязки из provision.py заполняет id и код; координаты пробуем взять из браузера
  useEffect(() => {
    if (!navigator.geolocation || position) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setPosition([Number(pos.coords.latitude.toFixed(6)), Number(pos.coords.longitude.toFixed(6))]),
      () => {},
      { timeout: 8000 },
    )
  }, [position])

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const device = await api('/devices/claim', {
        method: 'POST',
        body: {
          device_id: deviceId.trim().toLowerCase(),
          claim_code: code.trim().toUpperCase(),
          name,
          address,
          lat: position ? position[0] : null,
          lon: position ? position[1] : null,
          volume_l: volume ? Number(volume) : null,
        },
      })
      toast('Устройство привязано')
      await refreshAll().catch(() => {})
      navigate(`/devices/${device.id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid cols-2">
      <form className="card" onSubmit={submit}>
        <h1>Добавить устройство</h1>
        <p className="muted small">
          Идентификатор и код привязки печатает <code>tools/provision.py</code> при подготовке
          устройства. Если открыть ссылку привязки из его вывода, поля заполнятся сами.
        </p>

        <label className="field">
          <span>Идентификатор устройства</span>
          <input
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            placeholder="bin-a1b2c3"
            required
          />
        </label>
        <label className="field">
          <span>Код привязки</span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="7F3K9Q2M"
            required
          />
        </label>
        <label className="field">
          <span>Название площадки</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Площадка №12"
            required
          />
        </label>
        <label className="field">
          <span>Адрес</span>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="ул. Ленина, 4"
          />
        </label>
        <label className="field">
          <span>Объём контейнера, л</span>
          <select value={volume} onChange={(e) => setVolume(e.target.value)}>
            <option value="120">120</option>
            <option value="240">240</option>
            <option value="660">660</option>
            <option value="770">770</option>
            <option value="1100">1100</option>
            <option value="8000">8000 (бункер)</option>
          </select>
        </label>

        {error && <div className="error">{error}</div>}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? 'Привязываю…' : 'Привязать'}
        </button>
      </form>

      <div className="card">
        <h2>Место установки</h2>
        <MapPicker
          value={position}
          onChange={setPosition}
          center={publicConfig?.map_center}
          height={340}
        />
        <p className="small muted" style={{ marginTop: 8 }}>
          После привязки устройство мигнёт зелёным три раза. Затем закрепите его на пустом
          контейнере, удерживайте кнопку 3 секунды и закройте крышку: через 5 секунд устройство
          измерит глубину контейнера.
        </p>
      </div>
    </div>
  )
}
