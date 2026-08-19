import type { AddressSuggestion, AssessResult, ProgressEventPayload, RegionPreset, ResolvedRegion } from './types'

export async function fetchRegionPresets(): Promise<RegionPreset[]> {
  const res = await fetch('/api/regions')
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
  mode: string
  timelinePath?: string | null
  // HANDOVER §⑧ 층별 리스크 차등화(선택) — 미지정 시 건물 전체 스코어링으로 폴백.
  floorType?: string | null
  floorNo?: string | null
}

export interface AssessStreamHandlers {
  onProgress: (payload: ProgressEventPayload) => void
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
    mode: params.mode,
  })
  if (params.timelinePath) query.set('timeline_path', params.timelinePath)
  if (params.floorType) query.set('floor_type', params.floorType)
  if (params.floorNo) query.set('floor_no', params.floorNo)

  const source = new EventSource(`/api/assess?${query.toString()}`)

  source.addEventListener('progress', (ev) => {
    handlers.onProgress(JSON.parse((ev as MessageEvent).data))
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
