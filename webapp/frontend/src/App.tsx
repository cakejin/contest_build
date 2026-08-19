import { useEffect, useRef, useState } from 'react'
import { Header } from './components/Header'
import { AssessForm } from './components/AssessForm'
import { ProgressList } from './components/ProgressList'
import { ResultSection } from './components/ResultSection'
import { fetchRegionPresets, startAssessStream } from './api'
import type { AssessResult, ProgressItem, RegionPreset, ResolvedRegion } from './types'

function App() {
  const [presets, setPresets] = useState<RegionPreset[]>([])
  const [presetIndex, setPresetIndex] = useState(0)
  const [address, setAddress] = useState('')
  const [collateralValue, setCollateralValue] = useState('500000000')
  const [floorType, setFloorType] = useState('')
  const [floorNo, setFloorNo] = useState('')
  // HANDOVER 논의(DEV_LOG.md 2026-08-18) — region_code/mode/timeline_path는 더 이상
  // 프리셋에서 오지 않는다. AddressField가 입력 주소를 감지해 여기로 알려주면, 그
  // 감지 결과가 /api/assess로 보낼 값의 유일한 출처다(담보 평가↔포트폴리오 알림
  // 불일치 버그의 근본 수정).
  const [detectedRegion, setDetectedRegion] = useState<ResolvedRegion | null>(null)
  const [useReplay, setUseReplay] = useState(true)
  const [progressItems, setProgressItems] = useState<ProgressItem[]>([])
  const [result, setResult] = useState<AssessResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [connectionError, setConnectionError] = useState(false)
  const closeStreamRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    fetchRegionPresets().then((data) => {
      setPresets(data)
      if (data.length > 0) setAddress(data[0].sample_address)
    })
    return () => closeStreamRef.current?.()
  }, [])

  useEffect(() => {
    // 새로 감지된 지역에 큐레이션 리플레이가 있으면 기본으로 재생을 켜고, 없으면
    // (라이브만 가능하거나 커버리지 밖) 꺼둔다 — 지역이 바뀔 때마다 자동 재조정.
    setUseReplay(!!detectedRegion?.curated_replay)
  }, [detectedRegion?.curated_replay])

  const handlePresetChange = (index: number) => {
    setPresetIndex(index)
    const preset = presets[index]
    if (preset) setAddress(preset.sample_address) // AddressField가 이 변경을 감지해 자동으로 재조회함
  }

  const handleSubmit = () => {
    closeStreamRef.current?.()

    const mode = useReplay && detectedRegion?.curated_replay ? 'replay' : 'live'
    const timelinePath = mode === 'replay' ? detectedRegion?.curated_replay?.timeline_path ?? null : null

    setLoading(true)
    setConnectionError(false)
    setResult(null)
    setProgressItems([])

    closeStreamRef.current = startAssessStream(
      {
        address,
        collateralValue,
        regionCode: detectedRegion?.region_code || '',
        mode,
        timelinePath,
        floorType: floorType || null,
        floorNo: floorType ? floorNo || null : null,
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
            presets={presets}
            presetIndex={presetIndex}
            address={address}
            collateralValue={collateralValue}
            floorType={floorType}
            floorNo={floorNo}
            detectedRegion={detectedRegion}
            useReplay={useReplay}
            submitting={loading}
            onPresetChange={handlePresetChange}
            onAddressChange={setAddress}
            onRegionResolved={setDetectedRegion}
            onCollateralValueChange={setCollateralValue}
            onFloorTypeChange={setFloorType}
            onFloorNoChange={setFloorNo}
            onUseReplayChange={setUseReplay}
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
