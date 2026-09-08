import type { AssessResult, ProgressItem, QueryMode, SubmittedMeta } from '../types'

/* 2026-09-09 — 포트폴리오 지도(별도 HTML)로 갔다 돌아오면 React 앱이 새로 켜져 결과가 사라지던 문제.
   완료된 결과만 같은 탭의 sessionStorage에 두고 앱이 켜질 때 복원한다(탭을 닫으면 사라짐).
   계산 도중 이동하면 그 실행은 SSE가 끊겨 사라지고, 마지막 완료 결과가 복원된다. 복원된 결과는
   상단에 "이전 실행 결과 · 계산 HH:mm" 배지로 표시한다(새로 계산한 것처럼 보이지 않게).
   서버 쪽 "과거 조회 결과 캐시"(PROGRESS.md TODO)와는 별개 — 이건 화면 상태 유지만 담당한다. */

const KEY = 'climate-risk.assess.v1'

export interface SavedForm {
  address: string
  collateralValue: string
  floorType: string
  floorNo: string
  queryMode: QueryMode
  queryDate: string
}

export interface SavedSession {
  savedAt: string // ISO
  result: AssessResult
  meta: SubmittedMeta | null
  progressItems: ProgressItem[]
  form: SavedForm
}

export function loadSession(): SavedSession | null {
  try {
    const raw = window.sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<SavedSession>
    if (!parsed || typeof parsed !== 'object' || !parsed.result || !parsed.savedAt || !parsed.form) return null
    return parsed as SavedSession
  } catch {
    return null
  }
}

export function saveSession(s: SavedSession): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(s))
  } catch {
    // 용량 초과·비공개 모드 등 — 저장 실패는 조용히 무시(화면 동작엔 영향 없음)
  }
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}

export function fmtSavedAt(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}
