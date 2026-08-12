export function fmtWon(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return Math.round(n).toLocaleString('ko-KR') + '원'
}

export function fmtPctLabel(n: number): string {
  return (n * 100).toFixed(1) + '%'
}

const TIER_BADGE_BG: Record<string, string> = {
  내부: 'bg-tier-inner',
  근접: 'bg-tier-near',
  원거리: 'bg-tier-far',
}

export function tierBadgeBgClass(tier: string, coverage: string): string {
  if (coverage === 'OUT_OF_SCOPE') return 'bg-tier-oos'
  return TIER_BADGE_BG[tier] ?? 'bg-tier-oos'
}
