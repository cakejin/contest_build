import { fmtPctLabel } from '../lib/format'

export function PctBadge({ value }: { value: number }) {
  const label = fmtPctLabel(value)
  return value >= 0 ? (
    <span className="text-[#b23a2e] font-bold">+{label}</span>
  ) : (
    <span className="text-[#2e7a4f] font-bold">{label}</span>
  )
}
