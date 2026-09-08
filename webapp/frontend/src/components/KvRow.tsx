import type { ReactNode } from 'react'

export function KvRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-[13.5px] border-b border-surface-alt last:border-b-0">
      <span className="text-muted">{label}</span>
      <span className="font-bold">{value}</span>
    </div>
  )
}
