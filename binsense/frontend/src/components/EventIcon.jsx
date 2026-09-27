import { DEFAULT_EVENT_ICON, EVENT_ICONS } from '../lib/format'

export default function EventIcon({ type }) {
  const { icon: Icon, color } = EVENT_ICONS[type] || DEFAULT_EVENT_ICON
  return (
    <span className="event-icon" style={{ color }}>
      <Icon size={20} strokeWidth={2.2} aria-hidden="true" />
    </span>
  )
}
