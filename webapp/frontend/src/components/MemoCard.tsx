import type { MemoData } from '../types'
import { Card } from './Card'
import { Details, SourceChip } from './Details'

/* 2026-09-08 ② — 문장은 그대로 열어두고(심사역이 읽는 산출물), 문장별 source_id 원문은 토글 안으로.
   열린 부분의 인용 표시는 짧은 칩(접두어:파일명)만. 인용 없는 문장은 백엔드 게이트가 이미 걸러냈다. */
export function MemoCard({ memo, bare }: { memo: MemoData; bare?: boolean }) {
  const body = (
    <>
      {memo.fallback_used && (
        <p className="text-muted text-xs mt-0">인용 실패율이 임계치를 넘어 규칙기반 폴백 템플릿으로 대체됐어요(LLM 미사용, 항상 인용률 100%).</p>
      )}
      {memo.sections.map((s, i) => (
        <div key={i} className="text-[13.5px] leading-relaxed py-2 border-b border-surface-alt last:border-b-0">
          <span className="text-muted text-[11px] mr-1.5 tabular-nums">{i + 1}</span>
          {s.text}
          <span className="block mt-1">
            {s.citations.map((c) => (
              <SourceChip key={c} id={c} />
            ))}
          </span>
        </div>
      ))}
      {memo.rejected_sentences.length > 0 && (
        <div className="text-xs text-[#8a3b1f] bg-[#fdf0e9] rounded-lg py-2.5 px-3 mt-2">
          인용검증 게이트가 반려한 문장 {memo.rejected_sentences.length}건(근거 없음/미확인 출처라 심사메모에서 자동 제외됨)
        </div>
      )}
      <Details summary="문장별 source_id 원문 · 인용 검증">
        <ol className="m-0 pl-4 text-[11.5px] text-muted leading-relaxed">
          {memo.sections.map((s, i) => (
            <li key={i} className="break-all">
              {s.citations.join(' · ')}
            </li>
          ))}
        </ol>
        <p className="text-[11.5px] text-muted mt-2 mb-0">
          모든 문장은 에이전트가 태깅한 source_id 집합과 문자열로 대조돼요. 실패한 문장은 자동 차단되고 기록돼요(반려 {memo.rejected_sentences.length}건).
        </p>
      </Details>
    </>
  )
  return bare ? body : <Card icon="memo" title="근거 인용 심사메모">{body}</Card>
}
