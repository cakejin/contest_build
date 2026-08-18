import { useEffect, useRef, useState } from 'react'
import { Header } from './components/Header'
import { AssessForm } from './components/AssessForm'
import { ProgressList } from './components/ProgressList'
import { ResultSection } from './components/ResultSection'
import { fetchRegionPresets, startAssessStream } from './api'
import type { AssessResult, ProgressItem, RegionPreset } from './types'

function App() {
  const [presets, setPresets] = useState<RegionPreset[]>([])
  const [presetIndex, setPresetIndex] = useState(0)
  const [address, setAddress] = useState('')
  const [collateralValue, setCollateralValue] = useState('500000000')
  const [floorType, setFloorType] = useState('')
  const [floorNo, setFloorNo] = useState('')
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

  const handlePresetChange = (index: number) => {
    setPresetIndex(index)
    const preset = presets[index]
    if (preset) setAddress(preset.sample_address)
  }

  const handleSubmit = () => {
    closeStreamRef.current?.()
    const preset = presets[presetIndex]

    setLoading(true)
    setConnectionError(false)
    setResult(null)
    setProgressItems([])

    closeStreamRef.current = startAssessStream(
      {
        address,
        collateralValue,
        regionCode: preset?.region_code || '47111',
        mode: preset?.mode || 'replay',
        timelinePath: preset?.timeline_path,
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
            submitting={loading}
            onPresetChange={handlePresetChange}
            onAddressChange={setAddress}
            onCollateralValueChange={setCollateralValue}
            onFloorTypeChange={setFloorType}
            onFloorNoChange={setFloorNo}
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
