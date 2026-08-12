import type { FormEvent } from 'react'
import type { RegionPreset } from '../types'
import { Card } from './Card'

interface AssessFormProps {
  presets: RegionPreset[]
  presetIndex: number
  address: string
  collateralValue: string
  submitting: boolean
  onPresetChange: (index: number) => void
  onAddressChange: (value: string) => void
  onCollateralValueChange: (value: string) => void
  onSubmit: () => void
}

const labelClass = 'block text-xs font-semibold text-muted mt-3.5 mb-1.5 tracking-wide'
const inputClass =
  'w-full py-2.5 px-3 border border-border rounded-control text-[13px] [font-family:inherit] text-ink bg-surface transition-[border-color,box-shadow] duration-150 ease-out focus:outline-none focus:border-accent focus:shadow-[0_0_0_3px_rgba(0,168,143,0.16)]'

export function AssessForm({
  presets,
  presetIndex,
  address,
  collateralValue,
  submitting,
  onPresetChange,
  onAddressChange,
  onCollateralValueChange,
  onSubmit,
}: AssessFormProps) {
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <Card icon="result" title="담보 평가">
      <form onSubmit={handleSubmit}>
        <label htmlFor="preset" className={labelClass}>
          지역 프리셋
        </label>
        <select
          id="preset"
          className={inputClass}
          value={presetIndex}
          onChange={(e) => onPresetChange(Number(e.target.value))}
        >
          {presets.map((p, i) => (
            <option key={p.id} value={i}>
              {p.label}
            </option>
          ))}
        </select>

        <label htmlFor="address" className={labelClass}>
          담보 도로명주소
        </label>
        <input
          id="address"
          type="text"
          required
          placeholder="예: 경상북도 포항시 남구 인덕로 27"
          className={inputClass}
          value={address}
          onChange={(e) => onAddressChange(e.target.value)}
        />

        <label htmlFor="collateral-value" className={labelClass}>
          담보가액(원)
        </label>
        <input
          id="collateral-value"
          type="number"
          required
          step={1000000}
          className={inputClass}
          value={collateralValue}
          onChange={(e) => onCollateralValueChange(e.target.value)}
        />

        <button
          type="submit"
          disabled={submitting}
          className="mt-[18px] w-full bg-accent text-white border-none rounded-control py-3 px-3.5 text-sm font-bold cursor-pointer shadow-[0_6px_16px_-6px_rgba(0,168,143,0.55)] transition-[background,transform,box-shadow] duration-150 ease-out enabled:hover:bg-title enabled:hover:-translate-y-px enabled:hover:shadow-[0_10px_20px_-8px_rgba(0,127,108,0.5)] enabled:active:translate-y-0 disabled:bg-border disabled:shadow-none disabled:cursor-not-allowed"
        >
          {submitting ? '평가 실행 중...' : '평가 실행'}
        </button>
      </form>
    </Card>
  )
}
