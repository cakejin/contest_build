import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Header } from './components/Header'
import { AssessForm } from './components/AssessForm'
import { ProgressList } from './components/ProgressList'
import { LineIcon } from './components/Icons'
import { STAGE_SHORT } from './lib/stages'
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
  // 2026-09-08 — 토스형 3단 레이아웃(디자인 캔버스 12p 3안): 양쪽 열은 sticky, 가운데 결과 상자만
  // 내부 스크롤. 상자 높이 = 화면 높이 − 헤더 아래 여백. 900px 미만에서는 세로 스택 + 높이 자동.
  // 2026-09-08(계속7) — 토스증권처럼 900~1199px에서는 오른쪽 진행상황 열을 56px 아이콘 레일로 접고,
  // 아이콘을 누르면 결과 상자 위에 패널이 겹쳐 열린다(가운데를 더 좁히지 않기 위해 밀지 않고 덮음).
  const headerRef = useRef<HTMLDivElement | null>(null)
  const [boxHeight, setBoxHeight] = useState<number | undefined>(undefined)
  const [railMode, setRailMode] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  useLayoutEffect(() => {
    const measure = () => {
      const wide = window.matchMedia('(min-width: 900px)').matches
      setRailMode(wide && !window.matchMedia('(min-width: 1200px)').matches)
      if (!wide) {
        setBoxHeight(undefined)
        return
      }
      const bottom = headerRef.current?.getBoundingClientRect().bottom ?? 0
      // 2026-09-09 — 위 여백 24 + 아래 여백 16 + 하단 출처 줄 32 + 여유 8
      setBoxHeight(Math.max(480, window.innerHeight - bottom - 80))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

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
      collateralValue: Number(collateralValue) > 0 ? Number(collateralValue) : null,
      floorType: floorType || null,
      floorNo: floorType ? floorNo || null : null,
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
            { stage: payload.stage, message: payload.message, status: 'active' as const },
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
                const d = data as {
                  flood: PartialResult['flood']
                  coverage_label: string | null
                  flood_depth_class?: PartialResult['flood_depth_class']
                  flood_marks?: PartialResult['flood_marks']
                }
                return {
                  ...prev,
                  flood: d.flood,
                  coverage_label: d.coverage_label ?? undefined,
                  flood_depth_class: d.flood_depth_class ?? null,
                  flood_marks: d.flood_marks ?? null,
                }
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
      <div ref={headerRef}>
        <Header />
      </div>
      <main className="max-w-[1600px] mx-auto pt-6 px-8 pb-4 grid grid-cols-1 min-[900px]:grid-cols-[300px_minmax(0,1fr)_56px] min-[1200px]:grid-cols-[320px_minmax(0,1fr)_240px] gap-8 items-start">
        <section className="min-[900px]:sticky min-[900px]:top-5">
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
            height={boxHeight}
          />
        </section>

        <section className="min-w-0">
          {connectionError && !result ? (
            <div className="bg-surface rounded-card py-7 px-8">
              <div className="bg-[#fdecea] text-[#8a1f12] rounded-lg py-3.5 px-4 text-[13px]">
                서버 연결이 끊겼어요. 다시 시도해 주세요.
              </div>
            </div>
          ) : (
            <ResultSection result={result} partial={partial} loading={loading} meta={submittedMeta} boxHeight={boxHeight} />
          )}
        </section>

        <section className="min-[900px]:sticky min-[900px]:top-5 relative z-30">
          {railMode ? (
            <>
              <button
                type="button"
                onClick={() => setRailOpen((v) => !v)}
                aria-expanded={railOpen}
                aria-label="진행상황 열기"
                title="진행상황"
                className="w-14 bg-surface rounded-card py-3 px-0 flex flex-col items-center gap-1.5 cursor-pointer text-muted hover:text-ink border-0"
              >
                <span className="relative w-8 h-8 rounded-full bg-accent-soft text-title flex items-center justify-center">
                  <LineIcon icon="chart" className="w-4 h-4" />
                  {loading && <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-accent animate-pulse-dot shadow-[0_0_0_2px_var(--color-surface)]" />}
                </span>
                <span className="text-[10.5px] font-semibold leading-none">
                  {progressItems.length > 0 ? (STAGE_SHORT[progressItems[progressItems.length - 1].stage] ?? '진행') : '진행'}
                </span>
              </button>
              {railOpen && (
                <div className="absolute top-0 right-0 w-[280px] z-20 bg-surface rounded-card shadow-card-lg py-5 px-6">
                  <button type="button" onClick={() => setRailOpen(false)} aria-label="닫기" className="absolute top-3 right-4 z-10 bg-transparent border-0 text-muted hover:text-ink text-lg leading-none cursor-pointer">
                    ×
                  </button>
                  <ProgressList items={progressItems} timings={result?.timings} />
                </div>
              )}
            </>
          ) : (
            <ProgressList items={progressItems} timings={result?.timings} />
          )}
        </section>
      </main>
      {/* 2026-09-09 — 토스증권처럼 출처·면책은 상단이 아니라 하단 한 줄에. */}
      <footer className="max-w-[1600px] mx-auto px-8 h-8 flex items-center gap-4 text-[11px] text-muted whitespace-nowrap overflow-hidden">
        <span>데이터 출처: 기상청 특보 API · V-World · 건축HUB · 국토부 홍수위험지도</span>
        <span className="ml-auto">AI 기반 참고자료 · 여신 결정 아님</span>
      </footer>
    </>
  )
}

export default App
