// Тонкая обёртка над fetch: токен, параметры запроса, понятные ошибки.

const TOKEN_KEY = 'binsense_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* приватный режим браузера — работаем без сохранения */
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function describe(detail) {
  if (!detail) return 'Ошибка запроса'
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => `${(item.loc || []).slice(1).join('.')}: ${item.msg}`)
      .join('; ')
  }
  return JSON.stringify(detail)
}

export async function api(path, { method = 'GET', body, params, token } = {}) {
  const url = new URL(`/api${path}`, window.location.origin)
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value)
    }
  })

  const headers = {}
  const auth = token !== undefined ? token : getToken()
  if (auth) headers.Authorization = `Bearer ${auth}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 204) return null
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) {
    throw new ApiError(describe(data && data.detail), response.status)
  }
  return data
}

export function wsUrl(token) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`
}
