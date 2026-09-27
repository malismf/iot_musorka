// Общие функции отображения: цвета, подписи, даты.

export const COLORS = {
  ok: '#16a34a',
  warn: '#eab308',
  full: '#ef4444',
  offline: '#94a3b8',
  unknown: '#38bdf8',
}

export function fillColor(device) {
  if (!device) return COLORS.offline
  if (!device.online) return COLORS.offline
  if (device.fill === null || device.fill === undefined) return COLORS.unknown
  if (device.fill >= (device.full_pct ?? 80)) return COLORS.full
  if (device.fill >= 50) return COLORS.warn
  return COLORS.ok
}

export function fillLabel(device) {
  if (!device) return '—'
  if (device.fill === null || device.fill === undefined) return '—'
  return `${device.fill}%`
}

export function statusLabel(device) {
  if (device.status !== 'active') return 'не привязано'
  if (!device.online) return 'нет связи'
  if (!device.calibrated) return 'нужна калибровка'
  return 'на связи'
}

export function timeAgo(value) {
  if (!value) return 'никогда'
  const date = new Date(value)
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'только что'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} мин назад`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} ч назад`
  return `${Math.floor(seconds / 86400)} дн назад`
}

export function formatDateTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export const EVENT_TITLES = {
  full: 'Контейнер заполнен',
  full_urgent: 'Срочно вывезти',
  collected: 'Контейнер вывезен',
  offline: 'Нет связи',
  online: 'Снова в сети',
  sensor_error: 'Сбой датчика',
  calibrated: 'Калибровка',
  claimed: 'Устройство привязано',
  unclaimed: 'Устройство отвязано',
  hello: 'Устройство включено',
}

export const EVENT_ICONS = {
  full: '🟠',
  full_urgent: '🔴',
  collected: '✅',
  offline: '📡',
  online: '📶',
  sensor_error: '🛠',
  calibrated: '📏',
  claimed: '🔗',
  unclaimed: '🔓',
  hello: '👋',
}
