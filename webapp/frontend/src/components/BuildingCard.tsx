import type { BuildingData } from '../types'
import { Card } from './Card'
import { KvRow } from './KvRow'

const TIER_LABEL: Record<string, string> = { HIGH: '고위험', MEDIUM: '중위험', LOW: '저위험' }
const TIER_CLASS: Record<string, string> = {
  HIGH: 'bg-[#fdecea] text-[#8a1f12]',
  MEDIUM: 'bg-[#fff4e0] text-[#8a5a12]',
  LOW: 'bg-[#e6f6f2] text-[#0f6b57]',
}

export function BuildingCard({ data }: { data: BuildingData }) {
  const factors = data.contributing_factors || []
  const floorExposure = data.floor_exposure

  return (
    <Card icon="building" title="건물취약도">
      <KvRow label="점수" value={`${data.vulnerability_score ?? '—'} / 100`} />
      <KvRow label="상태" value={data.status} />
      {floorExposure && (
        <div className="mt-3 rounded-[10px] bg-surface-alt py-3 px-3.5">
          <div className="flex justify-between items-center text-[13px]">
            <span className="text-muted">층별 리스크(HANDOVER §⑧)</span>
            {floorExposure.floor_risk_tier ? (
              <span
                className={`text-xs font-bold py-1 px-2.5 rounded-full ${TIER_CLASS[floorExposure.floor_risk_tier]}`}
              >
                {TIER_LABEL[floorExposure.floor_risk_tier]}
              </span>
            ) : (
              <span className="text-xs font-semibold text-muted">미판정</span>
            )}
          </div>
          <p className="text-muted text-xs mt-1.5">
            {floorExposure.fallback_to_building_score
              ? `${floorExposure.reason} — 건물 전체 점수로 대체`
              : floorExposure.basis}
          </p>
          {floorExposure.exposure_ratio !== null && (
            <p className="text-muted text-xs mt-1">
              층 바닥 높이 {floorExposure.floor_elevation_m}m · 침수심 상한 {floorExposure.depth_upper_m}m ·
              노출비율 {(floorExposure.exposure_ratio * 100).toFixed(0)}%
            </p>
          )}
        </div>
      )}
      {factors.length > 0 && (
        <table className="w-full border-collapse text-xs mt-3 rounded-[10px] overflow-hidden">
          <thead>
            <tr>
              <th className="text-left py-2 px-2 border-b border-surface-alt text-muted font-semibold bg-surface-alt">항목</th>
              <th className="text-left py-2 px-2 border-b border-surface-alt text-muted font-semibold bg-surface-alt">원값</th>
              <th className="text-left py-2 px-2 border-b border-surface-alt text-muted font-semibold bg-surface-alt">정규화점수</th>
              <th className="text-left py-2 px-2 border-b border-surface-alt text-muted font-semibold bg-surface-alt">가중치</th>
            </tr>
          </thead>
          <tbody>
            {factors.map((f, i) => (
              <tr key={i} className={i % 2 === 1 ? 'bg-black/[0.014]' : ''}>
                <td className="py-2 px-2 border-b border-surface-alt">{f.name}</td>
                <td className="py-2 px-2 border-b border-surface-alt">{f.raw_value}</td>
                <td className="py-2 px-2 border-b border-surface-alt">{f.normalized_score}</td>
                <td className="py-2 px-2 border-b border-surface-alt">{(f.weight_used * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}
