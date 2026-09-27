// Общее состояние приложения: пользователь, устройства, события, WebSocket.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api, getToken, setToken, wsUrl } from './api'
import { DEFAULT_MAP_CENTER } from './tiles'

const AppContext = createContext(null)

export function useApp() {
  const value = useContext(AppContext)
  if (!value) throw new Error('useApp вне AppProvider')
  return value
}

export function AppProvider({ children }) {
  const [token, setTokenState] = useState(getToken())
  const [user, setUser] = useState(null)
  const [publicConfig, setPublicConfig] = useState(null)
  const [devices, setDevices] = useState([])
  const [events, setEvents] = useState([])
  const [stats, setStats] = useState(null)
  const [ready, setReady] = useState(false)
  const [toasts, setToasts] = useState([])
  const socketRef = useRef(null)

  const toast = useCallback((text, severity = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((list) => [...list, { id, text, severity }])
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 7000)
  }, [])

  const logout = useCallback(() => {
    setToken('')
    setTokenState('')
    setUser(null)
    setDevices([])
    setEvents([])
    setStats(null)
  }, [])

  const applyAuth = useCallback((data) => {
    setToken(data.access_token)
    setTokenState(data.access_token)
    setUser(data.user)
  }, [])

  const login = useCallback(
    async (email, password) => applyAuth(await api('/auth/login', { method: 'POST', body: { email, password } })),
    [applyAuth],
  )

  const register = useCallback(
    async (email, password, name) =>
      applyAuth(await api('/auth/register', { method: 'POST', body: { email, password, name } })),
    [applyAuth],
  )

  const refreshDevices = useCallback(async (options = {}) => {
    const list = await api('/devices', { params: options })
    setDevices(list)
    return list
  }, [])

  const refreshEvents = useCallback(async () => {
    const list = await api('/events', { params: { limit: 100 } })
    setEvents(list)
    return list
  }, [])

  const refreshStats = useCallback(async () => {
    const data = await api('/stats/overview')
    setStats(data)
    return data
  }, [])

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshDevices(), refreshEvents(), refreshStats()])
  }, [refreshDevices, refreshEvents, refreshStats])

  const deleteDevice = useCallback(
    async (deviceId) => {
      await api(`/admin/devices/${deviceId}`, { method: 'DELETE' })
      await refreshAll()
    },
    [refreshAll],
  )

  const clearEvents = useCallback(async () => {
    await api('/events', { method: 'DELETE' })
    setEvents([])
    refreshStats().catch(() => {})
  }, [refreshStats])

  const upsertDevice = useCallback((device) => {
    setDevices((list) => {
      const index = list.findIndex((d) => d.id === device.id)
      if (index === -1) return device.status === 'active' ? [...list, device] : list
      const copy = [...list]
      copy[index] = { ...copy[index], ...device }
      return copy
    })
  }, [])

  // публичные настройки (центр карты) — нужны и на экране входа
  useEffect(() => {
    api('/config/public', { token: '' })
      .then(setPublicConfig)
      .catch(() => setPublicConfig({ map_center: DEFAULT_MAP_CENTER, map_zoom: 12 }))
  }, [])

  // профиль по сохранённому токену
  useEffect(() => {
    let cancelled = false
    if (!token) {
      setUser(null)
      setReady(true)
      return () => {}
    }
    api('/me')
      .then((me) => !cancelled && setUser(me))
      .catch(() => !cancelled && logout())
      .finally(() => !cancelled && setReady(true))
    return () => {
      cancelled = true
    }
  }, [token, logout])

  // первичная загрузка данных
  useEffect(() => {
    if (!user) return
    refreshAll().catch(() => {})
  }, [user, refreshAll])

  // WebSocket: живые обновления карты и всплывающие уведомления
  useEffect(() => {
    if (!user || !token) return () => {}
    let closed = false
    let pingTimer = null
    let retryTimer = null

    const connect = () => {
      if (closed) return
      const socket = new WebSocket(wsUrl(token))
      socketRef.current = socket

      socket.onopen = () => {
        pingTimer = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send('ping')
        }, 30000)
      }

      socket.onmessage = (message) => {
        let payload
        try {
          payload = JSON.parse(message.data)
        } catch {
          return
        }
        if (payload.type === 'telemetry' && payload.device) {
          upsertDevice(payload.device)
        } else if (payload.type === 'event' && payload.event) {
          setEvents((list) => [payload.event, ...list].slice(0, 200))
          if (payload.event.severity !== 'info') {
            toast(payload.event.message, payload.event.severity)
          }
          refreshStats().catch(() => {})
        } else if (payload.type === 'events_cleared') {
          setEvents([])
        }
      }

      socket.onclose = () => {
        if (pingTimer) clearInterval(pingTimer)
        if (!closed) retryTimer = setTimeout(connect, 5000)
      }
      socket.onerror = () => socket.close()
    }

    connect()
    return () => {
      closed = true
      if (pingTimer) clearInterval(pingTimer)
      if (retryTimer) clearTimeout(retryTimer)
      if (socketRef.current) socketRef.current.close()
    }
  }, [user, token, upsertDevice, toast, refreshStats])

  const value = {
    token,
    user,
    setUser,
    publicConfig,
    devices,
    events,
    stats,
    ready,
    toasts,
    toast,
    login,
    register,
    logout,
    refreshAll,
    refreshDevices,
    refreshEvents,
    refreshStats,
    clearEvents,
    deleteDevice,
    upsertDevice,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
