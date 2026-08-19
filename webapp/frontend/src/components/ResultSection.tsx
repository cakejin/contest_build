import type { AssessResult, SubmittedMeta } from '../types'
import { Card } from './Card'
import { FloodCard } from './FloodCard'
import { BuildingCard } from './BuildingCard'
import { EalChart } from './EalChart'
import { MemoCard } from './MemoCard'
import { AdvisoryCard } from './AdvisoryCard'
import { PortfolioCard } from './PortfolioCard'
import { KvRow } from './KvRow'
import { fmtWon } from '../lib/format'

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

export function ResultSection({
  result,
  loading,
  meta,
}: {
  result: AssessResult | null
  loading: boolean
  meta: SubmittedMeta | null
}) {
  if (loading) {
    return (
      <>
        <TargetBanner meta={meta} />
        <Card icon="result" title="결과">
          <p className="text-muted text-xs">진행 중이에요 — 왼쪽 진행상황 패널을 확인하세요.</p>
        </Card>
      </>
    )
  }

  if (!result) {
    return (
      <Card icon="result" title="결과">
        <p className="text-muted text-xs">
          왼쪽에서 주소를 입력하고 "평가 실행"을 누르면 실제 침수판정·건물취약도·예상손실액·심사메모가 여기 표시됩니다.
        </p>
      </Card>
    )
  }

  if (result.error) {
    return (
      <>
        <TargetBanner meta={meta} />
        <Card icon="result" title="결과">
          <div className="bg-[#fdecea] text-[#8a1f12] rounded-[10px] py-3.5 px-4 text-[13px]">{result.error}</div>
        </Card>
      </>
    )
  }

  return (
    <>
      <TargetBanner meta={meta} />
      <FloodCard data={result.flood} coverageLabel={result.coverage_label} />
      <BuildingCard data={result.building} />

      <Card icon="chart" title="예상 손실액(EAL) 분포">
        <KvRow label="평균 EAL" value={fmtWon(result.scenario.eal.EAL_mean)} />
        <KvRow label="p95 / p99" value={`${fmtWon(result.scenario.eal.EAL_p95)} / ${fmtWon(result.scenario.eal.EAL_p99)}`} />
        <EalChart bins={result.scenario.eal.distribution_histogram_bins} />
        <p className="text-muted text-xs">
          시드 {result.scenario.eal.seed}, {result.scenario.eal.n_iterations.toLocaleString()}회 몬테카를로 시뮬레이션
        </p>
      </Card>

      <MemoCard memo={result.memo} />
      <AdvisoryCard advisory={result.advisory} />
      <PortfolioCard
        portfolioBatch={result.portfolio_batch}
        esgRecommendations={result.esg_recommendations}
        insuranceUnconfirmedCount={result.insurance_unconfirmed_count}
      />

      <div className="mt-[22px] bg-warn-bg text-warn-ink rounded-xl py-3.5 px-4 text-xs shadow-card">{result.memo.disclosure}</div>
    </>
  )
}
