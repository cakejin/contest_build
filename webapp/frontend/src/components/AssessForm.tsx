import { useState } from 'react'
import type { FormEvent } from 'react'
import type { InputMode, PortfolioListItem, QueryMode, RegionPreset, ResolvedRegion } from '../types'
import { LineIcon } from './Icons'
import { AddressField } from './AddressField'
import { PortfolioPicker } from './PortfolioPicker'

interface AssessFormProps {
  inputMode: InputMode
  address: string
  collateralValue: string
  floorType: string
  floorNo: string
  detectedRegion: ResolvedRegion | null
  queryMode: QueryMode
  queryDate: string
  presets: RegionPreset[]
  submitting: boolean
  onInputModeChange: (mode: InputMode) => void
  onAddressChange: (value: string) => void
  onFillSampleAddress: () => void
  onPortfolioSelect: (item: PortfolioListItem) => void
  onRegionResolved: (region: ResolvedRegion | null) => void
  onCollateralValueChange: (value: string) => void
  onFloorTypeChange: (value: string) => void
  onFloorNoChange: (value: string) => void
  onQueryModeChange: (mode: QueryMode) => void
  onQueryDateChange: (value: string) => void
  onEventChip: (preset: RegionPreset) => void
  onSubmit: () => void
  /** 가운데 결과 상자와 같은 높이(px). 없으면 내용 높이(좁은 화면 세로 스택). */
  height?: number
}

// 2026-09-08 — 입력 폼 수정(UX 점검 반영, 디자인 캔버스 4p): 라벨에 1·2·3 순서 번호, 내부 문서
// 참조(HANDOVER §⑧ 등) 문구 제거, 보조 설명은 라벨 오른쪽에 작게.
// 2026-09-08(계속6) — 토스형 3단에서 왼쪽 카드가 가운데 결과 상자보다 항상 길던 문제: 카드 높이를
// 상자와 같게 고정하고(헤더 / 필드 / 바닥 고정 버튼), 필드를 압축 — 신규·기존 토글을 헤더 오른쪽
// 텍스트 탭으로, 과거 사건 재현은 사건 칩이 주 조작이고 날짜 입력은 "직접 입력"을 눌러야 펼침,
// 버튼 아래 소요시간 안내(가운데 빈 상태에 이미 있음)와 두 줄짜리 주소 안내 삭제.
const labelClass = 'flex justify-between items-baseline text-xs font-semibold text-muted mt-3 mb-1.5 tracking-wide'
// 라벨 왼쪽 / 컨트롤 오른쪽 한 줄 행(토스 주문하기 폼 참고) — 담보가액·담보 층처럼 컨트롤이 짧은 항목용
const rowClass = 'flex items-center gap-2 mt-3'
const rowLabelClass = 'w-[64px] flex-none text-xs font-semibold text-muted tracking-wide whitespace-nowrap'
const inputClass =
  'w-full py-2 px-3 border border-border rounded-control text-[13px] [font-family:inherit] text-ink bg-surface transition-[border-color,box-shadow] duration-150 ease-out focus:outline-none focus:border-accent focus:shadow-[0_0_0_3px_rgba(0,168,143,0.16)]'

function StepNo({ n }: { n: number }) {
  return <span className="text-title mr-1">{n}</span>
}

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
      {!detectedRegion.curated_replay && !detectedRegion.live_supported && (
        <span className="ml-1">— 특보 연동 대상 지역이 아니에요</span>
      )}
    </div>
  )
}

const modeTabClass = (active: boolean) =>
  `bg-transparent border-0 border-b-2 px-0.5 py-1 text-[11.5px] cursor-pointer whitespace-nowrap transition-colors ${
    active ? 'border-title text-ink font-bold' : 'border-transparent text-muted font-semibold hover:text-ink'
  }`

/** 세그먼트 컨트롤 — OS 네이티브 <select> 대신 쓴다(선택지 2~3개는 드롭다운이 필요 없고,
 * 네이티브 옵션 목록은 OS마다 모양이 달라 화면과 어긋난다 — UX 점검 2026-09-07). */
function Segmented<T extends string>({
  value,
  options,
  onChange,
  name,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  name: string
}) {
  return (
    <div role="radiogroup" aria-label={name} className="flex border border-border rounded-control overflow-hidden bg-surface">
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={`flex-1 py-[7px] px-1.5 text-[12.5px] font-semibold whitespace-nowrap border-r border-border last:border-r-0 transition-colors duration-150 cursor-pointer ${
              active ? 'bg-title text-white' : 'bg-surface text-muted hover:bg-surface-alt'
            }`}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

function fmtEok(value: string): string | null {
  const n = Number(value)
  if (!value || !Number.isFinite(n) || n <= 0) return null
  if (n >= 1e8) {
    const eok = n / 1e8
    return `= ${Number.isInteger(eok) ? eok : eok.toFixed(1)}억원`
  }
  if (n >= 1e4) return `= ${Math.round(n / 1e4).toLocaleString('ko-KR')}만원`
  return null
}

export function AssessForm({
  inputMode,
  address,
  collateralValue,
  floorType,
  floorNo,
  detectedRegion,
  queryMode,
  queryDate,
  presets,
  submitting,
  onInputModeChange,
  onAddressChange,
  onFillSampleAddress,
  onPortfolioSelect,
  onRegionResolved,
  onCollateralValueChange,
  onFloorTypeChange,
  onFloorNoChange,
  onQueryModeChange,
  onQueryDateChange,
  onEventChip,
  onSubmit,
  height,
}: AssessFormProps) {
  // 날짜 직접 입력란은 접어 두고, 사건 칩과 안 맞는 날짜가 이미 들어 있으면 펼친 채로 시작
  const [showDateInput, setShowDateInput] = useState(false)
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  const eventChips = presets.filter((p) => p.sample_date)
  const eokLabel = fmtEok(collateralValue)
  const historicalNeedsDate = queryMode === 'historical' && !queryDate
  const dateMatchesChip = eventChips.some((p) => p.sample_date === queryDate)
  const dateInputOpen = showDateInput || (!!queryDate && !dateMatchesChip)

  return (
    <div
      style={height ? { height } : undefined}
      className="bg-surface border border-border/50 rounded-card shadow-card px-6 pt-4 pb-5 flex flex-col"
    >
      <div className="flex items-center gap-2 pb-2.5 mb-1 border-b border-surface-alt flex-none">
        <span className="flex-none w-7 h-7 rounded-[9px] bg-gradient-to-br from-accent-soft to-white border border-accent/20 text-title flex items-center justify-center">
          <LineIcon icon="result" className="w-4 h-4" />
        </span>
        <h2 className="text-[15px] font-bold m-0 text-ink tracking-tight whitespace-nowrap">담보 평가</h2>
        <div className="ml-auto flex gap-2" role="tablist" aria-label="입력 방식">
          <button type="button" role="tab" aria-selected={inputMode === 'new'} className={modeTabClass(inputMode === 'new')} onClick={() => onInputModeChange('new')}>
            신규 담보
          </button>
          <button type="button" role="tab" aria-selected={inputMode === 'portfolio'} className={modeTabClass(inputMode === 'portfolio')} onClick={() => onInputModeChange('portfolio')}>
            기존 포트폴리오
          </button>
        </div>
      </div>
      <form onSubmit={handleSubmit} className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1">

        <label htmlFor="address" className={labelClass}>
          <span>
            <StepNo n={1} />
            {inputMode === 'new' ? '담보 도로명주소' : '기존 담보(포트폴리오 470건 중 선택)'}
          </span>
          {inputMode === 'new' && (
            <button type="button" onClick={onFillSampleAddress} className="text-[11px] font-semibold text-title hover:underline cursor-pointer bg-transparent border-0 p-0">
              예시 주소 넣기
            </button>
          )}
        </label>
        {inputMode === 'new' ? (
          <AddressField value={address} inputClassName={inputClass} onChange={onAddressChange} onRegionResolved={onRegionResolved} />
        ) : (
          <PortfolioPicker inputClassName={inputClass} onSelect={onPortfolioSelect} onRegionResolved={onRegionResolved} />
        )}
        {inputMode === 'new' && !detectedRegion && (
          <p className="text-[11px] text-muted/80 mt-1.5 truncate">대구·포항·거제 커버리지 · 지역은 자동 감지</p>
        )}
        <RegionStatus detectedRegion={detectedRegion} />

        <div className={labelClass}>
          <span>
            <StepNo n={2} />
            조회 기준
          </span>
          <span className="font-normal text-[11px] text-muted/80">특보를 어느 시점으로 볼지</span>
        </div>
        <Segmented<QueryMode>
          name="조회 기준"
          value={queryMode}
          options={[
            { value: 'live', label: '지금 시점 특보' },
            { value: 'historical', label: '과거 사건 재현' },
          ]}
          onChange={onQueryModeChange}
        />
        {queryMode === 'historical' && (
          <>
            {eventChips.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {eventChips.map((p) => {
                  const active = queryDate === p.sample_date
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => onEventChip(p)}
                      className={`inline-flex items-center rounded-full py-1 px-2.5 text-[11.5px] font-semibold border cursor-pointer transition-colors ${
                        active ? 'bg-title text-white border-title' : 'bg-accent-soft/60 text-title border-accent-soft hover:bg-accent-soft'
                      }`}
                    >
                      {p.chip_label ?? p.label}
                    </button>
                  )
                })}
              </div>
            )}
            {dateInputOpen ? (
              <input
                id="query-date"
                type="date"
                className={`${inputClass} mt-2`}
                value={queryDate}
                onChange={(e) => onQueryDateChange(e.target.value)}
                aria-label="조회 날짜"
              />
            ) : (
              <p className="text-[11px] text-muted mt-1.5 mb-0 flex justify-between">
                <span>{historicalNeedsDate ? '사건 칩을 고르세요' : `조회일 ${queryDate}`}</span>
                <button type="button" onClick={() => setShowDateInput(true)} className="bg-transparent border-0 p-0 text-[11px] font-semibold text-title hover:underline cursor-pointer">
                  날짜 직접 입력
                </button>
              </p>
            )}
          </>
        )}

        <div className={rowClass}>
          <label htmlFor="collateral-value" className={rowLabelClass}>
            <StepNo n={3} />
            담보가액
          </label>
          <div className="relative flex-1 min-w-0">
            <input
              id="collateral-value"
              type="number"
              required
              step={1000000}
              placeholder="원 단위"
              className={`${inputClass} ${eokLabel ? 'pr-20' : ''}`}
              value={collateralValue}
              onChange={(e) => onCollateralValueChange(e.target.value)}
            />
            {eokLabel && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-muted pointer-events-none">{eokLabel}</span>}
          </div>
        </div>

        <div className={rowClass}>
          <span className={rowLabelClass} title="선택 — 층별 침수 노출 계산에 씁니다">
            담보 층
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex gap-1.5 items-stretch">
              <div className="flex-1 min-w-0">
                <Segmented<string>
                  name="담보 층 구분"
                  value={floorType}
                  options={[
                    { value: '', label: '미입력' },
                    { value: '지상', label: '지상' },
                    { value: '지하', label: '지하' },
                  ]}
                  onChange={onFloorTypeChange}
                />
              </div>
              <input
                id="floor-no"
                type="number"
                min={1}
                placeholder="층수"
                aria-label="층수"
                disabled={!floorType}
                className={`${inputClass} flex-none max-w-[66px] px-2 disabled:bg-surface-alt disabled:cursor-not-allowed`}
                value={floorNo}
                onChange={(e) => onFloorNoChange(e.target.value)}
              />
            </div>
          </div>
        </div>

        </div>
        <button
          type="submit"
          disabled={submitting || historicalNeedsDate}
          className="mt-4 flex-none w-full bg-accent text-white border-none rounded-control py-3 px-3.5 text-sm font-bold cursor-pointer shadow-[0_6px_16px_-6px_rgba(0,168,143,0.55)] transition-[background,transform,box-shadow] duration-150 ease-out enabled:hover:bg-title enabled:hover:-translate-y-px enabled:hover:shadow-[0_10px_20px_-8px_rgba(0,127,108,0.5)] enabled:active:translate-y-0 disabled:bg-border disabled:shadow-none disabled:cursor-not-allowed"
        >
          {submitting ? '평가 실행 중...' : '평가 실행'}
        </button>
      </form>
    </div>
  )
}
