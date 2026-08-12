import type { ReactNode } from 'react'
import type { IconKey } from './Icons'
import { CardHead } from './Icons'

export function Card({ icon, title, children }: { icon: IconKey; title: string; children: ReactNode }) {
  return (
    <div className="bg-surface border border-border/50 rounded-card shadow-card py-[22px] px-6 mb-5">
      <CardHead icon={icon} title={title} />
      {children}
    </div>
  )
}
