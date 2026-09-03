import type { EsgRecommendation, PortfolioBatch } from '../types'
import { Card } from './Card'
import { KvRow } from './KvRow'
import { PctBadge } from './PctBadge'
import { fmtWon } from '../lib/format'

const SEVERITY_SOURCE_LABEL: Record<string, string> = {
  historical_warning: '기상특보',
  disaster_msg: '재난문자',
}

const TIER_STYLE: Record<string, string> = {
  심각: 'bg-[#fdecea] text-[#8a1f12]',
  주의: 'bg-[#fff4d6] text-[#7a4b00]',
  강수미확인: 'bg-surface-alt text-muted',
}

// 특보·강수 기반 재심사 알림(2026-09-03, DEV_LOG (계속10)) — EAL 변화율(아래 "건물 등록정보
// 변경 감지" 표)과 완전히 독립된 채널. 지역 트리거(호우·태풍·홍수·폭풍해일 경보 이상, 또는
// 호우·홍수·태풍 긴급재난)가 켜지면 담보마다 최근접 관측소 일강수로 주의(≥110mm)/심각(≥180mm)을
// 매긴다. 최종 알림 단위는 요약 1건이고 담보 목록은 심사역이 펼쳐 본다(알림 피로 방지).
function SeverityAlertSection({ portfolioBatch }: { portfolioBatch: PortfolioBatch }) {
  const alerts = portfolioBatch.severity_alerts ?? []
  const summary = portfolioBatch.severity_summary
  const rep = alerts[0]
  return (
    <div className="mt-4 pt-4 border-t border-surface-alt">
      <h3 className="text-[13px] font-bold text-ink mb-2">
        재심사 알림 <span className="text-muted font-normal">— 특보·강수 기반(EAL 변화와 무관)</span>
      </h3>
      {!summary?.region_triggered ? (
        <div className="text-xs text-muted bg-surface-alt rounded-lg py-3 px-3.5">
          이번 조회 구간에 호우·태풍·홍수·폭풍해일 경보 이상 특보나 호우·홍수·태풍 긴급재난 재난문자가 없어 재심사 알림이 없어요.
          (폭염·강풍 등 다른 특보는 재심사 트리거로 쓰지 않아요.)
        </div>
      ) : (
        <>
          <div className="text-sm font-bold text-ink mb-1">
            지역 매칭 {summary.matched_count}건 중 재심사 알림 {summary.alert_count}건
            <span className="text-xs font-normal text-muted ml-2">
              심각 {summary.warning_count} · 주의 {summary.advisory_count}
              {summary.rain_unknown_count > 0 ? ` · 강수미확인 ${summary.rain_unknown_count}` : ''}
            </span>
          </div>
          <div className="text-xs text-muted mb-2">
            담보별 최근접 관측소 일강수 기준 주의 ≥{summary.threshold_advisory_mm}mm · 심각 ≥{summary.threshold_warning_mm}mm ({summary.threshold_basis})
            {summary.rain_status !== 'OK' ? ` · 강수 조회 상태: ${summary.rain_status}` : ''}
          </div>
          {rep && (
            <>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="inline-block bg-[#fdecea] text-[#8a1f12] rounded-full py-1 px-2.5 text-xs font-bold">
                  {rep.severity_level}
                </span>
                <span className="text-xs text-muted">
                  {SEVERITY_SOURCE_LABEL[rep.severity_source] ?? rep.severity_source} · {rep.issued_at}
                </span>
              </div>
              <p className="text-xs text-ink mb-2">{rep.event_description}</p>
              <a href={rep.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-title font-semibold">
                출처 확인
              </a>
            </>
          )}
          {alerts.length > 0 && (
            <details className="mt-2">
              <summary className="text-xs text-muted cursor-pointer">담보별 목록 펼치기 ({alerts.length}건)</summary>
              <div className="mt-1">
                {alerts.map((a) => (
                  <span
                    key={a.collateral_id}
                    className={`inline-block rounded-full py-1 px-2.5 text-xs font-semibold mr-1 mt-1 ${TIER_STYLE[a.alert_tier] ?? TIER_STYLE['강수미확인']}`}
                    title={a.rain_mm != null ? `${a.rain_station} ${a.rain_station_km}km · 일강수 ${a.rain_mm}mm` : '강수 관측 없음'}
                  >
                    {a.collateral_id} · {a.alert_tier}{a.rain_mm != null ? ` ${a.rain_mm}mm` : ''}
                  </span>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </div>
  )
}

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
          <h3 className="text-[13px] font-bold text-ink mt-3 mb-1">
            건물 등록정보 변경 감지 <span className="text-muted font-normal">— EAL 재계산 변화율 {'≥'}20%</span>
          </h3>
          {portfolioBatch.alerts.length === 0 ? (
            <div className="text-xs text-muted bg-surface-alt rounded-lg py-3 px-3.5">
              매칭된 담보 {portfolioBatch.matched_count}건 전부 건축물대장 기준 EAL 변화율이 임계치 미만이에요 — 이 표는 특보와 무관하게
              건물 등록정보가 바뀐 담보만 잡아내는 채널이라, 재해 심각도는 위의 재심사 알림에서 확인해 주세요.
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
          <SeverityAlertSection portfolioBatch={portfolioBatch} />
        </>
      )}
    </Card>
  )
}
