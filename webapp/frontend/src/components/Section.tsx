import type { ReactNode } from 'react'

/* 2026-09-08 — 결과 화면 확정안(디자인 캔버스 11p) 섹션 골격: 번호 원 + 제목 + 오른쪽 작은 설명.
   기존 Card와 달리 아이콘 대신 번호를 쓴다 — 읽는 순서를 고정하기 위함(결론 → 요약 → 조치 → 근거).
   tone은 테두리 색만 바꾼다(결론=경고 톤, 조치=민트 톤). 색 띠·그라데이션은 쓰지 않는다. */
export type SectionTone = 'default' | 'alert' | 'action'

const TONE_BORDER: Record<SectionTone, string> = {
  default: 'border-border/50',
  alert: 'border-[#f3c9c4]',
  action: 'border-accent-soft',
}

export function Section({
  id,
  n,
  title,
  note,
  tone = 'default',
  children,
}: {
  id: string
  n: number
  title: string
  note?: ReactNode
  tone?: SectionTone
  children: ReactNode
}) {
  return (
    <section id={id} className={`bg-surface border ${TONE_BORDER[tone]} rounded-card shadow-card mb-3 scroll-mt-[100px]`}>
      <div className="flex items-center gap-2.5 py-3 px-[18px]">
        <span className="flex-none w-[22px] h-[22px] rounded-full bg-ink text-white text-[11.5px] font-bold flex items-center justify-center">{n}</span>
        <h2 className="m-0 text-[13.5px] font-bold text-ink">{title}</h2>
        {note && <span className="ml-auto text-[11.5px] text-muted text-right">{note}</span>}
      </div>
      <div className="px-[18px] pb-4">{children}</div>
    </section>
  )
}

/** 아직 도착하지 않은 단계용 — 섹션 모양은 유지하고 본문만 "계산 중". */
export function PendingSection({ id, n, title, text }: { id: string; n: number; title: string; text: string }) {
  return (
    <Section id={id} n={n} title={title}>
      <p className="text-muted text-xs flex items-center gap-2 m-0">
        <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot flex-none" />
        {text}
      </p>
    </Section>
  )
}

/** 상태 배지(로젠지) — 색만으로 뜻을 전하지 않도록 항상 글자를 넣는다. */
export type LozengeTone = 'solid' | 'red' | 'amber' | 'green' | 'mint' | 'grey' | 'dash'
const LZ: Record<LozengeTone, string> = {
  solid: 'bg-tier-inner text-white',
  red: 'bg-[#fdecea] text-[#8a1f12]',
  amber: 'bg-[#fff4d6] text-[#7a4b00]',
  green: 'bg-[#e6f6f2] text-[#0f6b57]',
  mint: 'bg-accent-soft/70 text-title',
  grey: 'bg-surface-alt text-muted',
  dash: 'bg-surface text-muted border border-dashed border-[#9aa4a6]',
}
export function Lozenge({ tone, children }: { tone: LozengeTone; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 text-[10.5px] font-bold py-0.5 px-[7px] rounded-[3px] whitespace-nowrap ${LZ[tone]}`}>{children}</span>
}

/** 요약 행: 키 | 값 | 배지(오른쪽 열 고정) — 배지 위치를 한 열로 통일(11p 확정안). */
export function SummaryRow({ k, children, badge }: { k: string; children: ReactNode; badge?: ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_minmax(0,1fr)_auto] gap-2 items-center py-2.5 border-t border-surface-alt text-[13.5px]">
      <span className="text-muted font-semibold">{k}</span>
      <span className="min-w-0">{children}</span>
      <span className="flex justify-end">{badge}</span>
    </div>
  )
}
