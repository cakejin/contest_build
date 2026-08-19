import type { FormEvent } from 'react'
import type { RegionPreset, ResolvedRegion } from '../types'
import { Card } from './Card'
import { AddressField } from './AddressField'

interface AssessFormProps {
  presets: RegionPreset[]
  presetIndex: number
  address: string
  collateralValue: string
  floorType: string
  floorNo: string
  detectedRegion: ResolvedRegion | null
  useReplay: boolean
  submitting: boolean
  onPresetChange: (index: number) => void
  onAddressChange: (value: string) => void
  onRegionResolved: (region: ResolvedRegion | null) => void
  onCollateralValueChange: (value: string) => void
  onFloorTypeChange: (value: string) => void
  onFloorNoChange: (value: string) => void
  onUseReplayChange: (value: boolean) => void
  onSubmit: () => void
}

const labelClass = 'block text-xs font-semibold text-muted mt-3.5 mb-1.5 tracking-wide'
const inputClass =
  'w-full py-2.5 px-3 border border-border rounded-control text-[13px] [font-family:inherit] text-ink bg-surface transition-[border-color,box-shadow] duration-150 ease-out focus:outline-none focus:border-accent focus:shadow-[0_0_0_3px_rgba(0,168,143,0.16)]'

function RegionStatus({
  detectedRegion,
  useReplay,
  onUseReplayChange,
}: {
  detectedRegion: ResolvedRegion | null
  useReplay: boolean
  onUseReplayChange: (value: boolean) => void
}) {
  if (!detectedRegion) return null

  if (!detectedRegion.resolved) {
    return <p className="text-[#8a1f12] text-[11px] mt-1.5">{detectedRegion.reason}</p>
  }

  if (detectedRegion.coverage !== 'IN_SCOPE') {
    return (
      <p className="text-warn-ink text-[11px] mt-1.5">
        커버리지 밖 지역이에요 — 담보 평가는 가능하지만 포트폴리오 재심사 알림·특보 연동 대상은 아니에요.
      </p>
    )
  }

  return (
    <div className="text-[11px] text-muted mt-1.5">
      감지된 지역: <span className="font-semibold text-ink">{detectedRegion.region_name}</span>
      {detectedRegion.curated_replay ? (
        <label className="ml-2 inline-flex items-center gap-1 cursor-pointer">
          <input type="checkbox" checked={useReplay} onChange={(e) => onUseReplayChange(e.target.checked)} />
          {detectedRegion.curated_replay.label}로 재생
        </label>
      ) : detectedRegion.live_supported ? (
        <span className="ml-2">— 과거 재연 데이터가 없어 실시간 특보 조회만 가능해요</span>
      ) : (
        <span className="ml-2">— 특보 연동 대상 지역이 아니에요</span>
      )}
    </div>
  )
}

export function AssessForm({
  presets,
  presetIndex,
  address,
  collateralValue,
  floorType,
  floorNo,
  detectedRegion,
  useReplay,
  submitting,
  onPresetChange,
  onAddressChange,
  onRegionResolved,
  onCollateralValueChange,
  onFloorTypeChange,
  onFloorNoChange,
  onUseReplayChange,
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
          예시 주소로 채우기
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
        <AddressField
          value={address}
          inputClassName={inputClass}
          onChange={onAddressChange}
          onRegionResolved={onRegionResolved}
        />
        <RegionStatus detectedRegion={detectedRegion} useReplay={useReplay} onUseReplayChange={onUseReplayChange} />

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

        <label htmlFor="floor-type" className={labelClass}>
          담보 층수(선택 — HANDOVER §⑧ 층별 리스크 차등화)
        </label>
        <div className="flex gap-2">
          <select
            id="floor-type"
            className={inputClass}
            value={floorType}
            onChange={(e) => onFloorTypeChange(e.target.value)}
          >
            <option value="">미입력(건물 전체 스코어링)</option>
            <option value="지상">지상</option>
            <option value="지하">지하</option>
          </select>
          <input
            id="floor-no"
            type="number"
            min={1}
            placeholder="층수"
            disabled={!floorType}
            className={`${inputClass} max-w-[110px] disabled:bg-surface-alt disabled:cursor-not-allowed`}
            value={floorNo}
            onChange={(e) => onFloorNoChange(e.target.value)}
          />
        </div>

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
