import { useEffect, useRef, useState } from 'react'
import { Header } from './components/Header'
import { AssessForm } from './components/AssessForm'
import { ProgressList } from './components/ProgressList'
import { ResultSection } from './components/ResultSection'
import { fetchRegionPresets, startAssessStream } from './api'
import type { AssessResult, InputMode, PortfolioListItem, ProgressItem, ResolvedRegion } from './types'

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
  // 2026-08-19(계속, DEV_LOG.md 참조) — "리플레이/라이브/특정날짜" 3택 드롭다운은
  // 사용자 피드백으로 제거했다. 날짜 하나만 있으면 그 날짜의 과거 특보를, 비우면
  // 지금 시점 라이브 특보를 보여준다 — mode 판단은 백엔드가 이 값 유무로 알아서 한다.
  const [queryDate, setQueryDate] = useState('')
  const [progressItems, setProgressItems] = useState<ProgressItem[]>([])
  const [result, setResult] = useState<AssessResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [connectionError, setConnectionError] = useState(false)
  const closeStreamRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    // "예시 주소로 채우기" 드롭다운은 제거했다(사용자 요청, DEV_LOG.md 2026-08-19 참조) —
    // 대신 첫 로딩 시 힌남노 프리셋(포항 남구) 샘플 주소로 조용히 초기값만 채워둔다.
    fetchRegionPresets().then((data) => {
      if (data.length > 0) setAddress(data[0].sample_address)
    })
    return () => closeStreamRef.current?.()
  }, [])

  const handleInputModeChange = (mode: InputMode) => {
    setInputMode(mode)
    // 탭을 바꾸면 이전 탭의 선택/입력이 새 탭으로 잘못 넘어가지 않도록 초기화한다.
    setAddress('')
    setCollateralValue('')
    setDetectedRegion(null)
  }

  const handlePortfolioSelect = (item: PortfolioListItem) => {
    setAddress(item.address)
    setCollateralValue(String(item.collateral_value))
  }

  const handleSubmit = () => {
    closeStreamRef.current?.()

    setLoading(true)
    setConnectionError(false)
    setResult(null)
    setProgressItems([])

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
            queryDate={queryDate}
            submitting={loading}
            onInputModeChange={handleInputModeChange}
            onAddressChange={setAddress}
            onPortfolioSelect={handlePortfolioSelect}
            onRegionResolved={setDetectedRegion}
            onCollateralValueChange={setCollateralValue}
            onFloorTypeChange={setFloorType}
            onFloorNoChange={setFloorNo}
            onQueryDateChange={setQueryDate}
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
            <ResultSection result={result} loading={loading} />
          )}
        </section>
      </main>
    </>
  )
}

export default App
