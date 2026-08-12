import type { BuildingData } from '../types'
import { Card } from './Card'
import { KvRow } from './KvRow'

export function BuildingCard({ data }: { data: BuildingData }) {
  const factors = data.contributing_factors || []

  return (
    <Card icon="building" title="건물취약도">
      <KvRow label="점수" value={`${data.vulnerability_score ?? '—'} / 100`} />
      <KvRow label="상태" value={data.status} />
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
