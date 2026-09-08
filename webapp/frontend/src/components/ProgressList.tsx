import type { ProgressItem, Timings } from '../types'
import { Card } from './Card'
import { STAGE_LABEL } from '../lib/stages'

/* 2026-09-08 — 토스형 3단 레이아웃(디자인 캔버스 12p 3안)의 오른쪽 열. 폭이 260px라 단계는 짧은
   라벨로 보여주고 원래 진행 문구는 title(마우스 오버)에 남긴다. 결과가 오면 단계마다 실측 소요초를
   붙인다(백엔드 timings — on_stage 실제 호출 시각 차이, 타이머 흉내 아님). */

export function ProgressList({ items, timings }: { items: ProgressItem[]; timings?: Timings }) {
  const seconds = new Map(timings?.stages.map((s) => [s.stage, s.seconds]) ?? [])
  const visible = items.filter((it) => it.stage !== 'done')
  const finished = items.some((it) => it.stage === 'done')
  return (
    <Card icon="chart" title="진행상황">
      {visible.length === 0 ? (
        <p className="text-muted text-xs m-0">평가를 실행하면 실제 처리 단계가 여기에 표시됩니다.</p>
      ) : (
        <>
          <ul className="list-none m-0 p-0 relative before:content-[''] before:absolute before:left-[3px] before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
            {visible.map((item, i) => {
              const sec = seconds.get(item.stage)
              return (
                <li
                  key={i}
                  title={item.message}
                  className={`relative flex items-center gap-2.5 py-2 pl-[22px] text-[12.5px] ${item.status === 'active' ? 'font-semibold text-ink' : 'text-ink'}`}
                >
                  <span
                    className={`absolute left-0 w-2 h-2 rounded-full flex-none shadow-[0_0_0_3px_var(--color-surface)] ${
                      item.status === 'active' ? 'bg-accent animate-pulse-dot' : 'bg-title'
                    }`}
                  />
                  <span className="flex-1 min-w-0 truncate">{STAGE_LABEL[item.stage] ?? item.message}</span>
                  <span className="text-[10.5px] text-muted tabular-nums flex-none">
                    {sec != null ? `${sec.toFixed(1)}s` : item.status === 'active' ? '…' : ''}
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="text-[10.5px] text-muted mt-2 mb-0">
            {finished && timings
              ? `완료 · 처리 ${timings.total_seconds.toFixed(0)}초${timings.alert_latency_seconds != null ? ` · 특보→알림 ${timings.alert_latency_seconds.toFixed(0)}초` : ''}`
              : items.length > 0
                ? `${STAGE_LABEL[items[items.length - 1].stage] ?? '처리'} 중`
                : ''}
          </p>
        </>
      )}
    </Card>
  )
}
