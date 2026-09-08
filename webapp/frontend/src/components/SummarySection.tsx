import type { PartialResult, SubmittedMeta } from '../types'
import { Lozenge, SummaryRow } from './Section'
import { PanelSection } from './Panel'
import type { LozengeTone } from './Section'
import { fmtWon, fmtIssuedAt } from '../lib/format'
import { Details, shortSourceId } from './Details'

/* 2026-09-08 — 확정안 11p "2 요약": 키 | 값 | 배지 3열 행. 배지는 오른쪽 열에만 둔다.
   ③에서 예상 침수심(등급 범위)·실제 피해 기록(실측 침수흔적) 행을 추가. 값은 전부 응답에 있는 것. */

const TIER_TONE: Record<string, LozengeTone> = { 내부: 'solid', 근접: 'amber', 원거리: 'green' }
const BUILDING_STATUS: Record<string, string> = { OK: '건축물대장 확인', PARTIAL: '일부 항목 누락', FAILED: '조회 실패' }

export function SummarySection({ data, meta }: { data: PartialResult; meta: SubmittedMeta | null }) {
  const flood = data.flood?.flood
  const depth = data.flood_depth_class
  const marks = data.flood_marks
  const building = data.building
  const eal = data.scenario?.eal
  const advisory = data.advisory
  const sev = data.portfolio_batch?.severity_summary
  const ratio = eal?.EAL_mean != null && meta?.collateralValue ? (eal.EAL_mean / meta.collateralValue) * 100 : null
  const buildingLevel = building?.vulnerability_score == null ? null : building.vulnerability_score >= 70 ? '높음' : building.vulnerability_score >= 40 ? '중간' : '낮음'
  const buildingTone: LozengeTone = buildingLevel === '높음' ? 'red' : buildingLevel === '중간' ? 'amber' : buildingLevel === '낮음' ? 'green' : 'grey'
  const firstWarning = advisory?.active_warnings[0]
  const nearest = marks?.nearest_m ?? null
  const within2k = marks?.counts_by_radius_m?.['2000'] ?? 0
  const within500 = marks?.counts_by_radius_m?.['500'] ?? 0

  const reg = building?.registry
  const year = reg?.use_apr_day ? String(reg.use_apr_day).slice(0, 4) : null
  const structFactor = building?.contributing_factors?.find((f) => f.name === '구조재질')
  const useFactor = building?.contributing_factors?.find((f) => f.name === '주용도')
  const lead =
    flood && building ? (
      <>
        {year ? `${year}년 준공한 ` : ''}
        {structFactor ? `${structFactor.raw_value} ` : ''}
        {reg?.grnd_flr_cnt != null ? `${reg.grnd_flr_cnt}층 ` : ''}
        {useFactor ? `${useFactor.raw_value}` : '건물'}이에요.{' '}
        {flood.coverage === 'OUT_OF_SCOPE' ? (
          <>홍수위험지도 범위 밖이라 <b>침수 판정은 데이터 없음</b>이에요 — 위험 낮음이 아니에요.</>
        ) : flood.tier === '내부' ? (
          <>
            {flood.river_name ?? '하천'} 범람구역 안에 있어서 <b>위치 리스크가 건물 리스크보다 {building.vulnerability_score != null && building.vulnerability_score < 40 ? '큰' : '주가 되는'}</b> 담보예요.
          </>
        ) : (
          <>
            {flood.river_name ?? '하천'} 범람구역에서 {flood.distance_to_polygon_m ?? '—'}m 떨어진 <b>{flood.tier}</b> 구간이에요.
          </>
        )}
      </>
    ) : (
      <span className="text-muted">침수 판정과 건물 정보가 오면 한 줄 요약이 여기 나와요.</span>
    )

  return (
    <PanelSection id="sec-summary" title="요약" note="건축HUB · 홍수위험지도 · 합성 포트폴리오" lead={lead}>
      <SummaryRow
        k="침수 판정"
        badge={
          flood ? (
            data.coverage_label ? <Lozenge tone="grey">{data.coverage_label.split('(')[0]}</Lozenge> : <Lozenge tone={TIER_TONE[flood.tier ?? ''] ?? 'grey'}>{flood.tier ?? '—'}</Lozenge>
          ) : (
            <Lozenge tone="grey">계산 중</Lozenge>
          )
        }
      >
        {flood ? (
          flood.coverage === 'OUT_OF_SCOPE' ? (
            '홍수위험지도 범위 밖 — 데이터 없음이지 위험 낮음이 아님'
          ) : (
            <>
              {flood.river_name ?? '—'} 범람구역 · 폴리곤까지 {flood.distance_to_polygon_m ?? '—'}m · {flood.freq_label === 'MAX' ? '기왕최대' : `${flood.freq_label ?? '—'}년`} 빈도
            </>
          )
        ) : (
          <span className="text-muted">홍수위험지도 조회 중</span>
        )}
      </SummaryRow>

      {flood && flood.coverage === 'IN_SCOPE' && (
        <SummaryRow
          k="예상 침수심"
          badge={depth ? <Lozenge tone={depth.reliable ? (depth.rank >= 3 ? 'red' : 'amber') : 'grey'}>{depth.reliable ? `등급 ${depth.rank}/${depth.rank_max}` : '참고'}</Lozenge> : <Lozenge tone="dash">없음</Lozenge>}
        >
          {depth ? (
            <>
              <b>{depth.label}</b> <span className="text-muted">({depth.code}{depth.reliable ? '' : ' · 가장 가까운 폴리곤의 등급 — 이 좌표의 값 아님'})</span>
            </>
          ) : (
            <span className="text-muted">이 위치의 침수심 등급 없음</span>
          )}
        </SummaryRow>
      )}

      <SummaryRow k="건물취약도" badge={building ? <Lozenge tone={buildingTone}>{buildingLevel ?? '미확인'}</Lozenge> : <Lozenge tone="grey">계산 중</Lozenge>}>
        {building ? (
          <>
            <b>{building.vulnerability_score ?? '—'}</b> / 100 · {BUILDING_STATUS[building.status] ?? building.status}
            {building.registry?.use_apr_day ? ` · ${String(building.registry.use_apr_day).slice(0, 4)}년` : ''}
            {building.registry?.ugrnd_flr_cnt != null ? (building.registry.ugrnd_flr_cnt > 0 ? ` · 지하 ${building.registry.ugrnd_flr_cnt}층` : ' · 지하 없음') : ''}
            {building.status !== 'OK' && building.note ? <span className="text-muted"> · {building.note}</span> : null}
          </>
        ) : (
          <span className="text-muted">건축물대장 조회 중</span>
        )}
      </SummaryRow>

      <SummaryRow k="예상손실" badge={eal ? <Lozenge tone={eal.status === 'OK' ? 'grey' : 'dash'}>{eal.status === 'OK' ? '산출' : '산출 불가'}</Lozenge> : <Lozenge tone="grey">계산 중</Lozenge>}>
        {eal ? (
          eal.status === 'OK' && eal.EAL_mean != null ? (
            <>
              <b>{fmtWon(eal.EAL_mean)}</b>/년{ratio != null ? ` · 담보가액의 ${ratio.toFixed(2)}%` : ''} · p95 {fmtWon(eal.EAL_p95)}
            </>
          ) : (
            <span className="text-muted">{eal.reason ?? '입력 데이터 불충분'}</span>
          )
        ) : (
          <span className="text-muted">시뮬레이션 중</span>
        )}
      </SummaryRow>

      {flood && (
        <SummaryRow
          k="실제 피해 기록"
          badge={marks ? (within2k > 0 ? <Lozenge tone="red">기록 있음</Lozenge> : <Lozenge tone="grey">2km 내 없음</Lozenge>) : <Lozenge tone="dash">데이터 없음</Lozenge>}
        >
          {marks ? (
            nearest != null ? (
              <>
                {nearest <= 2000 ? <b>{Math.round(nearest)}m 지점 {marks.nearest_year}년 실측 침수흔적</b> : <>가장 가까운 침수흔적 {(nearest / 1000).toFixed(1)}km</>}
                {' · '}500m 내 {within500}건 · 2km 내 {within2k}건
              </>
            ) : (
              <span className="text-muted">등록된 실측 침수흔적 없음</span>
            )
          ) : (
            <span className="text-muted">실측 침수흔적 큐레이션 파일 없음 — 데이터 없음은 위험 낮음이 아님</span>
          )}
        </SummaryRow>
      )}

      <SummaryRow
        k="특보·실사건"
        badge={advisory ? <Lozenge tone={advisory.trigger_event ? 'red' : 'grey'}>{advisory.trigger_event ? '트리거' : '없음'}</Lozenge> : <Lozenge tone="grey">조회 중</Lozenge>}
      >
        {advisory ? (
          advisory.active_warnings.length === 0 ? (
            <span className="text-muted">이 지역·시점 특보 없음</span>
          ) : (
            <>
              {advisory.active_warnings.length}건 · {firstWarning?.type} {fmtIssuedAt(firstWarning?.issued_at)}
              {advisory.active_warnings.length > 1 ? ' 외' : ''}
            </>
          )
        ) : (
          <span className="text-muted">기상특보 조회 중</span>
        )}
      </SummaryRow>

      <SummaryRow
        k="재심사 알림"
        badge={
          sev ? (
            sev.region_triggered ? <Lozenge tone="solid">{sev.warning_count > 0 ? '심각' : sev.advisory_count > 0 ? '주의' : '강수미확인'}</Lozenge> : <Lozenge tone="green">없음</Lozenge>
          ) : advisory && !advisory.trigger_event ? (
            <Lozenge tone="green">없음</Lozenge>
          ) : (
            <Lozenge tone="grey">계산 중</Lozenge>
          )
        }
      >
        {sev ? (
          sev.region_triggered ? (
            <>
              특보 지역 담보 {sev.matched_count}건 중 {sev.alert_count}건 · 심각 {sev.warning_count} · 주의 {sev.advisory_count}
              {data.timings?.alert_latency_seconds != null ? ` · 특보 조회 시작 ${data.timings.alert_latency_seconds.toFixed(1)}초 뒤 알림` : ''}
            </>
          ) : (
            <span className="text-muted">경보 이상 수문 특보 없음 · 매칭 {sev.matched_count}건</span>
          )
        ) : advisory && !advisory.trigger_event ? (
          <span className="text-muted">특보 트리거 없어 재계산 생략</span>
        ) : (
          <span className="text-muted">특보 지역 담보 재계산 중</span>
        )}
      </SummaryRow>

      {meta?.collateralValue ? (
        <SummaryRow k="담보가액" badge={meta.collateralId ? <Lozenge tone="grey">합성</Lozenge> : undefined}>
          {fmtWon(meta.collateralValue)}
          {meta.collateralId ? ` · ${meta.collateralId}` : ''}
        </SummaryRow>
      ) : null}
      {(data.flood || building || eal || advisory) && (
        <Details summary="출처 보기">
          <ul className="m-0 pl-4 text-[11.5px] text-muted leading-relaxed">
            {data.flood && <li>침수: 환경부 홍수위험지도{flood?.source_shp_file ? ` · ${shortSourceId(`shp:${flood.source_shp_file}`).replace('shp:', '')}` : ''}{flood?.license ? ` · ${flood.license}` : ''}</li>}
            {marks && <li>실측 침수흔적: {marks.dataset} 큐레이션 {marks.total_in_dataset}건 · {marks.license_note}</li>}
            {building && <li>건물: {building.source || '건축HUB 건축물대장'}{building.source_id ? ` · ${shortSourceId(building.source_id)}` : ''}</li>}
            {eal && <li>손실: 몬테카를로 시드 {eal.seed} · {eal.n_iterations.toLocaleString()}회{data.scenario?.source_id ? ` · ${data.scenario.source_id}` : ''}</li>}
            {advisory && <li>특보: {advisory.mode === 'historical' ? '기상청 API허브 특보 이력 + 재난문자 + 큐레이션' : advisory.mode === 'live' ? '기상청 특보 API(지금 시점)' : '큐레이션 리플레이'} · status {advisory.status}</li>}
            {meta?.collateralId && <li>담보가액: 합성 포트폴리오({meta.collateralId})</li>}
          </ul>
        </Details>
      )}
    </PanelSection>
  )
}
