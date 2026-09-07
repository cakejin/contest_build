import { useEffect, useRef, useState } from 'react'
import { Header } from './components/Header'
import { AssessForm } from './components/AssessForm'
import { ProgressList } from './components/ProgressList'
import { ResultSection } from './components/ResultSection'
import { fetchRegionPresets, startAssessStream } from './api'
import type { AssessResult, InputMode, PartialResult, PortfolioListItem, ProgressItem, QueryMode, RegionPreset, ResolvedRegion, SubmittedMeta } from './types'

function App() {
  // 2026-08-19(계속, DEV_LOG.md 참조) — "신규 담보 조회"(자유입력)와 "기존 포트폴리오
  // 조회"(316건 중 선택)를 명확히 분리한 2탭 구조. 이전엔 주소창이 우리 316건 데이터와
  // 연결되는지 안 되는지 화면에서 구분이 안 돼 혼란이 있었다.
  const [inputMode, setInputMode] = useState<InputMode>('new')
  const [address, setAddress] = useState('')
  // 근거 없는 예시 숫자(5억)를 기본값으로 박아두지 않는다(DEV_LOG.md 2026-08-19 참조) —
  // "신규 담보 조회"는 빈 칸으로 시작해 사용자가 직접 입력하도록 강제하고, "기존
  // 포트폴리오 조회"는 선택한 레코드의 실제 담보가액으로 채워진다.
  const [collateralValue, setCollateralValue] = useState('')
  const [floorType, setFloorType] = useState('')
  const [floorNo, setFloorNo] = useState('')
  // HANDOVER 논의(DEV_LOG.md 2026-08-18) — region_code는 더 이상 프리셋에서 오지
  // 않는다. AddressField/PortfolioPicker가 입력·선택된 주소를 감지해 여기로 알려주면,
  // 그 감지 결과가 /api/assess로 보낼 region_code의 유일한 출처다(담보 평가↔포트폴리오
  // 알림 불일치 버그의 근본 수정).
  const [detectedRegion, setDetectedRegion] = useState<ResolvedRegion | null>(null)
  // "기존 포트폴리오 조회"에서 고른 담보ID — 결과 대시보드 상단에 명시하기 위한 용도로만
  // 쓴다("신규 담보 조회"는 애초에 포트폴리오 담보ID가 없으니 null).
  const [selectedCollateralId, setSelectedCollateralId] = useState<string | null>(null)
  const [submittedMeta, setSubmittedMeta] = useState<SubmittedMeta | null>(null)
  // 2026-08-19(계속, DEV_LOG.md 참조) — "리플레이/라이브/특정날짜" 3택 드롭다운은
  // 사용자 피드백으로 제거했다. 날짜 하나만 있으면 그 날짜의 과거 특보를, 비우면
  // 지금 시점 라이브 특보를 보여준다 — mode 판단은 백엔드가 이 값 유무로 알아서 한다.
  const [queryDate, setQueryDate] = useState('')
  // 2026-09-08 — 조회 기준을 두 버튼으로 드러냈다(UX 점검: "조회 날짜" 한 칸에 두 모드가 숨어 있었음).
  const [queryMode, setQueryMode] = useState<QueryMode>('live')
  const [presets, setPresets] = useState<RegionPreset[]>([])
  const [progressItems, setProgressItems] = useState<ProgressItem[]>([])
  const [result, setResult] = useState<AssessResult | null>(null)
  // 2026-09-07(멘토 피드백 1) — 단계별 부분 결과. SSE `partial` 이벤트가 오는 대로 채워지고,
  // 최종 `result`가 오면 그쪽이 화면의 원천이 된다(값은 동일 — 부분 결과는 먼저 보여주기용).
  const [partial, setPartial] = useState<PartialResult>({})
  const [loading, setLoading] = useState(false)
  const [connectionError, setConnectionError] = useState(false)
  const closeStreamRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    // 2026-09-08 — 첫 화면에 주소를 미리 채우지 않는다(UX 점검: 예시인지 입력값인지 구분이 안 됐음).
    // 프리셋은 "예시 주소 넣기" 링크와 "과거 사건 재현" 사건 칩에만 쓴다.
    fetchRegionPresets().then(setPresets)
    return () => closeStreamRef.current?.()
  }, [])

  const handleFillSampleAddress = () => {
    const first = presets[0]
    if (first) setAddress(first.sample_address)
  }

  const handleQueryModeChange = (mode: QueryMode) => {
    setQueryMode(mode)
    if (mode === 'live') setQueryDate('')
  }

  // 사건 칩: 날짜를 채우고, 주소가 비어 있으면 그 사건 지역의 예시 주소도 함께 채운다.
  const handleEventChip = (preset: RegionPreset) => {
    if (!preset.sample_date) return
    setQueryMode('historical')
    setQueryDate(preset.sample_date)
    if (inputMode === 'new' && !address.trim()) setAddress(preset.sample_address)
  }

  const handleInputModeChange = (mode: InputMode) => {
    setInputMode(mode)
    // 탭을 바꾸면 이전 탭의 선택/입력이 새 탭으로 잘못 넘어가지 않도록 초기화한다.
    setAddress('')
    setCollateralValue('')
    setDetectedRegion(null)
    setSelectedCollateralId(null)
  }

  const handlePortfolioSelect = (item: PortfolioListItem) => {
    setAddress(item.address)
    setCollateralValue(String(item.collateral_value))
    setSelectedCollateralId(item.collateral_id)
  }

  const handleSubmit = () => {
    if (queryMode === 'historical' && !queryDate) return
    closeStreamRef.current?.()

    setLoading(true)
    setConnectionError(false)
    setResult(null)
    setPartial({})
    setProgressItems([])
    setSubmittedMeta({
      address,
      collateralId: inputMode === 'portfolio' ? selectedCollateralId : null,
      queryDate,
    })

    closeStreamRef.current = startAssessStream(
      {
        address,
        collateralValue,
        regionCode: detectedRegion?.region_code || '',
        floorType: floorType || null,
        floorNo: floorType ? floorNo || null : null,
        queryDate: queryDate || null,
      },
      {
        onProgress: (payload) => {
          setProgressItems((prev) => [
            ...prev.map((it) => (it.status === 'active' ? { ...it, status: 'done' as const } : it)),
            { message: payload.message, status: 'active' as const },
          ])
        },
        onPartial: ({ stage, data }) => {
          setPartial((prev) => {
            switch (stage) {
              case 'advisory':
                return { ...prev, advisory: data as PartialResult['advisory'] }
              case 'geocode':
                return { ...prev, geocoded: data as PartialResult['geocoded'] }
              case 'flood': {
                // data.flood는 FloodAgentOutput 전체(asdict) — 최종 result.flood와 같은 형태(FloodData)다.
                const d = data as { flood: PartialResult['flood']; coverage_label: string | null }
                return { ...prev, flood: d.flood, coverage_label: d.coverage_label ?? undefined }
              }
              case 'building':
                return { ...prev, building: data as PartialResult['building'] }
              case 'scenario':
                return { ...prev, scenario: data as PartialResult['scenario'] }
              case 'memo':
                return { ...prev, memo: data as PartialResult['memo'] }
              case 'portfolio':
                return { ...prev, portfolio_batch: data as PartialResult['portfolio_batch'] }
              default:
                return prev
            }
          })
        },
        onResult: (data) => {
          setProgressItems((prev) => prev.map((it) => (it.status === 'active' ? { ...it, status: 'done' as const } : it)))
          setResult(data)
          setLoading(false)
        },
        onError: () => {
          setConnectionError(true)
          setLoading(false)
        },
      },
    )
  }

  return (
    <>
      <Header />
      <main className="max-w-[1120px] mx-auto pt-7 px-5 pb-[72px] grid grid-cols-[380px_1fr] max-[860px]:grid-cols-1 gap-6 items-start">
        <section>
          <AssessForm
            inputMode={inputMode}
            address={address}
            collateralValue={collateralValue}
            floorType={floorType}
            floorNo={floorNo}
            detectedRegion={detectedRegion}
            queryMode={queryMode}
            queryDate={queryDate}
            presets={presets}
            submitting={loading}
            onInputModeChange={handleInputModeChange}
            onAddressChange={setAddress}
            onFillSampleAddress={handleFillSampleAddress}
            onPortfolioSelect={handlePortfolioSelect}
            onRegionResolved={setDetectedRegion}
            onCollateralValueChange={setCollateralValue}
            onFloorTypeChange={setFloorType}
            onFloorNoChange={setFloorNo}
            onQueryModeChange={handleQueryModeChange}
            onQueryDateChange={setQueryDate}
            onEventChip={handleEventChip}
            onSubmit={handleSubmit}
          />
          <ProgressList items={progressItems} />
        </section>

        <section>
          {connectionError && !result ? (
            <div className="bg-surface border border-border/50 rounded-card shadow-card py-[22px] px-6 mb-5">
              <div className="bg-[#fdecea] text-[#8a1f12] rounded-[10px] py-3.5 px-4 text-[13px]">
                서버 연결이 끊겼어요. 다시 시도해 주세요.
              </div>
            </div>
          ) : (
            <ResultSection result={result} partial={partial} loading={loading} meta={submittedMeta} />
          )}
        </section>
      </main>
    </>
  )
}

export default App
