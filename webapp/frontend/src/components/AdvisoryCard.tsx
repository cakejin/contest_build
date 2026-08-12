import type { AdvisoryData } from '../types'
import { Card } from './Card'

export function AdvisoryCard({ advisory }: { advisory: AdvisoryData }) {
  return (
    <Card icon="bell" title="기상특보 이력">
      {advisory.active_warnings.length === 0 ? (
        <p className="text-muted text-xs">이 지역·시점엔 발효 중인 특보가 없어요(status: {advisory.status}).</p>
      ) : (
        advisory.active_warnings.map((w, i) => (
          <div key={i} className="text-xs py-2 border-b border-surface-alt last:border-b-0">
            <strong>{w.type}</strong> · {w.issued_at} ·{' '}
            <a href={w.source_url} target="_blank" rel="noopener noreferrer" className="text-title font-semibold">
              출처
            </a>
          </div>
        ))
      )}
    </Card>
  )
}
