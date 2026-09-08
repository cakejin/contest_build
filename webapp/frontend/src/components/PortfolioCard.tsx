import type { EsgRecommendation, PortfolioBatch } from '../types'
import { Card } from './Card'
import { KvRow } from './KvRow'
import { PctBadge } from './PctBadge'
import { Details } from './Details'
import { fmtWon, fmtIssuedAt } from '../lib/format'

const SEVERITY_SOURCE_LABEL: Record<string, string> = {
  historical_warning: '기상특보',
  disaster_msg: '재난문자',
}

const TIER_STYLE: Record<string, string> = {
  심각: 'bg-[#fdecea] text-[#8a1f12]',
  주의: 'bg-[#fff4d6] text-[#7a4b00]',
  강수미확인: 'bg-surface-alt text-muted',
}

// 특보·강수 기반 재심사 알림(2026-09-03, DEV_LOG (계속10)) — EAL 변화율(아래 표)과 완전히 독립된
// 채널. 지역 트리거(호우·태풍·홍수·폭풍해일 경보 이상, 또는 호우·홍수·태풍 긴급재난)가 켜지면
// 담보마다 최근접 관측소 일강수로 주의(≥110mm)/심각(≥180mm)을 매긴다.
// 2026-09-08 ② — 열린 부분: 한 문장 + 대표 사건. 담보별 목록·기준은 토글 안.
function SeverityAlertSection({ portfolioBatch }: { portfolioBatch: PortfolioBatch }) {
  const alerts = portfolioBatch.severity_alerts ?? []
  const summary = portfolioBatch.severity_summary
  const rep = alerts[0]
  if (!summary?.region_triggered) {
    return (
      <p className="text-[13.5px] leading-relaxed text-ink mt-0 mb-0">
        특보 지역 담보 <b>{portfolioBatch.matched_count}건</b>을 다시 계산했지만, 이번 조회 구간엔 호우·태풍·홍수·폭풍해일 경보 이상 특보가 없어 <b>재심사 알림은 없어요</b>.
        <span className="text-muted text-xs"> (폭염·강풍 등 다른 특보는 재심사 트리거로 쓰지 않아요.)</span>
      </p>
    )
  }
  return (
    <>
      <p className="text-[13.5px] leading-relaxed text-ink mt-0 mb-2">
        특보 지역 담보 <b>{summary.matched_count}건</b> 중 <b>{summary.alert_count}건</b>에 재심사 알림이 갔어요. 심각 {summary.warning_count} · 주의 {summary.advisory_count}
        {summary.rain_unknown_count > 0 ? ` · 강수미확인 ${summary.rain_unknown_count}` : ''}.
      </p>
      {rep && (
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className="inline-block bg-[#fdecea] text-[#8a1f12] rounded-full py-1 px-2.5 font-bold">{rep.severity_level}</span>
          <span className="text-ink">{rep.event_description.split('(')[0].trim()}</span>
          <span className="text-muted">
            {SEVERITY_SOURCE_LABEL[rep.severity_source] ?? rep.severity_source} · {fmtIssuedAt(rep.issued_at)}
          </span>
          <a href={rep.source_url} target="_blank" rel="noopener noreferrer" className="text-title font-semibold">
            출처
          </a>
        </div>
      )}
      <Details summary={`담보별 알림 ${alerts.length}건 · 알림 기준`}>
        <div className="text-[11.5px] text-muted mb-1.5">
          담보별 최근접 관측소 일강수 기준 주의 ≥{summary.threshold_advisory_mm}mm · 심각 ≥{summary.threshold_warning_mm}mm ({summary.threshold_basis})
          {summary.rain_status !== 'OK' ? ` · 강수 조회 상태: ${summary.rain_status}` : ''}
        </div>
        <div>
          {alerts.map((a) => (
            <span
              key={a.collateral_id}
              className={`inline-block rounded-full py-1 px-2.5 text-xs font-semibold mr-1 mt-1 ${TIER_STYLE[a.alert_tier] ?? TIER_STYLE['강수미확인']}`}
              title={a.rain_mm != null ? `${a.rain_station} ${a.rain_station_km}km · 일강수 ${a.rain_mm}mm` : '강수 관측 없음'}
            >
              {a.collateral_id} · {a.alert_tier}
              {a.rain_mm != null ? ` ${a.rain_mm}mm` : ''}
            </span>
          ))}
        </div>
      </Details>
    </>
  )
}

function EalChangeDetails({
  portfolioBatch,
  esgRecommendations,
  insuranceUnconfirmedCount,
}: {
  portfolioBatch: PortfolioBatch
  esgRecommendations: EsgRecommendation[]
  insuranceUnconfirmedCount?: number
}) {
  return (
    <Details summary={`EAL 재계산 변화 ${portfolioBatch.alerts.length}건 (스냅샷 대비 ≥20%) · 재계산 범위`}>
      <p className="text-[11.5px] text-muted mt-0 mb-2">
        특보 지역 담보 {portfolioBatch.matched_count}건(전체 {portfolioBatch.total_records}건 중)의 침수 판정·건축물대장·몬테카를로 EAL을 지금 시점 원자료로 다시 계산해
        포트폴리오 스냅샷과 비교했어요. 특보 자체는 이 숫자에 들어가지 않고, 물리 데이터가 바뀐 담보만 잡히는 채널이에요.
      </p>
      {portfolioBatch.alerts.length > 0 && !!insuranceUnconfirmedCount && <KvRow label="보험 커버리지 미확인" value={`${insuranceUnconfirmedCount}건`} />}
      {portfolioBatch.alerts.length === 0 ? (
        <div className="text-xs text-muted bg-surface-alt rounded-lg py-3 px-3.5">매칭된 담보 전부 스냅샷 대비 EAL 변화율이 임계치 미만이에요.</div>
      ) : (
        <table className="w-full border-collapse text-xs mt-1">
          <thead>
            <tr>
              <th className="text-left py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">담보ID</th>
              <th className="text-right py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">EAL(스냅샷)</th>
              <th className="text-right py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">EAL(재계산)</th>
              <th className="text-right py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">변화율</th>
              <th className="text-left py-2 px-1.5 border-b border-surface-alt text-muted bg-surface-alt">추천 액션</th>
            </tr>
          </thead>
          <tbody>
            {portfolioBatch.alerts.map((a) => {
              const rec = esgRecommendations?.find((r) => r.collateral_id === a.collateral_id)
              return (
                <tr key={a.collateral_id} className="even:bg-black/[0.014]">
                  <td className="py-2 px-1.5 border-b border-surface-alt font-semibold">{a.collateral_id}</td>
                  <td className="py-2 px-1.5 border-b border-surface-alt text-right tabular-nums">{fmtWon(a.EAL_before)}</td>
                  <td className="py-2 px-1.5 border-b border-surface-alt text-right tabular-nums">{fmtWon(a.EAL_after)}</td>
                  <td className="py-2 px-1.5 border-b border-surface-alt text-right">{typeof a.EAL_change_pct === 'number' ? <PctBadge value={a.EAL_change_pct} /> : a.EAL_change_pct}</td>
                  <td className="py-2 px-1.5 border-b border-surface-alt">
                    {rec?.actions.map((act, i) => (
                      <span key={i} className="inline-block bg-accent-soft text-title rounded-full py-1 px-2.5 text-xs font-semibold mr-1 mt-0.5">
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
    </Details>
  )
}

export function PortfolioCard({
  portfolioBatch,
  esgRecommendations,
  insuranceUnconfirmedCount,
  bare,
}: {
  portfolioBatch: PortfolioBatch | null
  esgRecommendations: EsgRecommendation[]
  insuranceUnconfirmedCount?: number
  bare?: boolean
}) {
  const body = !portfolioBatch ? (
    <p className="text-[13.5px] leading-relaxed text-ink mt-0 mb-0">
      특보 트리거가 없어 <b>포트폴리오 재계산을 생략</b>했어요.
      <span className="text-muted text-xs"> 특보가 없으면 배치를 돌리지 않는 것도 설계상 정상 동작이에요 — 전체 점검은 정기 배치의 몫이에요.</span>
    </p>
  ) : (
    <>
      <SeverityAlertSection portfolioBatch={portfolioBatch} />
      <EalChangeDetails portfolioBatch={portfolioBatch} esgRecommendations={esgRecommendations} insuranceUnconfirmedCount={insuranceUnconfirmedCount} />
    </>
  )
  return bare ? body : <Card icon="portfolio" title="포트폴리오 재심사 알림 · ESG 추천">{body}</Card>
}
