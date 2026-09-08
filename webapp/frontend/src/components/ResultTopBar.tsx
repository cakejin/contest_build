import type { PartialResult, SubmittedMeta } from '../types'
import { Lozenge } from './Section'
import type { LozengeTone } from './Section'
import { fmtWon } from '../lib/format'
import { fmtSavedAt } from '../lib/session'

/* 2026-09-08 — 토스형 3단 레이아웃(12p 3안): 가운데 스크롤 상자 상단에 고정되는 두 줄.
   1줄: 담보 한 줄(주소·담보가액·조회일·처리 시간) + 결론 배지 4개(재심사 알림·침수·취약도·EAL).
   2줄: 밑줄형 목차 탭 — 클릭하면 상자 안에서 해당 섹션으로 스크롤, 현재 섹션에 밑줄.
   이 줄이 결론 한 줄 배너와 바깥 탭 칩의 역할을 대신한다. 값은 전부 응답에 있는 것. */

export const SECTIONS: { id: string; label: string }[] = [
  { id: 'sec-conclusion', label: '결론' },
  { id: 'sec-actions', label: '권고 조치' },
  { id: 'sec-summary', label: '요약' },
  { id: 'sec-flood', label: '침수' },
  { id: 'sec-building', label: '건물' },
  { id: 'sec-eal', label: '손실' },
  { id: 'sec-advisory', label: '특보·알림' },
  { id: 'sec-memo', label: '근거 원문' },
]

const TIER_TONE: Record<string, LozengeTone> = { 내부: 'solid', 근접: 'amber', 원거리: 'green' }

export function ResultTopBar({
  data,
  meta,
  loading,
  active,
  onJump,
  restoredAt = null,
}: {
  data: PartialResult
  meta: SubmittedMeta | null
  loading: boolean
  active: string
  onJump: (id: string) => void
  restoredAt?: string | null
}) {
  const flood = data.flood?.flood
  const building = data.building
  const eal = data.scenario?.eal
  const advisory = data.advisory
  const sev = data.portfolio_batch?.severity_summary
  const triggered = advisory?.trigger_event === true
  const alertPending = loading && (advisory === undefined || (triggered && data.portfolio_batch === undefined))
  const buildingLevel = building?.vulnerability_score == null ? null : building.vulnerability_score >= 70 ? '높음' : building.vulnerability_score >= 40 ? '중간' : '낮음'

  return (
    <div className="sticky top-0 z-10 bg-surface border-b border-surface-alt">
      <div className="flex items-center gap-2.5 flex-wrap px-8 pt-4 pb-2 text-[12px] text-muted">
        <span className="min-w-0 truncate">
          <b className="text-ink text-[13.5px]">
            {meta?.collateralId && <span className="text-accent mr-1.5">{meta.collateralId}</span>}
            {data.geocoded?.refined_text ?? meta?.address ?? ''}
          </b>
          {meta?.collateralValue ? ` · 담보가액 ${fmtWon(meta.collateralValue)}` : ''}
          {meta ? ` · ${meta.queryDate ? `조회일 ${meta.queryDate} (과거 특보)` : '현재 시점 특보'}` : ''}
          {data.timings ? ` · 처리 ${data.timings.total_seconds.toFixed(0)}초` : ''}
        </span>
        <span className="ml-auto flex items-center gap-1.5 flex-wrap">
          {restoredAt && (
            // 2026-09-09 — 지도 갔다 돌아와 복원된 결과임을 표시(새로 계산한 게 아님).
            <Lozenge tone="dash">이전 실행 결과 · {fmtSavedAt(restoredAt)} 계산</Lozenge>
          )}
          {alertPending ? (
            <Lozenge tone="grey">재심사 알림 계산 중</Lozenge>
          ) : sev?.region_triggered ? (
            <Lozenge tone="solid">재심사 알림 · {sev.warning_count > 0 ? '심각' : sev.advisory_count > 0 ? '주의' : '강수미확인'} {sev.alert_count}건</Lozenge>
          ) : advisory ? (
            <Lozenge tone="green">재심사 알림 없음</Lozenge>
          ) : null}
          {flood ? (
            data.coverage_label ? (
              <Lozenge tone="grey">{data.coverage_label.split('(')[0]}</Lozenge>
            ) : (
              <Lozenge tone={TIER_TONE[flood.tier ?? ''] ?? 'grey'}>범람구역 {flood.tier ?? '—'}</Lozenge>
            )
          ) : (
            <Lozenge tone="grey">침수 계산 중</Lozenge>
          )}
          {building ? (
            <Lozenge tone={buildingLevel === '높음' ? 'red' : buildingLevel === '중간' ? 'amber' : buildingLevel === '낮음' ? 'green' : 'grey'}>
              취약도 {building.vulnerability_score ?? '—'}
            </Lozenge>
          ) : (
            <Lozenge tone="grey">건물 계산 중</Lozenge>
          )}
          {eal ? (
            <Lozenge tone="grey">{eal.status === 'OK' && eal.EAL_mean != null ? `EAL ${fmtWon(eal.EAL_mean)}` : 'EAL 산출 불가'}</Lozenge>
          ) : (
            <Lozenge tone="grey">EAL 계산 중</Lozenge>
          )}
        </span>
      </div>
      <nav className="flex gap-1 px-6 overflow-x-auto" aria-label="결과 섹션">
        {SECTIONS.map((s) => {
          const on = s.id === active
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onJump(s.id)}
              className={`bg-transparent border-0 border-b-2 py-2 px-2.5 text-[13px] cursor-pointer whitespace-nowrap ${
                on ? 'border-title text-ink font-bold' : 'border-transparent text-muted font-medium hover:text-ink'
              }`}
            >
              {s.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}
