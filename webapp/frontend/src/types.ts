export interface RegionPreset {
  id: string
  label: string
  region_code: string
  mode: string
  timeline_path: string | null
  sample_address: string
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
