import type { MemoData } from '../types'
import { Card } from './Card'

export function MemoCard({ memo }: { memo: MemoData }) {
  return (
    <Card icon="memo" title="근거 인용 심사메모">
      {memo.fallback_used && (
        <p className="text-muted text-xs">
          인용 실패율이 임계치를 넘어 규칙기반 폴백 템플릿으로 대체됐어요(LLM 미사용, 항상 인용률 100%).
        </p>
      )}
      {memo.sections.map((s, i) => (
        <div key={i} className="text-[13px] py-2.5 pl-3 border-l-[3px] border-accent-soft mb-2">
          {s.text}
          <span className="block text-[11px] text-muted mt-1">근거: {s.citations.join(', ')}</span>
        </div>
      ))}
      {memo.rejected_sentences.length > 0 && (
        <div className="text-xs text-[#8a3b1f] bg-[#fdf0e9] rounded-lg py-2.5 px-3 mt-1.5">
          인용검증 게이트가 반려한 문장 {memo.rejected_sentences.length}건(근거 없음/미확인 출처라 심사메모에서 자동 제외됨)
        </div>
      )}
    </Card>
  )
}
