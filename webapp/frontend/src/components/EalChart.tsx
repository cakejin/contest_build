import { useMemo, useState } from 'react'
import type { EalBin, EalChartMode } from '../types'
import { fmtWon } from '../lib/format'

const EAL_RAMPS = ['bg-ramp-1', 'bg-ramp-2', 'bg-ramp-3', 'bg-ramp-4', 'bg-ramp-5']

const MODE_OPTIONS: { mode: EalChartMode; label: string }[] = [
  { mode: 'severity', label: '손실 발생 구간만' },
  { mode: 'log', label: '전체(로그 스케일)' },
  { mode: 'linear', label: '전체(선형, 원본)' },
]

function rampClass(bin: EalBin, lastBinEnd: number): string {
  const idx = Math.min(4, Math.floor((bin.bin_end / lastBinEnd) * 5))
  return EAL_RAMPS[idx]
}

function EalBar({ bin, heightPct, lastBinEnd }: { bin: EalBin; heightPct: number; lastBinEnd: number }) {
  return (
    <div
      className={`flex-1 max-w-6 rounded-t-[5px] min-h-px relative ${rampClass(bin, lastBinEnd)}`}
      style={{ height: `${heightPct}%` }}
      title={`${fmtWon(bin.bin_start)} ~ ${fmtWon(bin.bin_end)}: ${bin.count}회`}
    />
  )
}

/* EAL 히스토그램 — 세 가지 보기를 토글로 비교할 수 있게 한다(2026-08-12, 사용자 피드백:
   "0원 구간이 99%대라 나머지가 안 보인다"). 세 보기 전부 같은 원본 20-bin 데이터를 다르게
   변형할 뿐 — 새 계산은 없다. */
export function EalChart({ bins }: { bins: EalBin[] | null | undefined }) {
  const [mode, setMode] = useState<EalChartMode>('severity')

  const validBins = bins && bins.length ? bins : null

  const renderedBars = useMemo(() => {
    if (!validBins) return []
    const lastBinEnd = validBins[validBins.length - 1].bin_end

    if (mode === 'severity') {
      const tail = validBins.slice(1)
      const maxCount = Math.max(0, ...tail.map((b) => b.count))
      return tail.map((b) => ({ bin: b, heightPct: maxCount > 0 ? (b.count / maxCount) * 100 : 0, lastBinEnd }))
    }
    if (mode === 'log') {
      const maxLog = Math.max(...validBins.map((b) => Math.log10(b.count + 1)))
      return validBins.map((b) => ({
        bin: b,
        heightPct: maxLog > 0 ? (Math.log10(b.count + 1) / maxLog) * 100 : 0,
        lastBinEnd,
      }))
    }
    const maxCount = Math.max(...validBins.map((b) => b.count))
    return validBins.map((b) => ({ bin: b, heightPct: maxCount > 0 ? (b.count / maxCount) * 100 : 0, lastBinEnd }))
  }, [validBins, mode])

  if (!validBins) {
    return <p className="text-muted text-xs">분포를 산출하지 못했어요(입력 데이터 불충분).</p>
  }

  const total = validBins.reduce((sum, b) => sum + b.count, 0)
  const noLoss = validBins[0].count
  const noLossPct = total > 0 ? ((noLoss / total) * 100).toFixed(1) : '0.0'
  const rangeStart = mode === 'severity' ? (validBins[1]?.bin_start ?? 0) : 0
  const rangeEnd = validBins[validBins.length - 1].bin_end

  return (
    <>
      <div className="flex gap-1 bg-surface-alt rounded-[10px] p-1 mt-3 mb-1">
        {MODE_OPTIONS.map((opt) => (
          <button
            key={opt.mode}
            type="button"
            onClick={() => setMode(opt.mode)}
            className={`flex-1 w-auto m-0 py-[7px] px-2 text-[11px] font-semibold rounded-[7px] shadow-none transition-none ${
              mode === opt.mode ? 'bg-surface text-title shadow-[0_1px_4px_rgba(0,0,0,0.14)]' : 'bg-transparent text-muted hover:bg-white/60'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="flex items-end gap-0.5 h-[140px] mt-3 border-b border-border pb-0.5">
        {renderedBars.map(({ bin, heightPct, lastBinEnd }, i) => (
          <EalBar key={i} bin={bin} heightPct={heightPct} lastBinEnd={lastBinEnd} />
        ))}
      </div>
      <div className="text-[11px] text-muted mt-1.5 flex justify-between">
        <span>{fmtWon(rangeStart)}</span>
        <span>{fmtWon(rangeEnd)}</span>
      </div>

      {mode === 'severity' && (
        <p className="text-muted text-xs">
          {noLoss.toLocaleString()}회({noLossPct}%)는 손실 없음(0원 구간, 표에서 제외) — 아래는{' '}
          <strong>손실이 발생한 {(total - noLoss).toLocaleString()}회만</strong>의 분포입니다.
        </p>
      )}
      {mode === 'log' && (
        <p className="text-muted text-xs">
          ⚠ 로그 스케일 — 막대 높이가 실제 발생 비율에 비례하지 않습니다(0원 구간이 {noLossPct}%라 압축해서 표시). 정확한 비율은 막대에
          마우스를 올려 확인하세요.
        </p>
      )}
      {mode === 'linear' && (
        <p className="text-muted text-xs">
          0원 구간이 전체의 {noLossPct}%({noLoss.toLocaleString()}회)를 차지해 나머지 구간이 잘 안 보일 수 있어요.
        </p>
      )}
    </>
  )
}
