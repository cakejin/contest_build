import type { ReactNode } from 'react'

/* 2026-09-08 — 확정안 v2.1(디자인 캔버스 11p): 결론 카드 아래의 섹션들은 흰 패널 한 장 안에
   "제목 + 출처(회색) + 쉬운 한 문장 + 시각 1개 + 표" 골격으로 세로로 이어진다(토스 분석 탭 흐름).
   섹션마다 카드를 따로 두지 않는다. id는 섹션 탭 앵커용. */
export function Panel({ children }: { children: ReactNode }) {
  // 2026-09-09 — 보고서형 미니멀: 패널 자체의 테두리·그림자 없음(결과 시트가 곧 종이). 섹션은 여백으로만 나뉜다.
  return <div>{children}</div>
}

export function PanelSection({
  id,
  title,
  note,
  help,
  lead,
  children,
}: {
  id: string
  title: string
  note?: ReactNode
  help?: ReactNode
  lead?: ReactNode
  children?: ReactNode
}) {
  return (
    <section id={id} className="px-8 pt-10 pb-4 scroll-mt-[100px]">
      <h3 className="m-0 text-[18px] font-extrabold text-ink flex items-baseline gap-2 flex-wrap">
        {title}
        {note && <small className="text-[12px] font-normal text-muted">{note}</small>}
        {help && <span className="ml-auto text-[12px] font-normal text-muted">{help}</span>}
      </h3>
      {lead && <p className="text-[14.5px] leading-[1.75] text-[#3a4446] mt-2.5 mb-4">{lead}</p>}
      {children}
    </section>
  )
}

export function PendingPanelSection({ id, title, text }: { id: string; title: string; text: string }) {
  return (
    <PanelSection id={id} title={title}>
      <p className="text-muted text-xs flex items-center gap-2 m-0 mb-2">
        <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot flex-none" />
        {text}
      </p>
    </PanelSection>
  )
}
