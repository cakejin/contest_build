import type { BuildingData } from '../types'
import { Card } from './Card'
import { KvRow } from './KvRow'
import { Details, shortSourceId } from './Details'

const TIER_LABEL: Record<string, string> = { HIGH: '고위험', MEDIUM: '중위험', LOW: '저위험' }
const TIER_CLASS: Record<string, string> = {
  HIGH: 'bg-[#fdecea] text-[#8a1f12]',
  MEDIUM: 'bg-[#fff4e0] text-[#8a5a12]',
  LOW: 'bg-[#e6f6f2] text-[#0f6b57]',
}
const STATUS_LABEL: Record<string, string> = {
  OK: '건축물대장 확인',
  PARTIAL: '일부 항목 누락',
  FAILED: '건축물대장 조회 실패',
}

function fmtDay(s: string | null | undefined): string {
  if (!s || s.length < 8) return s ?? '—'
  return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}`
}

/* 2026-09-08 ② — 열린 부분: 점수·상태 + 쉬운 한 문장(가장 큰 요인) + 층별 리스크(입력 시).
   ③ — 요인별 기여도 타일 4개(contribution = 정규화점수 × 가중치, 백엔드 값)와 건축물대장 요약 행 추가.
   요인 표·가중치·출처는 토글 안. 실패/결측 사유는 접지 않는다(데이터 없음 ≠ 위험 없음). */
export function BuildingCard({ data, bare }: { data: BuildingData; bare?: boolean }) {
  const factors = data.contributing_factors || []
  const floorExposure = data.floor_exposure
  const reg = data.registry
  const contrib = (f: (typeof factors)[number]) => f.contribution ?? f.normalized_score * f.weight_used
  const ranked = [...factors].sort((a, b) => contrib(b) - contrib(a))
  const top = ranked[0]
  const level = data.vulnerability_score == null ? null : data.vulnerability_score >= 70 ? '높은' : data.vulnerability_score >= 40 ? '중간' : '낮은'

  const body = (
    <>
      {data.vulnerability_score != null && level ? (
        <p className="text-[14.5px] leading-[1.75] text-ink mt-0 mb-4">
          건물 자체는 <b>{data.vulnerability_score}점으로 {level} 편</b>이에요.
          {top ? (
            <>
              {' '}가장 큰 요인은 <b>{top.name}</b>({top.raw_value}, {contrib(top).toFixed(1)}점)이에요.
            </>
          ) : null}
        </p>
      ) : null}
      {factors.length > 0 && (
        <div className="grid grid-cols-4 max-[700px]:grid-cols-2 gap-6 mb-5">
          {factors.map((f, i) => (
            <div key={i} className="border-t border-surface-alt pt-2.5">
              <div className="text-[11px] text-muted">{f.name}</div>
              <div className="text-[20px] font-extrabold tabular-nums leading-tight mt-0.5">
                {contrib(f).toFixed(1)}
                <span className="text-[11px] text-muted font-medium"> /{Math.round(f.weight_used * 100)}</span>
              </div>
              <div className="text-[11px] text-muted truncate" title={String(f.raw_value)}>
                {f.name === '연식' && typeof f.raw_value === 'string' && f.raw_value.length >= 8 ? `${f.raw_value.slice(0, 4)}년` : f.raw_value}
              </div>
            </div>
          ))}
        </div>
      )}
      <KvRow label="점수" value={`${data.vulnerability_score ?? '—'} / 100`} />
      <KvRow label="상태" value={STATUS_LABEL[data.status] ?? data.status} />
      {reg && (
        <>
          <KvRow
            label="대장 요약"
            value={
              <span className="font-medium">
                {reg.tot_area != null ? `연면적 ${reg.tot_area}㎡` : ''}
                {reg.arch_area != null ? ` · 건축면적 ${reg.arch_area}㎡` : ''}
                {reg.grnd_flr_cnt != null ? ` · 지상 ${reg.grnd_flr_cnt}층` : ''}
                {reg.ugrnd_flr_cnt != null ? (reg.ugrnd_flr_cnt > 0 ? ` · 지하 ${reg.ugrnd_flr_cnt}층` : ' · 지하 없음') : ''}
              </span>
            }
          />
          <KvRow
            label="높이 · 지붕 · 내진"
            value={
              <span className="font-medium">
                {reg.height_m != null ? `${reg.height_m}m` : '—'}
                {reg.roof ? ` · ${reg.roof}` : ''}
                {reg.earthquake_design ? ` · 내진설계 ${reg.earthquake_design === 'Y' ? '적용' : '미적용'}` : ''}
                {reg.use_apr_day ? ` · 사용승인 ${fmtDay(reg.use_apr_day)}` : ''}
              </span>
            }
          />
        </>
      )}
      {data.status !== 'OK' && (
        <div className="mt-3 text-xs text-[#8a1f12] bg-[#fdecea] rounded-lg py-2.5 px-3">
          {data.note ?? '건물 정보를 확인하지 못했어요'}
          {data.missing_fields && data.missing_fields.length > 0 && <span className="block text-muted mt-1">결측 항목: {data.missing_fields.join(', ')}</span>}
          <span className="block text-muted mt-1">데이터 없음은 위험 낮음이 아니에요 — 같은 조건으로 다시 실행하거나 건축물대장을 직접 확인해 주세요.</span>
        </div>
      )}
      {floorExposure && (
        <div className="mt-5">
          <div className="flex justify-between items-center text-[13.5px]">
            <span className="text-muted">층별 리스크</span>
            {floorExposure.floor_risk_tier ? (
              <span className={`text-xs font-bold py-1 px-2.5 rounded-full ${TIER_CLASS[floorExposure.floor_risk_tier]}`}>{TIER_LABEL[floorExposure.floor_risk_tier]}</span>
            ) : (
              <span className="text-xs font-semibold text-muted">미판정</span>
            )}
          </div>
          <p className="text-muted text-xs mt-1.5">
            {floorExposure.fallback_to_building_score ? `${floorExposure.reason} — 건물 전체 점수로 대체` : floorExposure.basis}
          </p>
          {floorExposure.exposure_ratio !== null && (
            <p className="text-muted text-xs mt-1">
              층 바닥 높이 {floorExposure.floor_elevation_m}m · 침수심 상한 {floorExposure.depth_upper_m}m · 노출비율 {(floorExposure.exposure_ratio * 100).toFixed(0)}%
            </p>
          )}
        </div>
      )}
      {factors.length > 0 && (
        <Details summary={`요인 ${factors.length}개 · 가중치 · 출처`}>
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="text-left py-2 px-2 border-b border-surface-alt text-muted font-semibold">항목</th>
                <th className="text-left py-2 px-2 border-b border-surface-alt text-muted font-semibold">원값</th>
                <th className="text-right py-2 px-2 border-b border-surface-alt text-muted font-semibold">정규화점수</th>
                <th className="text-right py-2 px-2 border-b border-surface-alt text-muted font-semibold">가중치</th>
                <th className="text-right py-2 px-2 border-b border-surface-alt text-muted font-semibold">기여</th>
              </tr>
            </thead>
            <tbody>
              {factors.map((f, i) => (
                <tr key={i} className={i % 2 === 1 ? 'bg-black/[0.014]' : ''}>
                  <td className="py-2 px-2 border-b border-surface-alt">{f.name}</td>
                  <td className="py-2 px-2 border-b border-surface-alt">{f.raw_value}</td>
                  <td className="py-2 px-2 border-b border-surface-alt text-right tabular-nums">{Number(f.normalized_score).toFixed(1)}</td>
                  <td className="py-2 px-2 border-b border-surface-alt text-right tabular-nums">{(f.weight_used * 100).toFixed(1)}%</td>
                  <td className="py-2 px-2 border-b border-surface-alt text-right tabular-nums">{contrib(f).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11.5px] text-muted mt-2 mb-0">
            가중합(잠정 가중치, 실측 캘리브레이션 대기) · 대장 요약은 표시용이며 취약도 계산엔 쓰이지 않아요
            {data.source ? ` · ${data.source}` : ''}
            {data.source_id ? ` · ${shortSourceId(data.source_id)}` : ''}
          </p>
        </Details>
      )}
    </>
  )
  return bare ? body : <Card icon="building" title="건물취약도">{body}</Card>
}
