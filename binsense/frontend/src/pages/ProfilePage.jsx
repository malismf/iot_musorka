import { useState } from 'react'
import { roleLabel } from '../components/Layout'
import { api } from '../lib/api'
import { useApp } from '../lib/store'

export default function ProfilePage() {
  const { user, setUser, publicConfig, toast } = useApp()
  const [name, setName] = useState(user?.name || '')
  const [password, setPassword] = useState('')
  const [link, setLink] = useState(null)
  const [error, setError] = useState('')

  const save = async (event) => {
    event.preventDefault()
    setError('')
    try {
      const body = { name }
      if (password) body.password = password
      setUser(await api('/me', { method: 'PATCH', body }))
      setPassword('')
      toast('Профиль сохранён')
    } catch (err) {
      setError(err.message)
    }
  }

  const toggleNotify = async (field, value) => {
    setUser(await api('/me', { method: 'PATCH', body: { [field]: value } }))
  }

  const makeLink = async () => {
    setError('')
    try {
      const data = await api('/me/telegram-link', { method: 'POST' })
      setLink(data)
      if (data.url) window.open(data.url, '_blank', 'noopener')
    } catch (err) {
      setError(err.message)
    }
  }

  const unlink = async () => {
    await api('/me/telegram', { method: 'DELETE' })
    setUser({ ...user, telegram_linked: false })
    toast('Telegram отвязан')
  }

  return (
    <div className="grid cols-2">
      <form className="card" onSubmit={save}>
        <h1>Профиль</h1>
        <p className="muted small">
          {user?.email} · роль: {roleLabel(user?.role)}
        </p>
        <label className="field">
          <span>Имя</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Новый пароль (необязательно)</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            autoComplete="new-password"
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="primary" type="submit">
          Сохранить
        </button>
      </form>

      <div className="card">
        <h2>Уведомления</h2>
        <label className="check">
          <input
            type="checkbox"
            checked={user?.notify_enabled ?? true}
            onChange={(e) => toggleNotify('notify_enabled', e.target.checked)}
          />
          Присылать уведомления в Telegram
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={user?.notify_info ?? false}
            onChange={(e) => toggleNotify('notify_info', e.target.checked)}
          />
          В том числе информационные (вывоз, калибровка)
        </label>

        <h3 style={{ marginTop: 16 }}>Telegram</h3>
        {user?.telegram_linked ? (
          <div className="row">
            <span className="badge ok">привязан</span>
            <button className="small" onClick={unlink}>
              Отвязать
            </button>
          </div>
        ) : (
          <>
            <p className="small muted">
              Нажмите кнопку — откроется чат с ботом
              {publicConfig?.bot_username ? ` @${publicConfig.bot_username}` : ''}. Отправьте
              предложенную команду /start, и уведомления начнут приходить.
            </p>
            <button onClick={makeLink}>Привязать Telegram</button>
            {link && (
              <p className="small" style={{ marginTop: 8 }}>
                Если чат не открылся, перейдите по ссылке:{' '}
                <a href={link.url} target="_blank" rel="noreferrer">
                  {link.url || 'бот не настроен на сервере'}
                </a>
                <br />
                Токен действует 30 минут.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
