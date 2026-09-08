// 파이프라인 단계 라벨 — 오른쪽 진행상황(260px)과 좁은 화면의 아이콘 레일(56px)에서 같이 쓴다.
export const STAGE_LABEL: Record<string, string> = {
  advisory: '특보 조회',
  geocode: '주소 → 좌표',
  flood: '침수위험지도',
  building: '건축물대장',
  scenario: '예상손실(EAL)',
  portfolio: '포트폴리오 재계산',
  memo: '심사메모(LLM)',
  done: '완료',
}

export const STAGE_SHORT: Record<string, string> = {
  advisory: '특보',
  geocode: '좌표',
  flood: '지도',
  building: '건물',
  scenario: 'EAL',
  portfolio: '재계산',
  memo: '메모',
  done: '완료',
}
