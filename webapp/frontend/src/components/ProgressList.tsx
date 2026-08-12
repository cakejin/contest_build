import type { ProgressItem } from '../types'
import { Card } from './Card'

export function ProgressList({ items }: { items: ProgressItem[] }) {
  return (
    <Card icon="chart" title="진행상황">
      {items.length === 0 ? (
        <p className="text-muted text-xs m-0">평가를 실행하면 실제 처리 단계가 여기에 표시됩니다.</p>
      ) : (
        <ul className="list-none m-0 p-0 relative before:content-[''] before:absolute before:left-[3px] before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
          {items.map((item, i) => (
            <li
              key={i}
              className={`relative flex items-center gap-2.5 py-2 pl-[22px] text-[13px] ${
                item.status === 'active' || item.status === 'done' ? 'text-ink' : 'text-muted'
              } ${item.status === 'active' ? 'font-semibold' : ''}`}
            >
              <span
                className={`absolute left-0 w-2 h-2 rounded-full flex-none shadow-[0_0_0_3px_var(--color-surface)] ${
                  item.status === 'active'
                    ? 'bg-accent animate-pulse-dot'
                    : item.status === 'done'
                      ? 'bg-title'
                      : 'bg-border'
                }`}
              />
              <span>{item.message}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
