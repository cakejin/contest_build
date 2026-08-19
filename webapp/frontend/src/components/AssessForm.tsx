import type { FormEvent } from 'react'
import type { InputMode, PortfolioListItem, ResolvedRegion } from '../types'
import { Card } from './Card'
import { AddressField } from './AddressField'
import { PortfolioPicker } from './PortfolioPicker'

interface AssessFormProps {
  inputMode: InputMode
  address: string
  collateralValue: string
  floorType: string
  floorNo: string
  detectedRegion: ResolvedRegion | null
  queryDate: string
  submitting: boolean
  onInputModeChange: (mode: InputMode) => void
  onAddressChange: (value: string) => void
  onPortfolioSelect: (item: PortfolioListItem) => void
  onRegionResolved: (region: ResolvedRegion | null) => void
  onCollateralValueChange: (value: string) => void
  onFloorTypeChange: (value: string) => void
  onFloorNoChange: (value: string) => void
  onQueryDateChange: (value: string) => void
  onSubmit: () => void
}

const labelClass = 'block text-xs font-semibold text-muted mt-3.5 mb-1.5 tracking-wide'
const inputClass =
  'w-full py-2.5 px-3 border border-border rounded-control text-[13px] [font-family:inherit] text-ink bg-surface transition-[border-color,box-shadow] duration-150 ease-out focus:outline-none focus:border-accent focus:shadow-[0_0_0_3px_rgba(0,168,143,0.16)]'

function RegionStatus({ detectedRegion }: { detectedRegion: ResolvedRegion | null }) {
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
      {detectedRegion.curated_replay && (
        <span className="ml-1">— 💡 {detectedRegion.curated_replay.label} 관련 날짜를 조회해보세요</span>
      )}
      {!detectedRegion.curated_replay && !detectedRegion.live_supported && (
        <span className="ml-1">— 특보 연동 대상 지역이 아니에요</span>
      )}
    </div>
  )
}

const tabButtonClass = (active: boolean) =>
  `flex-1 py-2 px-3 text-[13px] font-semibold rounded-control border transition-colors duration-150 ease-out cursor-pointer ${
    active
      ? 'bg-accent text-white border-accent'
      : 'bg-surface text-muted border-border hover:bg-surface-alt'
  }`

export function AssessForm({
  inputMode,
  address,
  collateralValue,
  floorType,
  floorNo,
  detectedRegion,
  queryDate,
  submitting,
  onInputModeChange,
  onAddressChange,
  onPortfolioSelect,
  onRegionResolved,
  onCollateralValueChange,
  onFloorTypeChange,
  onFloorNoChange,
  onQueryDateChange,
  onSubmit,
}: AssessFormProps) {
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <Card icon="result" title="담보 평가">
      <form onSubmit={handleSubmit}>
        <div className="flex gap-2">
          <button
            type="button"
            className={tabButtonClass(inputMode === 'new')}
            onClick={() => onInputModeChange('new')}
          >
            신규 담보 조회
          </button>
          <button
            type="button"
            className={tabButtonClass(inputMode === 'portfolio')}
            onClick={() => onInputModeChange('portfolio')}
          >
            기존 포트폴리오 조회
          </button>
        </div>

        <label htmlFor="address" className={labelClass}>
          {inputMode === 'new' ? '담보 도로명주소' : '기존 담보(포트폴리오 316건 중 선택)'}
        </label>
        {inputMode === 'new' ? (
          <AddressField
            value={address}
            inputClassName={inputClass}
            onChange={onAddressChange}
            onRegionResolved={onRegionResolved}
          />
        ) : (
          <PortfolioPicker
            inputClassName={inputClass}
            onSelect={onPortfolioSelect}
            onRegionResolved={onRegionResolved}
          />
        )}
        <RegionStatus detectedRegion={detectedRegion} />

        <label htmlFor="query-date" className={labelClass}>
          조회 날짜(선택 — 비워두면 지금 시점 특보를 조회해요)
        </label>
        <input
          id="query-date"
          type="date"
          className={inputClass}
          value={queryDate}
          onChange={(e) => onQueryDateChange(e.target.value)}
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
