import { fillColor, fillLabel } from '../lib/format'

export default function FillBar({ device, showLabel = true }) {
  const value = device?.fill ?? 0
  return (
    <div className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
      <div className="fill-bar" title={fillLabel(device)}>
        <span style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: fillColor(device) }} />
      </div>
      {showLabel && <span className="small" style={{ width: 42 }}>{fillLabel(device)}</span>}
    </div>
  )
}
