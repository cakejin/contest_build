import type { ReactNode } from 'react'
import type { IconKey } from './Icons'
import { CardHead } from './Icons'

/* 2026-09-09 — 보고서형 미니멀: 테두리·그림자 없는 흰 시트. 여백으로만 구획한다. */
export function Card({ icon, title, children }: { icon: IconKey; title: string; children: ReactNode }) {
  return (
    <div className="bg-surface rounded-card py-7 px-8 mb-6">
      <CardHead icon={icon} title={title} />
      {children}
    </div>
  )
}
