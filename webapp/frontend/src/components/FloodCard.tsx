import type { FloodData, FloodDepthClass, FloodMarksNearby, FloorExposure, SubmittedMeta } from '../types'
import { FloodCrossSection } from './FloodCrossSection'
import { Card } from './Card'
import { KvRow } from './KvRow'
import { Details, shortSourceId } from './Details'
import { tierBadgeBgClass } from '../lib/format'

const FREQ_WORD: Record<string, string> = { MAX: '기왕최대' }
function freqWord(label: string | null): string {
  if (!label) return '—'
  return FREQ_WORD[label] ?? `${label}년`
}

/* 2026-09-08 ② — 열린 부분: 배지 + 쉬운 한 문장 + 핵심 행. 커버리지·라이선스·방법론 유의사항·
   SHP 파일명은 토글 안. ③ — 침수심 등급(SEG_CODE 범위)과 실측 침수흔적 근접 요약 행 추가. */
export function FloodCard({
  data,
  coverageLabel,
  depth,
  marks,
  meta,
  exposure,
  bare,
}: {
  data: FloodData
  coverageLabel?: string
  depth?: FloodDepthClass | null
  marks?: FloodMarksNearby | null
  meta?: SubmittedMeta | null
  exposure?: FloorExposure | null
  bare?: boolean
}) {
  const flood = data.flood
  const tierLabel = coverageLabel || (flood.coverage === 'OUT_OF_SCOPE' ? '커버리지 밖' : flood.tier)
  const inScope = flood.coverage === 'IN_SCOPE'
  const within500 = marks?.counts_by_radius_m?.['500'] ?? 0
  const within2k = marks?.counts_by_radius_m?.['2000'] ?? 0

  const lead = !inScope ? (
    <>
      이 좌표는 <b>홍수위험지도 범위 밖</b>이에요. 데이터가 없는 것이지 위험이 낮다는 뜻이 아니에요.
    </>
  ) : coverageLabel ? (
    <>
      이 담보는 홍수위험지도 범위 안이지만 <b>판정을 보류</b>했어요. 데이터 공백이지 위험 낮음이 아니에요.
    </>
  ) : flood.tier === '내부' ? (
    <>
      이 담보는 <b>{flood.river_name ?? '하천'} 범람구역 안</b>에 있어요(폴리곤까지 {flood.distance_to_polygon_m ?? 0}m, {freqWord(flood.freq_label)} 빈도).
      {depth?.reliable ? (
        <>
          {' '}극한 상황을 가정한 예상 침수심은 <b>{depth.label}</b>이에요.
        </>
      ) : null}
    </>
  ) : (
    <>
      이 담보는 {flood.river_name ?? '하천'} 범람구역에서 <b>{flood.distance_to_polygon_m ?? '—'}m 떨어진 {flood.tier}</b> 구간이에요({freqWord(flood.freq_label)} 빈도).
    </>
  )

  // 2026-09-08(계속7) — 10p·11p 목업의 "시각 1개": 범위 안 + 침수심 등급이 있을 때 단면도(왼쪽) + 값 표(오른쪽)
  const diagram = inScope && !coverageLabel && depth ? <FloodCrossSection depth={depth} floorType={meta?.floorType ?? null} floorNo={meta?.floorNo ?? null} exposure={exposure} /> : null
  const rows = (
    <>
      <KvRow label="하천" value={flood.river_name || '—'} />
      <KvRow label="폴리곤까지 거리" value={flood.distance_to_polygon_m != null ? `${flood.distance_to_polygon_m} m` : '—'} />
      <KvRow label="빈도" value={freqWord(flood.freq_label)} />
      {inScope && (
        <KvRow
          label="예상 침수심 등급"
          value={
            depth ? (
              <>
                {depth.label} <span className="text-muted font-normal">({depth.code} · {depth.rank}/{depth.rank_max}{depth.reliable ? '' : ' · 가장 가까운 폴리곤의 등급'})</span>
              </>
            ) : (
              '—'
            )
          }
        />
      )}
      <KvRow
        label="실측 침수흔적"
        value={
          marks ? (
            marks.nearest_m != null ? (
              <>
                최근접 {marks.nearest_m >= 1000 ? `${(marks.nearest_m / 1000).toFixed(1)}km` : `${Math.round(marks.nearest_m)}m`} ({marks.nearest_year}년
                {marks.nearest_cause ? ` · ${marks.nearest_cause}` : ''}
                {marks.nearest_depth_cm != null ? ` · 평균 침수 ${marks.nearest_depth_cm}cm` : ''}) · 500m 내 {within500}건 · 2km 내 {within2k}건
              </>
            ) : (
              '등록 기록 없음'
            )
          ) : (
            <span className="text-muted font-normal">큐레이션 파일 없음</span>
          )
        }
      />
    </>
  )
  const body = (
    <>
      <div className="flex items-center gap-2.5 mb-2">
        <span className={`inline-block py-[5px] px-3 rounded-full text-[11.5px] font-bold tracking-[0.2px] text-white shadow-[0_3px_8px_-3px_rgba(0,0,0,0.3)] ${tierBadgeBgClass(flood.tier, coverageLabel ? 'OUT_OF_SCOPE' : flood.coverage)}`}>
          {tierLabel || '판정'}
        </span>
        <span className="text-[13.5px] leading-relaxed text-ink">{lead}</span>
      </div>
      {diagram ? (
        <div className="grid grid-cols-1 min-[1200px]:grid-cols-[300px_minmax(0,1fr)] gap-x-5 gap-y-2 items-center">
          {diagram}
          <div>{rows}</div>
        </div>
      ) : (
        rows
      )}
      <Details summary="방법론 유의사항 · 출처">
        <div className="text-[11.5px] text-muted leading-relaxed">
          {flood.methodology_disclaimer && <p className="mt-0 mb-1.5">{flood.methodology_disclaimer}</p>}
          {depth && !depth.reliable && <p className="mt-0 mb-1.5">침수심 등급은 이 좌표가 폴리곤 안(내부)일 때만 그 지점의 값이에요. 지금은 가장 가까운 폴리곤의 등급이라 참고용이에요.</p>}
          <p className="m-0">
            커버리지 {flood.coverage}
            {flood.region_name ? ` · ${flood.region_name}` : ''}
            {flood.source_shp_file ? ` · 파일 ${shortSourceId(`shp:${flood.source_shp_file}`).replace('shp:', '')}` : ''}
            {flood.license ? ` · ${flood.license}` : ''}
            {data.source_id ? ` · source_id ${shortSourceId(data.source_id)}` : ''}
          </p>
          {marks && (
            <p className="mt-1.5 mb-0">
              실측 침수흔적: {marks.dataset} 큐레이션 {marks.total_in_dataset}건 · {marks.license_note} — 좌표·원본은 표시하지 않아요.
            </p>
          )}
        </div>
      </Details>
    </>
  )
  return bare ? body : <Card icon="flood" title="침수 위험 판정">{body}</Card>
}
