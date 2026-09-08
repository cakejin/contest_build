import type { AdvisoryEvent } from '../types'
import { fmtIssuedAt } from '../lib/format'

/* 2026-09-08 ③ — 특보 타임라인. advisory.timeline(이력 원본)을 시각 순으로 한 줄에 놓고,
   백엔드가 골라준 trigger_event_ids만 빨강으로 표시한다(규칙은 프론트에 없다). 날짜만 있는
   이벤트(time_precision=day)는 그날 00:00 위치. 라벨은 트리거·처음·마지막만 붙여 겹침을 피한다. */

function parseIso(s: string): number {
  const t = Date.parse(s.length === 10 ? `${s}T00:00:00+09:00` : s)
  return Number.isFinite(t) ? t : NaN
}

export function Timeline({ events, triggerIds }: { events: AdvisoryEvent[]; triggerIds: string[] }) {
  const pts = events
    .map((e) => ({ e, t: parseIso(e.issued_at) }))
    .filter((p) => Number.isFinite(p.t))
    .sort((a, b) => a.t - b.t)
  if (pts.length === 0) return null
  const t0 = pts[0].t
  const t1 = pts[pts.length - 1].t
  const span = Math.max(1, t1 - t0)
  const W = 900
  const PAD = 16
  const x = (t: number) => PAD + ((t - t0) / span) * (W - PAD * 2)
  const trig = new Set(triggerIds)
  const firstTrigger = pts.find((p) => trig.has(p.e.event_id))

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} 66`} className="w-full min-w-[520px] h-[66px]" role="img" aria-label="특보 타임라인">
        <line x1={PAD} y1={30} x2={W - PAD} y2={30} stroke="#e3e6e6" strokeWidth={4} strokeLinecap="round" />
        {firstTrigger && <line x1={x(firstTrigger.t)} y1={30} x2={W - PAD} y2={30} stroke="#c8443c" strokeWidth={4} strokeLinecap="round" />}
        {pts.map((p, i) => {
          const isTrig = trig.has(p.e.event_id)
          const label = isTrig || i === 0 || i === pts.length - 1
          const cx = x(p.t)
          const anchor = i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle'
          const above = i % 2 === 0
          return (
            <g key={p.e.event_id}>
              <circle cx={cx} cy={30} r={isTrig ? 6 : 4} fill={isTrig ? '#c8443c' : '#9aa4a6'} />
              {label && (
                <text x={cx} y={above ? 16 : 52} textAnchor={anchor} fontSize={10} fill={isTrig ? '#8a1f12' : '#5b6466'} fontWeight={isTrig ? 700 : 400}>
                  {fmtIssuedAt(p.e.issued_at)} {(p.e.warning_type ?? p.e.event_type).slice(0, 14)}
                  {isTrig ? ' → 트리거' : ''}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
