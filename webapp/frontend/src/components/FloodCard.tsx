import type { FloodData } from '../types'
import { Card } from './Card'
import { KvRow } from './KvRow'
import { tierBadgeBgClass } from '../lib/format'

export function FloodCard({ data, coverageLabel }: { data: FloodData; coverageLabel?: string }) {
  const flood = data.flood
  const tierLabel = coverageLabel || (flood.coverage === 'OUT_OF_SCOPE' ? '커버리지 밖' : flood.tier)

  return (
    <Card icon="flood" title="침수 위험 판정">
      <span
        className={`inline-block py-[5px] px-3 rounded-full text-[11.5px] font-bold tracking-[0.2px] text-white shadow-[0_3px_8px_-3px_rgba(0,0,0,0.3)] ${tierBadgeBgClass(flood.tier, flood.coverage)}`}
      >
        {tierLabel || '판정'}
      </span>
      <KvRow label="하천" value={flood.river_name || '—'} />
      <KvRow label="폴리곤까지 거리" value={`${flood.distance_to_polygon_m ?? '—'} m`} />
      <KvRow label="빈도" value={flood.freq_label || '—'} />
    </Card>
  )
}
