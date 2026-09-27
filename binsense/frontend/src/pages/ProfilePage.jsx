import { useState } from 'react'
import { roleLabel } from '../components/Layout'
import { api } from '../lib/api'
import { useApp } from '../lib/store'

export default function ProfilePage() {
  const { user, setUser, toast } = useApp()
  const [name, setName] = useState(user?.name || '')
  const [password, setPassword] = useState('')
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
    </div>
  )
}
