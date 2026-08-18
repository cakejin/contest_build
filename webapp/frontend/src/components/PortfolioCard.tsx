import type { EsgRecommendation, PortfolioBatch } from '../types'
import { Card } from './Card'
import { KvRow } from './KvRow'
import { PctBadge } from './PctBadge'
import { fmtWon } from '../lib/format'

export function PortfolioCard({
  portfolioBatch,
  esgRecommendations,
  insuranceUnconfirmedCount,
}: {
  portfolioBatch: PortfolioBatch | null
  esgRecommendations: EsgRecommendation[]
  insuranceUnconfirmedCount?: number
}) {
  return (
    <Card icon="portfolio" title="포트폴리오 재심사 알림 · ESG 추천">
      {!portfolioBatch ? (
        <div className="text-xs text-muted bg-surface-alt rounded-lg py-3 px-3.5">
          특보 트리거가 없어 포트폴리오 재계산을 생략했어요(특보가 없으면 배치를 돌리지 않는 것도 설계상 정상 동작입니다).
        </div>
      ) : (
        <>
          <KvRow label="지역 매칭" value={`${portfolioBatch.matched_count}건 / 전체 ${portfolioBatch.total_records}건`} />
          {portfolioBatch.alerts.length > 0 && !!insuranceUnconfirmedCount && (
            <KvRow label="보험 커버리지 미확인" value={`${insuranceUnconfirmedCount}건`} />
          )}
          {portfolioBatch.alerts.length === 0 ? (
            <div className="text-xs text-muted bg-surface-alt rounded-lg py-3 px-3.5">
              매칭된 담보 {portfolioBatch.matched_count}건 전부 EAL 변화율이 재심사 임계치 미만이라 알림이 발생하지 않았어요 — 특보가
              있어도 실제 손실액 변화가 없으면 알림을 만들어내지 않는 것이 설계 의도입니다.
            </div>
          ) : (
            <table className="w-full border-collapse text-xs mt-2">
              <thead>
                <tr>
                  <th className="text-left py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">담보ID</th>
                  <th className="text-left py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">EAL(이전)</th>
                  <th className="text-left py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">EAL(재계산)</th>
                  <th className="text-left py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">변화율</th>
                  <th className="text-left py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">ESG 추천 액션</th>
                </tr>
              </thead>
              <tbody>
                {portfolioBatch.alerts.map((a) => {
                  const rec = esgRecommendations?.find((r) => r.collateral_id === a.collateral_id)
                  return (
                    <tr key={a.collateral_id} className="even:bg-black/[0.014]">
                      <td className="py-2 px-1.5 border-b border-surface-alt">{a.collateral_id}</td>
                      <td className="py-2 px-1.5 border-b border-surface-alt">{fmtWon(a.EAL_before)}</td>
                      <td className="py-2 px-1.5 border-b border-surface-alt">{fmtWon(a.EAL_after)}</td>
                      <td className="py-2 px-1.5 border-b border-surface-alt">
                        {typeof a.EAL_change_pct === 'number' ? <PctBadge value={a.EAL_change_pct} /> : a.EAL_change_pct}
                      </td>
                      <td className="py-2 px-1.5 border-b border-surface-alt">
                        {rec?.actions.map((act, i) => (
                          <span
                            key={i}
                            className="inline-block bg-accent-soft text-title rounded-full py-1 px-2.5 text-xs font-semibold mr-1 mt-0.5"
                          >
                            {act}
                          </span>
                        ))}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </>
      )}
    </Card>
  )
}
