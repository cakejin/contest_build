import type { AssessResult, PartialResult, SubmittedMeta } from '../types'
import { Card } from './Card'
import { FloodCard } from './FloodCard'
import { BuildingCard } from './BuildingCard'
import { EalChart } from './EalChart'
import { MemoCard } from './MemoCard'
import { AdvisoryCard } from './AdvisoryCard'
import { PortfolioCard } from './PortfolioCard'
import { KvRow } from './KvRow'
import { fmtWon } from '../lib/format'
import type { IconKey } from './Icons'

// 결과 대시보드 상단에 "지금 이게 어떤 담보인지"를 항상 보여준다(사용자 피드백) —
// 여러 건을 잇달아 조회하다 보면 화면만 보고는 지금 뜬 게 어느 주소/담보ID 결과인지
// 헷갈릴 수 있어서다.
function TargetBanner({ meta }: { meta: SubmittedMeta | null }) {
  if (!meta) return null
  return (
    <div className="flex items-center justify-between gap-3 bg-surface-alt border border-border/50 rounded-card py-2.5 px-4 mb-4 text-[12.5px]">
      <span className="text-ink font-semibold truncate">
        {meta.collateralId && <span className="text-accent mr-1.5">{meta.collateralId}</span>}
        {meta.address}
      </span>
      <span className="text-muted flex-none">{meta.queryDate ? `조회일 ${meta.queryDate}` : '현재 시점'}</span>
    </div>
  )
}

// 2026-09-07(멘토 피드백 1) — 아직 도착하지 않은 단계의 자리표시자. 카드 모양·순서는
// 기존 디자인 그대로 두고, 내용만 "계산 중"으로 비워둔다(디자인 변경은 별도 논의 중 —
// 후보 캔버스 참조).
function PendingCard({ icon, title, text }: { icon: IconKey; title: string; text: string }) {
  return (
    <Card icon={icon} title={title}>
      <p className="text-muted text-xs flex items-center gap-2 m-0">
        <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot flex-none" />
        {text}
      </p>
    </Card>
  )
}

export function ResultSection({
  result,
  partial,
  loading,
  meta,
}: {
  result: AssessResult | null
  partial: PartialResult
  loading: boolean
  meta: SubmittedMeta | null
}) {
  const hasPartial = Object.keys(partial).length > 0

  if (!result && !loading && !hasPartial) {
    return (
      <Card icon="result" title="결과">
        <p className="text-muted text-xs">
          왼쪽에서 주소를 입력하고 "평가 실행"을 누르면 실제 침수판정·건물취약도·예상손실액·심사메모가 여기 표시됩니다.
        </p>
      </Card>
    )
  }

  if (result?.error) {
    return (
      <>
        <TargetBanner meta={meta} />
        <Card icon="result" title="결과">
          <div className="bg-[#fdecea] text-[#8a1f12] rounded-[10px] py-3.5 px-4 text-[13px]">{result.error}</div>
        </Card>
      </>
    )
  }

  // 최종 result가 오면 그쪽이 원천(값은 partial과 동일). 그 전엔 도착한 단계부터 그린다.
  const view: PartialResult = result ?? partial
  const advisory = view.advisory
  const triggered = advisory?.trigger_event === true
  const portfolioPending = loading && (advisory === undefined || (triggered && view.portfolio_batch === undefined))

  return (
    <>
      <TargetBanner meta={meta} />

      {view.flood ? (
        <FloodCard data={view.flood} coverageLabel={view.coverage_label ?? undefined} />
      ) : (
        <PendingCard icon="flood" title="침수 위험 판정" text="홍수위험지도를 조회하고 있어요" />
      )}

      {view.building ? (
        <BuildingCard data={view.building} />
      ) : (
        <PendingCard icon="building" title="건물취약도" text="건축물대장을 조회하고 있어요" />
      )}

      {view.scenario ? (
        <Card icon="chart" title="예상 손실액(EAL) 분포">
          <KvRow label="평균 EAL" value={fmtWon(view.scenario.eal.EAL_mean)} />
          <KvRow label="p95 / p99" value={`${fmtWon(view.scenario.eal.EAL_p95)} / ${fmtWon(view.scenario.eal.EAL_p99)}`} />
          <EalChart bins={view.scenario.eal.distribution_histogram_bins} />
          <p className="text-muted text-xs">
            시드 {view.scenario.eal.seed}, {view.scenario.eal.n_iterations.toLocaleString()}회 몬테카를로 시뮬레이션
          </p>
        </Card>
      ) : (
        <PendingCard icon="chart" title="예상 손실액(EAL) 분포" text="몬테카를로 시뮬레이션을 돌리고 있어요" />
      )}

      {view.memo ? (
        <MemoCard memo={view.memo} />
      ) : (
        <PendingCard icon="memo" title="근거 인용 심사메모" text="근거를 인용한 심사메모를 작성하고 있어요 (LLM 호출)" />
      )}

      {advisory ? (
        <AdvisoryCard advisory={advisory} />
      ) : (
        <PendingCard icon="bell" title="기상특보 이력" text="기상특보 이력을 조회하고 있어요" />
      )}

      {portfolioPending ? (
        <PendingCard
          icon="portfolio"
          title="포트폴리오 재심사 알림 · ESG 추천"
          text={advisory === undefined ? '특보 조회 결과를 기다리는 중이에요' : '발효된 특보에 따라 포트폴리오를 재계산하고 있어요'}
        />
      ) : (
        <PortfolioCard
          portfolioBatch={view.portfolio_batch ?? null}
          esgRecommendations={view.esg_recommendations ?? []}
          insuranceUnconfirmedCount={view.insurance_unconfirmed_count}
        />
      )}

      {view.memo && (
        <div className="mt-[22px] bg-warn-bg text-warn-ink rounded-xl py-3.5 px-4 text-xs shadow-card">{view.memo.disclosure}</div>
      )}
    </>
  )
}
