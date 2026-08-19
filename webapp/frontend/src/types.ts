export interface RegionPreset {
  id: string
  label: string
  region_code: string
  mode: string
  timeline_path: string | null
  sample_address: string
}

// HANDOVER 논의(DEV_LOG.md 2026-08-18) — 지역 프리셋이 아니라 실제 입력 주소를
// 지오코딩해 감지한 지역. 담보 평가와 포트폴리오 알림이 항상 같은 지역을 가리키게
// 하기 위해 이 값이 /api/assess로 보낼 region_code/mode/timeline_path의 유일한 출처다.
export interface CuratedReplay {
  mode: string
  timeline_path: string | null
  label: string
}

export interface ResolvedRegion {
  resolved: boolean
  reason?: string
  matched_address?: string
  lat?: number
  lon?: number
  coverage?: string
  region_code?: string | null
  region_name?: string | null
  live_supported?: boolean
  curated_replay?: CuratedReplay | null
}

export interface AddressSuggestion {
  road_address: string
  building_name: string | null
}

// 2026-08-19(계속, DEV_LOG.md 참조) — "기존 포트폴리오 조회" 탭용. ltv/balance는
// 노출하지 않는다(고를 때 참고용으로 불필요, HANDOVER §⑥ 블루라이닝 방지 설계 참조).
export interface PortfolioListItem {
  collateral_id: string
  address: string
  collateral_type: string
  region_code: string | null
  collateral_value: number
}

// "신규 담보 조회"(자유입력)와 "기존 포트폴리오 조회"(316건 중 선택)를 명확히 분리
// (사용자 피드백, DEV_LOG.md 2026-08-19 참조 — 이전엔 이 구분이 화면에 안 보였다).
export type InputMode = 'new' | 'portfolio'

// 결과 대시보드 상단에 "지금 보고 있는 게 어떤 담보인지" 명시하기 위한 스냅샷
// (사용자 피드백) — /api/assess 응답에 없는 값이라 제출 시점 폼 상태를 그대로 들고 있는다.
export interface SubmittedMeta {
  address: string
  collateralId: string | null
  queryDate: string
}

export interface FloodResult {
  coverage: string
  tier: string
  river_name: string | null
  distance_to_polygon_m: number | null
  freq_label: string | null
}

export interface FloodData {
  flood: FloodResult
}

export interface ContributingFactor {
  name: string
  raw_value: string | number
  normalized_score: number
  weight_used: number
}

// HANDOVER §⑧ 층별 리스크 차등화 — target_floor 미입력 시 null(건물 전체 스코어링 폴백).
export interface FloorExposure {
  floor_risk_tier: 'HIGH' | 'MEDIUM' | 'LOW' | null
  floor_unassessed: boolean
  fallback_to_building_score: boolean
  basis: string | null
  reason: string | null
  floor_elevation_m: number | null
  depth_upper_m: number | null
  exposure_ratio: number | null
}

export interface BuildingData {
  vulnerability_score: number | null
  status: string
  contributing_factors: ContributingFactor[]
  floor_exposure?: FloorExposure | null
}

export interface EalBin {
  bin_start: number
  bin_end: number
  count: number
}

export interface EalStats {
  EAL_mean: number
  EAL_p95: number
  EAL_p99: number
  seed: number
  n_iterations: number
  distribution_histogram_bins: EalBin[]
}

export interface ScenarioData {
  eal: EalStats
}

export interface MemoSection {
  text: string
  citations: string[]
}

export interface MemoData {
  sections: MemoSection[]
  rejected_sentences: unknown[]
  fallback_used: boolean
  disclosure: string
}

export interface AdvisoryWarning {
  type: string
  issued_at: string
  source_url: string
}

export interface AdvisoryData {
  active_warnings: AdvisoryWarning[]
  status: string
}

export interface PortfolioAlert {
  collateral_id: string
  EAL_before: number | null
  EAL_after: number
  EAL_change_pct: number | string
  insurance_covered: boolean | null
}

export interface PortfolioBatch {
  matched_count: number
  total_records: number
  alerts: PortfolioAlert[]
}

export interface EsgRecommendation {
  collateral_id: string
  actions: string[]
}

export interface AssessResult {
  error?: string
  flood: FloodData
  building: BuildingData
  scenario: ScenarioData
  memo: MemoData
  advisory: AdvisoryData
  portfolio_batch: PortfolioBatch | null
  esg_recommendations: EsgRecommendation[]
  insurance_unconfirmed_count?: number
  coverage_label?: string
}

export interface ProgressEventPayload {
  stage: string
  message: string
}

export interface ProgressItem {
  message: string
  status: 'active' | 'done'
}

export type EalChartMode = 'severity' | 'log' | 'linear'
