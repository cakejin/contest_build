import type { PartialResult, SubmittedMeta } from '../types'
import { Lozenge } from './Section'
import { PanelSection, PendingPanelSection } from './Panel'
import { fmtWon } from '../lib/format'

/* 2026-09-08 — 확정안 11p "3 권고 조치": 정책 템플릿 4종(백엔드 policy/disclosures.py 상수를
   /api/assess 응답의 action_templates로 그대로 노출)을 번호 목록으로 보여준다. 읽기 전용 —
   체크박스 없음, 쓰기 동작은 1 결론의 심사역 확인 버튼 하나(UX 점검 2026-09-08).
   "왜" 줄은 응답에 있는 값으로만. ③에서 적응 설비 항목 아래에 차수판 전후 EAL(scenario.adaptation)을 붙임. */

const KEY_ORDER = ['INSURANCE_CHECK', 'SITE_INSPECTION', 'DISASTER_SUPPORT_REFERRAL', 'ADAPTATION_INCENTIVE']

export function ActionsSection({ data, meta, loading }: { data: PartialResult; meta: SubmittedMeta | null; loading: boolean }) {
  const templates = data.action_templates
  if (!templates) {
    return loading ? (
      <PendingPanelSection id="sec-actions" title="권고 조치" text="판정이 끝나면 정책 템플릿에 맞춰 정리해요" />
    ) : null
  }

  const flood = data.flood?.flood
  const depth = data.flood_depth_class
  const marks = data.flood_marks
  const sev = data.portfolio_batch?.severity_summary
  const adaptation = data.scenario?.adaptation ?? null
  const insuranceUnconfirmed = data.insurance_unconfirmed_count ?? 0
  const inside = flood?.tier === '내부'
  const triggered = sev?.region_triggered === true
  const myRec = meta?.collateralId ? data.esg_recommendations?.find((r) => r.collateral_id === meta.collateralId) : undefined
  const nearestMark = marks?.nearest_m != null && marks.nearest_m <= 2000 ? marks : null
  const mid = adaptation?.scenarios.find((s) => s.barrier_height_m === 0.5) ?? adaptation?.scenarios[Math.floor((adaptation.scenarios.length - 1) / 2)]

  const why: Record<string, string> = {
    INSURANCE_CHECK: [
      inside ? '범람구역 내부' : flood?.tier ? `범람구역 ${flood.tier}` : null,
      nearestMark ? `${nearestMark.nearest_year}년 실측 침수흔적 ${Math.round(nearestMark.nearest_m!)}m` : null,
      triggered ? `특보 지역 알림 ${sev!.alert_count}건` : null,
      insuranceUnconfirmed ? `보험 미확인 ${insuranceUnconfirmed}건` : null,
    ]
      .filter(Boolean)
      .join(' · ') || '담보 부보 상태 확인',
    SITE_INSPECTION: [
      depth?.reliable ? `예상 침수심 ${depth.label}` : flood?.coverage === 'IN_SCOPE' && flood.distance_to_polygon_m != null ? `폴리곤까지 ${flood.distance_to_polygon_m}m` : null,
      triggered && sev?.representative_event ? sev.representative_event.split('(')[0].trim() : null,
    ]
      .filter(Boolean)
      .join(' · ') || '침수 대비 상태 점검',
    DISASTER_SUPPORT_REFERRAL: '회수·조건 변경 트리거로 쓰지 않는 보호형 규율 · 피해 발생 시 지자체 지원 창구',
    ADAPTATION_INCENTIVE: mid
      ? `차수판 ${mid.barrier_height_m}m 설치 시 예상손실 ${(mid.change_pct * 100).toFixed(0)}% · 인하 방향만, 소급 불리 없음`
      : '적응 투자 완료 시 우대 조건 안내 · 인하 방향만, 소급 불리 없음',
  }
  const priority: Record<string, boolean> = {
    INSURANCE_CHECK: inside || triggered,
    SITE_INSPECTION: inside || triggered,
  }
  const ordered = [...templates].sort((a, b) => KEY_ORDER.indexOf(a.key) - KEY_ORDER.indexOf(b.key))

  return (
    <PanelSection id="sec-actions" title="권고 조치" note="정책 템플릿 4종 · 인하·지원 방향만 · 읽기 전용">
      {ordered.map((t, i) => (
        <div key={t.key} className="grid grid-cols-[22px_minmax(0,1fr)_auto] gap-3 items-start py-3 border-t border-surface-alt text-[13.5px]">
          <span className="w-[18px] h-[18px] rounded-full bg-accent-soft/70 text-title text-[11px] font-extrabold flex items-center justify-center flex-none mt-px">{i + 1}</span>
          <span>
            <b>{t.text}</b>
            <span className="text-[11px] text-muted"> — 왜: {why[t.key] ?? ''}</span>
            {t.key === 'ADAPTATION_INCENTIVE' && adaptation && (
              <div className="mt-2 flex items-center gap-3 flex-wrap text-[12px]">
                <span className="text-muted">설치 시 예상 EAL</span>
                <span className="font-extrabold tabular-nums">{fmtWon(adaptation.baseline_EAL_mean)}</span>
                <span className="text-muted">→</span>
                {adaptation.scenarios.map((s) => (
                  <span key={s.barrier_height_m} className={`tabular-nums ${s === mid ? 'font-extrabold text-[#0f6b57]' : 'text-muted'}`}>
                    {s.barrier_height_m}m {fmtWon(s.EAL_mean)} ({(s.change_pct * 100).toFixed(0)}%)
                  </span>
                ))}
                <a href="#sec-eal" className="text-[11px] text-title font-semibold ml-auto">
                  6 손실에서 가정 보기
                </a>
              </div>
            )}
          </span>
          <span>
            {priority[t.key] ? <Lozenge tone="amber">우선</Lozenge> : t.key === 'ADAPTATION_INCENTIVE' ? <Lozenge tone="green">인하</Lozenge> : null}
          </span>
        </div>
      ))}
      {myRec && (
        <p className="text-[11.5px] text-muted mt-2 mb-0">
          이 담보({meta?.collateralId})에 대한 배치 추천: {myRec.actions.join(' · ')}
        </p>
      )}
      <div className="flex items-center gap-2.5 pt-4 text-[11.5px] text-muted">
        <Lozenge tone="mint">원칙</Lozenge>리스크 식별의 목적은 배제가 아니라 보호와 적응 지원 — 기존 차주 소급 불리 적용 없음
      </div>
    </PanelSection>
  )
}
