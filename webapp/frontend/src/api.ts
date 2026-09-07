import type {
  AddressSuggestion,
  AssessResult,
  PartialEventPayload,
  PortfolioListItem,
  ProgressEventPayload,
  RegionPreset,
  ResolvedRegion,
} from './types'

export async function fetchRegionPresets(): Promise<RegionPreset[]> {
  const res = await fetch('/api/regions')
  return res.json()
}

/** "기존 포트폴리오 조회" 탭용 — 316건 전체를 한 번에 받아 프론트에서 필터링한다. */
export async function fetchPortfolioList(): Promise<PortfolioListItem[]> {
  const res = await fetch('/api/portfolio-list')
  return res.json()
}

/** 입력 주소를 지오코딩→홍수 에이전트로 region_code를 감지한다(디바운스는 호출부 책임). */
export async function resolveRegion(address: string): Promise<ResolvedRegion> {
  const res = await fetch(`/api/resolve-region?address=${encodeURIComponent(address)}`)
  return res.json()
}

/** 도로명주소 자동완성 — 실패해도 부가기능이라 빈 배열로 조용히 degrade. */
export async function searchAddress(keyword: string): Promise<AddressSuggestion[]> {
  const res = await fetch(`/api/address-search?keyword=${encodeURIComponent(keyword)}`)
  if (!res.ok) return []
  return res.json()
}

export interface AssessParams {
  address: string
  collateralValue: string
  regionCode: string
  // HANDOVER §⑧ 층별 리스크 차등화(선택) — 미지정 시 건물 전체 스코어링으로 폴백.
  floorType?: string | null
  floorNo?: string | null
  // 2026-08-19(계속, DEV_LOG.md 참조) — "YYYY-MM-DD" 하나만 있으면 그 날짜의 과거 특보를
  // 조회하고, 비우면(null) 지금 시점 라이브 특보를 조회한다 — mode/timeline_path는 이제
  // 백엔드가 이 값 하나로 알아서 결정한다(리플레이/라이브 드롭다운 제거, 사용자 피드백).
  queryDate?: string | null
}

export interface AssessStreamHandlers {
  onProgress: (payload: ProgressEventPayload) => void
  // 2026-09-07(멘토 피드백 1) — 단계 산출물이 완료 즉시 도착. 마지막 result와 같은 값이다.
  onPartial: (payload: PartialEventPayload) => void
  onResult: (result: AssessResult) => void
  onError: () => void
}

/** SSE 스트림 — 백엔드가 실제 단계에 진입할 때 보낸 progress 이벤트를 그대로 순서대로
 * 중계한다(포트폴리오 재계산 단계는 특보 트리거가 있을 때만 나타남). 연결을 닫는 함수를 반환한다. */
export function startAssessStream(params: AssessParams, handlers: AssessStreamHandlers): () => void {
  const query = new URLSearchParams({
    address: params.address,
    collateral_value: params.collateralValue,
    region_code: params.regionCode,
  })
  if (params.floorType) query.set('floor_type', params.floorType)
  if (params.floorNo) query.set('floor_no', params.floorNo)
  if (params.queryDate) query.set('query_date', params.queryDate)

  const source = new EventSource(`/api/assess?${query.toString()}`)

  source.addEventListener('progress', (ev) => {
    handlers.onProgress(JSON.parse((ev as MessageEvent).data))
  })

  source.addEventListener('partial', (ev) => {
    handlers.onPartial(JSON.parse((ev as MessageEvent).data))
  })

  source.addEventListener('result', (ev) => {
    handlers.onResult(JSON.parse((ev as MessageEvent).data))
    source.close()
  })

  source.onerror = () => {
    handlers.onError()
    source.close()
  }

  return () => source.close()
}
