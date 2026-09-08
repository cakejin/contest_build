import { useCallback, useEffect, useRef, useState } from 'react'
import type { AssessResult, PartialResult, SubmittedMeta } from '../types'
import { Card } from './Card'
import { Panel, PanelSection, PendingPanelSection } from './Panel'
import { ResultTopBar, SECTIONS } from './ResultTopBar'
import { ConclusionSection } from './ConclusionSection'
import { SummarySection } from './SummarySection'
import { ActionsSection } from './ActionsSection'
import { FloodCard } from './FloodCard'
import { BuildingCard } from './BuildingCard'
import { EalChart } from './EalChart'
import { MemoCard } from './MemoCard'
import { AdvisoryCard } from './AdvisoryCard'
import { PortfolioCard } from './PortfolioCard'
import { KvRow } from './KvRow'
import { fmtWon } from '../lib/format'
import { Details } from './Details'

const STAGE_LABEL: Record<string, string> = {
  advisory: '특보',
  geocode: '주소',
  flood: '지도',
  building: '건축물대장',
  scenario: 'EAL',
  portfolio: '포트폴리오 재계산',
  memo: '심사메모(LLM)',
}

/* 2026-09-08 — 결과 화면 ①단계: 순서·섹션 골격(확정안 11p). 결론 → 요약 → 권고 조치 → 침수 → 건물
   → 손실 → 특보·알림 → 근거 원문. 근거 섹션(4~8)은 기존 카드 컴포넌트를 껍데기 없이(bare) 그대로
   넣는다 — 토글·출처 이동은 ②, 새 값 추가는 ③, 심사역 확인 버튼 연결은 ④에서. 각 섹션은 SSE partial로
   그 단계 산출물이 도착하는 즉시 채워진다. */
export function ResultSection({
  result,
  partial,
  loading,
  meta,
  boxHeight,
}: {
  result: AssessResult | null
  partial: PartialResult
  loading: boolean
  meta: SubmittedMeta | null
  boxHeight?: number
}) {
  const hasPartial = Object.keys(partial).length > 0
  // 2026-09-08 — 토스형: 이 컴포넌트가 스크롤 상자를 소유한다. 상자 스크롤 위치로 현재 섹션을 계산해
  // 상단 탭에 밑줄을 옮기고, 탭 클릭은 상자 안 스크롤로 이동한다(페이지 스크롤은 건드리지 않음).
  const boxRef = useRef<HTMLDivElement | null>(null)
  const [active, setActive] = useState('sec-conclusion')
  const TOP_OFFSET = 96 // 고정 줄 높이(담보 한 줄 + 탭) 근사치 — 섹션의 scroll-margin과 맞춘다
  const updateActive = useCallback(() => {
    const box = boxRef.current
    if (!box) return
    const boxTop = box.getBoundingClientRect().top
    let current = SECTIONS[0].id
    for (const sct of SECTIONS) {
      const el = box.querySelector<HTMLElement>(`#${sct.id}`)
      if (!el) continue
      if (el.getBoundingClientRect().top - boxTop <= TOP_OFFSET + 8) current = sct.id
    }
    setActive(current)
  }, [])
  useEffect(() => {
    const box = boxRef.current
    if (!box) return
    box.addEventListener('scroll', updateActive, { passive: true })
    updateActive()
    return () => box.removeEventListener('scroll', updateActive)
  }, [updateActive, result, loading])
  const jump = (id: string) => {
    const box = boxRef.current
    const el = box?.querySelector<HTMLElement>(`#${id}`)
    if (!box || !el) return
    const top = el.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - TOP_OFFSET
    box.scrollTo({ top, behavior: 'smooth' })
  }

  if (!result && !loading && !hasPartial) {
    return (
      <div style={boxHeight ? { height: boxHeight } : undefined} className="[&>div]:h-full [&>div]:mb-0 [&>div]:box-border">
      <Card icon="result" title="결과">
        {/* 2026-09-08 — 첫 방문 빈 상태를 3단계 안내로(UX 점검: 빈 상태가 곧 안내). */}
        <p className="text-sm font-bold text-ink mt-0 mb-1">담보 주소 하나로 침수 위험·건물취약도·예상손실과 근거 인용 심사메모를 만듭니다</p>
        <p className="text-muted text-xs mt-0 mb-3.5">왼쪽 폼을 위에서부터 채우면 됩니다. 처음이면 "예시 주소 넣기"로 힌남노 사례를 바로 볼 수 있어요.</p>
        <div className="grid grid-cols-3 max-[600px]:grid-cols-1 gap-6 mt-6">
          {[
            ['1 주소 입력', '대구·포항·거제 도로명주소. 지역은 자동 감지'],
            ['2 조회 기준 선택', '지금 시점 특보, 또는 과거 사건 재현'],
            ['3 평가 실행', '10초 안에 판정, 약 1분 뒤 심사메모'],
          ].map(([t, d]) => (
            <div key={t} className="border-t border-surface-alt pt-3">
              <div className="text-[11.5px] font-bold text-title">{t}</div>
              <div className="text-[13px] text-ink mt-1">{d}</div>
            </div>
          ))}
        </div>
        <p className="text-[11.5px] text-muted/80 mt-6 mb-0">이 산출물은 AI 기반 참고자료이며 여신 결정이 아닙니다.</p>
      </Card>
      </div>
    )
  }

  if (result?.error) {
    return (
      <div style={boxHeight ? { height: boxHeight } : undefined} className="[&>div]:h-full [&>div]:mb-0 [&>div]:box-border">
      <Card icon="result" title="결과">
        <p className="text-[12.5px] text-muted mt-0">{meta?.address}</p>
        <div className="bg-[#fdecea] text-[#8a1f12] rounded-lg py-3.5 px-4 text-[13px]">{result.error}</div>
      </Card>
      </div>
    )
  }

  // 최종 result가 오면 그쪽이 원천(값은 partial과 동일). 그 전엔 도착한 단계부터 그린다.
  const view: PartialResult = result ?? partial
  const advisory = view.advisory
  const triggered = advisory?.trigger_event === true
  const portfolioPending = loading && (advisory === undefined || (triggered && view.portfolio_batch === undefined))

  return (
    <div
      ref={boxRef}
      style={boxHeight ? { height: boxHeight } : undefined}
      className={`bg-surface rounded-card ${boxHeight ? 'overflow-y-auto' : ''}`}
    >
      <ResultTopBar data={view} meta={meta} loading={loading} active={active} onJump={jump} />
      {/* 2026-09-09 — 보고서형 미니멀: 결과 시트 한 장. 안쪽 회색 바탕·카드 껍데기 없이 섹션이 여백으로 이어진다. */}
      <div className="pb-10">
      <ConclusionSection data={view} meta={meta} loading={loading} />

      <Panel>
      <ActionsSection data={view} meta={meta} loading={loading} />
      <SummarySection data={view} meta={meta} />

      {view.flood ? (
        <PanelSection id="sec-flood" title="침수 노출" note="환경부 홍수위험지도 · 행안부 침수흔적">
          <FloodCard data={view.flood} coverageLabel={view.coverage_label ?? undefined} depth={view.flood_depth_class} marks={view.flood_marks} meta={meta} exposure={view.building?.floor_exposure} bare />
        </PanelSection>
      ) : (
        <PendingPanelSection id="sec-flood" title="침수 노출" text="홍수위험지도를 조회하고 있어요" />
      )}

      {view.building ? (
        <PanelSection id="sec-building" title="건물취약도" note="국토교통부 건축HUB">
          <BuildingCard data={view.building} bare />
        </PanelSection>
      ) : (
        <PendingPanelSection id="sec-building" title="건물취약도" text="건축물대장을 조회하고 있어요" />
      )}

      {view.scenario ? (
        <PanelSection id="sec-eal" title="예상손실" note={`몬테카를로 ${view.scenario.eal.n_iterations.toLocaleString()}회 · 시드 고정`}>
          {view.scenario.eal.status === 'OK' && view.scenario.eal.EAL_mean != null ? (
            <p className="text-[14.5px] leading-[1.75] text-ink mt-0 mb-3">
              연평균 예상손실은 <b>{fmtWon(view.scenario.eal.EAL_mean)}</b>이에요
              {meta?.collateralValue ? `(담보가액의 ${((view.scenario.eal.EAL_mean / meta.collateralValue) * 100).toFixed(2)}%)` : ''}.
              {view.scenario.eal.EAL_p95 === 0 ? ' 대부분의 해에는 손실이 없고, 드문 침수 해의 큰 손실이 평균을 만들어요.' : ''}
            </p>
          ) : (
            <p className="text-[14.5px] leading-[1.75] text-ink mt-0 mb-3">
              예상손실을 <b>산출하지 않았어요</b>({view.scenario.eal.reason ?? '입력 데이터 불충분'}). 데이터 없음은 위험 낮음이 아니에요.
            </p>
          )}
          <KvRow label="평균 EAL" value={fmtWon(view.scenario.eal.EAL_mean)} />
          <KvRow label="p95 / p99" value={`${fmtWon(view.scenario.eal.EAL_p95)} / ${fmtWon(view.scenario.eal.EAL_p99)}`} />
          <EalChart bins={view.scenario.eal.distribution_histogram_bins} />
          {view.scenario.adaptation && (
            <div className="mt-6">
              <div className="text-[13px] font-bold text-ink mb-2">차수판 설치 시 예상손실 <span className="font-normal text-muted">— 같은 시드 재실행 · 참고치</span></div>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr>
                    <th className="text-left py-1.5 font-semibold text-muted border-b border-border/40">차수판 높이</th>
                    <th className="text-right py-1.5 font-semibold text-muted border-b border-border/40">설치 후 평균 EAL</th>
                    <th className="text-right py-1.5 font-semibold text-muted border-b border-border/40">변화</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="py-1.5">현재(설치 전)</td>
                    <td className="py-1.5 text-right tabular-nums font-bold">{fmtWon(view.scenario.adaptation.baseline_EAL_mean)}</td>
                    <td className="py-1.5 text-right text-muted">—</td>
                  </tr>
                  {view.scenario.adaptation.scenarios.map((sc) => (
                    <tr key={sc.barrier_height_m}>
                      <td className="py-1.5">{sc.barrier_height_m}m</td>
                      <td className="py-1.5 text-right tabular-nums">{fmtWon(sc.EAL_mean)}</td>
                      <td className="py-1.5 text-right tabular-nums text-[#0f6b57] font-semibold">{(sc.change_pct * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[11px] text-muted mt-2 mb-0">{view.scenario.adaptation.assumption_note}</p>
            </div>
          )}
          <Details summary="계산 방식 · 재현 정보">
            <p className="text-[11.5px] text-muted mt-0 mb-1">{view.scenario.eal.methodology_note}</p>
            <p className="text-[11.5px] text-muted m-0">
              시드 {view.scenario.eal.seed} · {view.scenario.eal.n_iterations.toLocaleString()}회 — 같은 시드로 재실행하면 같은 값이 나와요
              {view.scenario.source_id ? ` · ${view.scenario.source_id}` : ''}
            </p>
          </Details>
        </PanelSection>
      ) : (
        <PendingPanelSection id="sec-eal" title="예상손실" text="몬테카를로 시뮬레이션을 돌리고 있어요" />
      )}

      {advisory ? (
        <PanelSection id="sec-advisory" title="특보 · 재심사 알림" note="기상청 특보 · 재난문자 · 특보 지역 포트폴리오 재계산">
          <AdvisoryCard advisory={advisory} bare />
          <div className="mt-6">
            {portfolioPending ? (
              <p className="text-muted text-xs flex items-center gap-2 m-0">
                <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot flex-none" />
                발효된 특보에 따라 특보 지역 담보를 재계산하고 있어요
              </p>
            ) : (
              <PortfolioCard
                portfolioBatch={view.portfolio_batch ?? null}
                esgRecommendations={view.esg_recommendations ?? []}
                insuranceUnconfirmedCount={view.insurance_unconfirmed_count}
                bare
              />
            )}
          </div>
        </PanelSection>
      ) : (
        <PendingPanelSection id="sec-advisory" title="특보 · 재심사 알림" text="기상특보 이력을 조회하고 있어요" />
      )}

      {view.memo ? (
        <PanelSection id="sec-memo" title="근거 원문" note={`심사메모 ${view.memo.sections.length}문장 · 인용 검증 통과 ${view.memo.sections.length} · 반려 ${view.memo.rejected_sentences.length}`} lead="위 내용의 원문이에요. 문장마다 출처가 붙어 있고, 출처가 없는 문장은 자동으로 빠져요.">
          <MemoCard memo={view.memo} bare />
        </PanelSection>
      ) : (
        <PendingPanelSection id="sec-memo" title="근거 원문" text="근거를 인용한 심사메모를 작성하고 있어요 (LLM 호출)" />
      )}
      </Panel>

      {view.timings && (
        <div className="px-8 pt-4">
          <Details summary={`처리 소요 ${view.timings.total_seconds.toFixed(1)}초 · 단계별 실측 시간`}>
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              {view.timings.stages
                .filter((st) => st.stage !== 'done')
                .map((st) => (
                  <span key={st.stage} className={`rounded px-2 py-1 tabular-nums ${st.stage === 'portfolio' ? 'bg-accent-soft text-title font-bold' : 'bg-surface-alt text-muted'}`}>
                    {STAGE_LABEL[st.stage] ?? st.stage} {st.seconds.toFixed(1)}s
                  </span>
                ))}
            </div>
            <p className="text-[11px] text-muted mt-2 mb-0">
              각 단계가 실제로 시작된 시각의 차이예요(타이머 흉내 아님).
              {view.timings.alert_latency_seconds != null ? ` 특보 조회 시작부터 특보 지역 담보 재계산 완료까지 ${view.timings.alert_latency_seconds.toFixed(1)}초.` : ''}
            </p>
          </Details>
        </div>
      )}
      {view.memo && (
        <p className="mx-8 mt-8 mb-0 pt-5 border-t border-surface-alt text-[12px] leading-relaxed text-muted">{view.memo.disclosure}</p>
      )}
      </div>
    </div>
  )
}
