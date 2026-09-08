import type { AdvisoryData } from '../types'
import { Card } from './Card'
import { Details } from './Details'
import { Timeline } from './Timeline'
import { fmtIssuedAt } from '../lib/format'

/* 2026-09-08 ② — 열린 부분: 쉬운 한 문장(트리거 여부·건수·첫 특보). 이력 전체 목록은 토글 안.
   ③ — 타임라인(advisory.timeline + trigger_event_ids) 추가. */
export function AdvisoryCard({ advisory, bare }: { advisory: AdvisoryData; bare?: boolean }) {
  const n = advisory.active_warnings.length
  const first = advisory.active_warnings[0]
  const timeline = advisory.timeline ?? []
  const triggerIds = advisory.trigger_event_ids ?? []

  const body = (
    <>
      {n === 0 ? (
        <p className="text-[13.5px] leading-relaxed text-ink mt-0 mb-0">
          이 지역·시점엔 <b>발효 중인 특보가 없어요</b>
          <span className="text-muted text-xs"> (status: {advisory.status})</span>.
        </p>
      ) : (
        <p className="text-[13.5px] leading-relaxed text-ink mt-0 mb-0">
          조회 구간에 특보·재난문자 <b>{n}건</b>이 있어요. 첫 건은 <b>{first.type}</b>({fmtIssuedAt(first.issued_at)}).{' '}
          {advisory.trigger_event ? (
            <>
              이 중 <b>호우·태풍·홍수·폭풍해일 경보 이상</b>{triggerIds.length > 0 ? ` ${triggerIds.length}건` : ''}이 있어 재심사 트리거가 켜졌어요.
            </>
          ) : (
            <>경보 이상 수문 특보는 없어 재심사 트리거는 꺼져 있어요.</>
          )}
        </p>
      )}
      {timeline.length > 1 && (
        <div className="mt-2">
          <Timeline events={timeline} triggerIds={triggerIds} />
        </div>
      )}
      {n > 0 && (
        <Details summary={`특보 이력 ${n}건 · 출처`}>
          {advisory.active_warnings.map((w, i) => (
            <div key={i} className="text-xs py-1.5 border-b border-surface-alt last:border-b-0 flex items-baseline gap-2">
              <strong className="flex-none">{w.type}</strong>
              <span className="text-muted tabular-nums">{fmtIssuedAt(w.issued_at)}</span>
              <a href={w.source_url} target="_blank" rel="noopener noreferrer" className="text-title font-semibold ml-auto">
                출처
              </a>
            </div>
          ))}
          <p className="text-[11.5px] text-muted mt-2 mb-0">특보는 알림 트리거로만 쓰여요 — 예상손실·LTV·금리 계산에는 들어가지 않아요. 빨간 점은 재심사 트리거를 켠 이벤트예요.</p>
        </Details>
      )}
    </>
  )
  return bare ? body : <Card icon="bell" title="기상특보 이력">{body}</Card>
}
