import type { PartialResult, SubmittedMeta } from '../types'
import { Section, Lozenge } from './Section'
import { fmtWon, fmtIssuedAt } from '../lib/format'

/* 2026-09-08 — 확정안 11p "1 결론": 재심사 알림 배너 + 한 줄 판정 + 행동 버튼.
   전부 응답에 이미 있는 값으로만 만든다(새 계산 없음). ③에서 침수심 등급·특보→알림 소요·실사건을 문장에 더함.
   심사역 확인 버튼은 ④단계에서 감사로그 API에 연결하기 전까지 비활성. */

function tierWord(tier: string | null | undefined, coverageLabel: string | null | undefined): string {
  if (coverageLabel) return coverageLabel.split('(')[0]
  if (tier === '내부') return '범람구역 내부'
  if (tier === '근접') return '범람구역 근접'
  if (tier === '원거리') return '범람구역 원거리'
  return '판정 없음'
}

function buildingWord(score: number | null | undefined): string {
  if (score == null) return '건물 정보 미확인'
  const level = score >= 70 ? '높음' : score >= 40 ? '중간' : '낮음'
  return `취약도 ${score}점(${level})`
}

export function ConclusionSection({ data, meta, loading }: { data: PartialResult; meta: SubmittedMeta | null; loading: boolean }) {
  const flood = data.flood?.flood
  const depth = data.flood_depth_class
  const marks = data.flood_marks
  const building = data.building
  const eal = data.scenario?.eal
  const advisory = data.advisory
  const batch = data.portfolio_batch
  const sev = batch?.severity_summary
  const triggered = advisory?.trigger_event === true
  const batchPending = loading && triggered && batch === undefined
  const alertPending = loading && (advisory === undefined || batchPending)
  const latency = data.timings?.alert_latency_seconds ?? null

  const ratio = eal?.EAL_mean != null && meta?.collateralValue ? (eal.EAL_mean / meta.collateralValue) * 100 : null
  const region = flood?.region_name ?? ''
  const nearestMark = marks?.nearest_m != null && marks.nearest_m <= 2000 ? marks : null

  return (
    <Section id="sec-conclusion" n={1} title="결론" note="먼저 볼 것" tone={sev?.region_triggered ? 'alert' : 'default'}>
      {alertPending ? (
        <div className="flex items-center gap-2 text-xs text-muted bg-surface-alt rounded-lg py-3 px-4">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot flex-none" />
          {advisory === undefined ? '특보를 조회하고 있어요' : '특보 지역 담보를 재계산하고 있어요'}
        </div>
      ) : sev?.region_triggered ? (
        <div className="flex items-center gap-3.5 bg-[#fdecea] rounded-lg py-3.5 px-4">
          <Lozenge tone="solid">재심사 알림 · {sev.warning_count > 0 ? '심각' : sev.advisory_count > 0 ? '주의' : '강수미확인'}</Lozenge>
          <div className="min-w-0">
            <div className="text-[15px] font-extrabold text-ink leading-snug">
              {(sev.representative_event ?? '수문 특보').split('(')[0].trim()}
              {sev.representative_issued_at ? ` (${fmtIssuedAt(sev.representative_issued_at)})` : ''} → {region || '특보 지역'} 담보 {sev.matched_count}건 중 {sev.alert_count}건 알림
              {latency != null ? `, 특보 조회 시작 ${latency.toFixed(0)}초 뒤` : ''}
            </div>
            <div className="text-[12px] text-[#6b2c24] mt-0.5">
              심각 {sev.warning_count} · 주의 {sev.advisory_count}
              {sev.rain_unknown_count > 0 ? ` · 강수미확인 ${sev.rain_unknown_count}` : ''} · 기준 주의 ≥{sev.threshold_advisory_mm}mm · 심각 ≥{sev.threshold_warning_mm}mm
              {data.insurance_unconfirmed_count ? ` · 보험 미확인 ${data.insurance_unconfirmed_count}건` : ''}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3 bg-surface-alt rounded-lg py-3 px-4">
          <Lozenge tone="green">재심사 알림 없음</Lozenge>
          <span className="text-[12.5px] text-ink">
            {advisory && advisory.active_warnings.length > 0
              ? `특보 ${advisory.active_warnings.length}건이 있으나 호우·태풍·홍수·폭풍해일 경보 이상은 아니에요`
              : '조회 시점에 이 지역 특보가 없어요'}
          </span>
        </div>
      )}

      {flood && building && eal ? (
        <p className="text-[14px] leading-relaxed text-ink mt-3 mb-0">
          이 담보는 <b>{flood.river_name ? `${flood.river_name} ` : ''}{tierWord(flood.tier, data.coverage_label)}</b>
          {flood.coverage === 'IN_SCOPE' && flood.distance_to_polygon_m != null ? `(폴리곤까지 ${flood.distance_to_polygon_m}m` : ''}
          {flood.coverage === 'IN_SCOPE' && depth?.reliable ? `, 예상 침수심 ${depth.label}` : ''}
          {flood.coverage === 'IN_SCOPE' && flood.distance_to_polygon_m != null ? ')' : ''}
          {nearestMark ? (
            <>
              이며 <b>{Math.round(nearestMark.nearest_m!)}m 지점에 {nearestMark.nearest_year}년 실측 침수흔적</b>이 있습니다.
            </>
          ) : (
            '입니다.'
          )}{' '}
          건물은 <b>{buildingWord(building.vulnerability_score)}</b>입니다.{' '}
          {eal.status === 'OK' && eal.EAL_mean != null ? (
            <>
              연평균 예상손실은 <b>{fmtWon(eal.EAL_mean)}</b>
              {ratio != null ? `(담보가액의 ${ratio.toFixed(2)}%)` : ''}입니다.
            </>
          ) : (
            <>예상손실은 <b>산출하지 않았습니다</b>({eal.reason ?? '입력 데이터 불충분'} — 데이터 없음은 위험 낮음이 아니에요).</>
          )}
        </p>
      ) : (
        <p className="text-muted text-xs mt-3 mb-0 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot flex-none" />
          침수 판정·건물·예상손실을 계산하고 있어요
        </p>
      )}

      <div className="flex items-center gap-2 mt-3.5 flex-wrap">
        <button
          type="button"
          disabled
          title="④단계에서 감사로그 API에 연결 예정"
          className="bg-title text-white rounded-lg py-2 px-3.5 text-[13px] font-bold border-0 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          심사역 확인
        </button>
        {sev?.region_triggered && (
          <a href="#sec-advisory" className="bg-surface text-ink border border-border rounded-lg py-2 px-3.5 text-[13px] font-bold no-underline">
            담보별 알림 {sev.alert_count}건
          </a>
        )}
        <span className="text-[11px] text-muted">확인 버튼만 감사로그에 기록돼요 · 나머지는 읽기 전용</span>
        <span className="text-[11px] text-muted ml-auto">AI 참고자료 · 여신 결정 아님</span>
      </div>
    </Section>
  )
}
