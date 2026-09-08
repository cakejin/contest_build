import type { ReactNode } from 'react'

/* 2026-09-08 — 결과 화면 확정안(디자인 캔버스 11p) 섹션 골격. 2026-09-09 보고서형 미니멀로 카드 껍데기
   (테두리·그림자·번호 원·톤 테두리)를 걷어내고 제목 + 오른쪽 작은 설명만 남긴다 — PanelSection과 같은 결.
   결론의 경고 톤은 테두리가 아니라 본문의 알림 배너가 담당한다. */
export function Section({
  id,
  title,
  note,
  children,
}: {
  id: string
  title: string
  note?: ReactNode
  children: ReactNode
}) {
  return (
    <section id={id} className="px-8 pt-8 pb-4 scroll-mt-[100px]">
      <div className="flex items-baseline gap-2.5 mb-4">
        <h2 className="m-0 text-[18px] font-extrabold text-ink">{title}</h2>
        {note && <span className="ml-auto text-[12px] text-muted text-right">{note}</span>}
      </div>
      {children}
    </section>
  )
}

/** 아직 도착하지 않은 단계용 — 섹션 모양은 유지하고 본문만 "계산 중". */
export function PendingSection({ id, title, text }: { id: string; title: string; text: string }) {
  return (
    <Section id={id} title={title}>
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
    <div className="grid grid-cols-[140px_minmax(0,1fr)_auto] gap-3 items-center py-3 border-t border-surface-alt text-[14px]">
      <span className="text-muted font-semibold">{k}</span>
      <span className="min-w-0">{children}</span>
      <span className="flex justify-end">{badge}</span>
    </div>
  )
}
