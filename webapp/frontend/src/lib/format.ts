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

/** ISO 시각(2022-09-06T00:00:00+09:00) → "2022-09-06 00:00". 날짜만 오면 그대로. (2026-09-08 ②) */
export function fmtIssuedAt(iso: string | null | undefined): string {
  if (!iso) return '—'
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})(?:T(\d{2}):(\d{2}))?/)
  if (!m) return iso
  return m[2] ? `${m[1]} ${m[2]}:${m[3]}` : m[1]
}
