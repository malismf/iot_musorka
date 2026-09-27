import { useApp } from '../lib/store'

export default function Toasts() {
  const { toasts } = useApp()
  if (!toasts.length) return null
  return (
    <div className="toasts">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.severity}`}>
          {toast.text}
        </div>
      ))}
    </div>
  )
}
