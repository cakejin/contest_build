import type { ReactNode } from 'react'

/* 2026-09-08 — 결과 화면 ②단계: 근거 섹션의 표·산식·출처·재현 정보를 접는 공통 토글.
   네이티브 <details>라 키보드·스크린리더가 그대로 동작한다. 열림 상태는 저장하지 않는다. */
export function Details({ summary, defaultOpen = false, children }: { summary: ReactNode; defaultOpen?: boolean; children: ReactNode }) {
  return (
    <details className="group mt-3" open={defaultOpen}>
      <summary className="list-none cursor-pointer select-none flex items-center gap-2 py-2 text-[12.5px] font-semibold text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 flex-none transition-transform group-open:rotate-180">
          <path d="M6 9l6 6 6-6" />
        </svg>
        <span>{summary}</span>
      </summary>
      <div className="pb-2 pl-[22px]">{children}</div>
    </details>
  )
}

/** 출처 표기용 — source_id에 절대경로가 들어 있으면 파일명만 보여주고 전체는 title로 남긴다. */
export function shortSourceId(id: string): string {
  const m = id.match(/^([a-z_]+):(.*)$/)
  if (!m) return id
  const tail = m[2].split(/[\\/]/).pop() ?? m[2]
  return `${m[1]}:${tail}`
}

export function SourceChip({ id }: { id: string }) {
  return (
    <span title={id} className="inline-block text-[10.5px] text-muted bg-surface-alt rounded px-1.5 py-0.5 mr-1 mb-1 font-mono">
      {shortSourceId(id)}
    </span>
  )
}
