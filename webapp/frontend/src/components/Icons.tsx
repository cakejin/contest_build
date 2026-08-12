/* 카드 헤더용 라인 아이콘(24x24, currentColor) — 섹션 성격을 한눈에 구분하기 위한 시각 보조.
   판정·수치 자체에는 영향 없음(순수 장식). */
import type { ReactNode } from 'react'

export type IconKey = 'result' | 'flood' | 'building' | 'chart' | 'memo' | 'bell' | 'portfolio'

const ICON_PATHS: Record<IconKey, ReactNode> = {
  result: (
    <>
      <path d="M6 2h9l5 5v15H6z" />
      <path d="M14 2v6h6" />
    </>
  ),
  flood: (
    <>
      <path d="M2 8c1.5 1.5 3 1.5 4.5 0s3-1.5 4.5 0 3 1.5 4.5 0 3-1.5 4.5 0" />
      <path d="M2 14c1.5 1.5 3 1.5 4.5 0s3-1.5 4.5 0 3 1.5 4.5 0 3-1.5 4.5 0" />
      <path d="M2 20c1.5 1.5 3 1.5 4.5 0s3-1.5 4.5 0 3 1.5 4.5 0 3-1.5 4.5 0" />
    </>
  ),
  building: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="1.5" />
      <path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 16h1M14 16h1" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M2 20h20" />
    </>
  ),
  memo: (
    <>
      <path d="M6 2h9l5 5v15H6z" />
      <path d="M14 2v6h6" />
      <path d="M9 15l2 2 4-4" />
    </>
  ),
  bell: (
    <>
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </>
  ),
  portfolio: (
    <>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </>
  ),
}

export function LineIcon({ icon, className }: { icon: IconKey; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {ICON_PATHS[icon]}
    </svg>
  )
}

export function CardHead({ icon, title }: { icon: IconKey; title: string }) {
  return (
    <div className="flex items-center gap-2.5 pb-3 mb-4 border-b border-surface-alt">
      <span className="flex-none w-[38px] h-[38px] rounded-[11px] bg-gradient-to-br from-accent-soft to-white border border-accent/20 text-title flex items-center justify-center">
        <LineIcon icon={icon} className="w-5 h-5" />
      </span>
      <h2 className="text-[15.5px] font-bold m-0 text-ink tracking-tight">{title}</h2>
    </div>
  )
}
