import type { FloodDepthClass, FloorExposure } from '../types'

/* 2026-09-08(계속7) — 침수 노출 단면도(디자인 캔버스 10p·11p의 SVG). 지표선 위로 예상 침수심 범위를
   물 띠로 그리고, 건물 상자 안에 심사 대상 층의 바닥 높이를 표시한다. 값은 전부 응답에 있는 것:
   침수심 등급 하한·상한(flood_depth_class), 층 바닥 높이·층 위험등급(building.floor_exposure).
   새 계산 없음 — 층을 안 넣었으면 "층을 입력하면 층별 노출도 계산" 안내만. */

const W = 300
const H = 140
const GROUND_Y = 100
// 건물 상자는 오른쪽에 두고 왼쪽 빈 공간에 침수심 라벨을 놓는다(라벨끼리 안 겹치게)
const BOX_X = 150
const BOX_W = 110
const BOX_TOP = 22

function fmtM(v: number): string {
  return `${v.toFixed(1)}m`
}

export function FloodCrossSection({
  depth,
  floorType,
  floorNo,
  exposure,
}: {
  depth: FloodDepthClass
  floorType: string | null
  floorNo: string | null
  exposure?: FloorExposure | null
}) {
  const basement = floorType === '지하'
  const floorLabel = floorType ? `${floorType} ${floorNo || '?'}층` : null
  const elev = exposure?.floor_elevation_m ?? null
  // 눈금: 침수심 상한과 층 바닥 높이 중 큰 값이 상자 높이(GROUND_Y − BOX_TOP) 안에 들어오게
  const maxM = Math.max(depth.upper_m, elev != null ? Math.abs(elev) + 0.3 : 0, 2.5)
  const s = (GROUND_Y - BOX_TOP - 6) / maxM
  const yUpper = GROUND_Y - depth.upper_m * s
  const yLower = GROUND_Y - depth.lower_m * s
  const tierWord = exposure?.floor_risk_tier === 'HIGH' ? '높음' : exposure?.floor_risk_tier === 'MEDIUM' ? '중간' : exposure?.floor_risk_tier === 'LOW' ? '낮음' : null
  const floorY = elev != null ? Math.max(BOX_TOP + 4, Math.min(H - 6, GROUND_Y - elev * s)) : null

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`침수 단면도: 예상 침수심 ${depth.label}${floorLabel ? `, ${floorLabel}` : ''}`} className="max-w-full h-auto">
      {/* 지표 */}
      <rect x={0} y={GROUND_Y} width={W} height={H - GROUND_Y - 14} fill="#e3e6e6" />
      {/* 건물 상자 (지하층이면 지표 아래 상자 추가) */}
      <rect x={BOX_X} y={BOX_TOP} width={BOX_W} height={GROUND_Y - BOX_TOP} fill="#fff" stroke="#9aa4a6" />
      {basement && <rect x={BOX_X} y={GROUND_Y} width={BOX_W} height={22} fill="#fff" stroke="#9aa4a6" strokeDasharray="3 2" />}
      {/* 예상 침수심: 하한까지 진하게, 상한까지 연하게 */}
      <rect x={0} y={yLower} width={W} height={GROUND_Y - yLower + (basement ? 22 : 0)} fill="rgba(200,68,60,0.20)" />
      <rect x={0} y={yUpper} width={W} height={yLower - yUpper} fill="rgba(200,68,60,0.10)" />
      <line x1={0} y1={yUpper} x2={W} y2={yUpper} stroke="#c8443c" strokeWidth={1.5} strokeDasharray="5 3" />
      <text x={4} y={yUpper - 5} textAnchor="start" fontSize={11} fill="#8a1f12">
        예상 침수심 {fmtM(depth.lower_m)}~{fmtM(depth.upper_m)}
        {depth.reliable ? '' : ' (인접 폴리곤)'}
      </text>
      {/* 심사 대상 층 */}
      {floorLabel ? (
        <>
          {floorY != null && !basement && <line x1={BOX_X} y1={floorY} x2={BOX_X + BOX_W} y2={floorY} stroke="#007f6c" strokeWidth={1.5} />}
          {/* 층 라벨은 바닥선 바로 아래(상자 안), 층 노출 등급은 상자 바닥 — 서로 겹치지 않게 */}
          <text x={BOX_X + BOX_W / 2} y={basement ? GROUND_Y + 15 : (floorY ?? GROUND_Y - 20) + 13} textAnchor="middle" fontSize={11} fontWeight={700} fill="#007f6c">
            {floorLabel}
            {elev != null && !basement ? ` 바닥 +${fmtM(elev)}` : ''}
          </text>
          {tierWord && (
            <text x={BOX_X + BOX_W / 2} y={basement ? GROUND_Y - 6 : GROUND_Y - 6} textAnchor="middle" fontSize={10.5} fill="#5b6466">
              층 노출 {tierWord}
            </text>
          )}
        </>
      ) : (
        <text x={BOX_X + BOX_W / 2} y={GROUND_Y - 8} textAnchor="middle" fontSize={11} fill="#5b6466">
          1F 바닥 = 지표
        </text>
      )}
      <text x={4} y={H - 3} fontSize={10} fill="#5b6466">
        {floorLabel ? '지표 기준 · 극한 상황(기왕최대) 가정' : '층을 입력하면 층별 노출도를 계산해요'}
      </text>
    </svg>
  )
}
