export interface RegionPreset {
  id: string
  label: string
  // 2026-09-08 — "과거 사건 재현" 사건 칩용. sample_date가 없으면 칩으로 그리지 않는다.
  chip_label?: string | null
  region_code: string
  mode: string
  timeline_path: string | null
  sample_address: string
  sample_date?: string | null
}

// 2026-09-08 — 조회 기준 세그먼트. live면 query_date를 보내지 않고(지금 시점 특보),
// historical이면 날짜 필수. 백엔드 판단 방식(query_date 유무)은 그대로다.
export type QueryMode = "live" | "historical"

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
  status: string // "OK" | "PARTIAL" | "FAILED"
  contributing_factors: ContributingFactor[]
  missing_fields?: string[]
  note?: string | null
  floor_exposure?: FloorExposure | null
}

export interface EalBin {
  bin_start: number
  bin_end: number
  count: number
}

export interface EalStats {
  EAL_mean: number | null
  EAL_p50: number | null
  EAL_p95: number | null
  EAL_p99: number | null
  seed: number
  n_iterations: number
  distribution_histogram_bins: EalBin[] | null
  methodology_note: string
  status: string // "OK" | "INSUFFICIENT_INPUT"
  reason: string | null
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
  trigger_event: boolean
  mode: string
  status: string
}

export interface PortfolioAlert {
  collateral_id: string
  EAL_before: number | null
  EAL_after: number
  EAL_change_pct: number | string
  insurance_covered: boolean | null
}

// 2026-08-31 추가(DEV_LOG.md 참조) — EAL 변화율 알림(위 PortfolioAlert)과 완전히 독립된
// 채널. EAL 재계산 결과와 무관하게 특보/재난문자 자체의 심각도(경보 이상·긴급재난 이상)만
// 보고 뜬다 — 거제 2026-08 실호우처럼 EAL 채널이 조용해도(0% 변화) 여기는 뜰 수 있다.
export interface SeverityAlert {
  collateral_id: string
  region_code: string | null
  severity_level: string
  severity_source: 'historical_warning' | 'disaster_msg'
  event_description: string
  issued_at: string
  source_url: string
  alert_tier: '심각' | '주의' | '강수미확인' | string
  rain_mm: number | null
  rain_station: string | null
  rain_station_km: number | null
}

export interface SeverityAlertSummary {
  matched_count: number
  alert_count: number
  warning_count: number
  advisory_count: number
  rain_unknown_count: number
  region_triggered: boolean
  rain_status: string
  rain_note: string
  threshold_advisory_mm: number
  threshold_warning_mm: number
  threshold_basis: string
  representative_event: string | null
  representative_issued_at: string | null
}

export interface PortfolioBatch {
  matched_count: number
  total_records: number
  alerts: PortfolioAlert[]
  severity_alerts: SeverityAlert[]
  severity_summary?: SeverityAlertSummary
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

// 2026-09-07(멘토 피드백 1) — 단계별 부분 결과 SSE 이벤트. data는 stage에 따라 AssessResult의
// 해당 키 값과 완전히 같은 형태다(graph/week3_demo.py::OnPartial 참조).
export interface PartialEventPayload {
  stage: string
  data: unknown
}

export interface GeocodedData {
  lat: number
  lon: number
  refined_text: string
  input_address: string
}

// 도착한 단계만 채워지는 결과 — undefined는 "아직 안 옴", portfolio_batch의 null은 "트리거 없어 생략".
export type PartialResult = Partial<
  Pick<AssessResult, 'advisory' | 'flood' | 'building' | 'scenario' | 'memo' | 'portfolio_batch' | 'coverage_label' | 'esg_recommendations' | 'insurance_unconfirmed_count'>
> & { geocoded?: GeocodedData }

export interface ProgressItem {
  message: string
  status: 'active' | 'done'
}

export type EalChartMode = 'severity' | 'log' | 'linear'
