import type { ReactNode } from 'react'

export function KvRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between py-[7px] text-[13px] border-b border-surface-alt last:border-b-0">
      <span className="text-muted">{label}</span>
      <span className="font-bold">{value}</span>
    </div>
  )
}
