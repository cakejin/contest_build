import { useEffect, useRef, useState } from 'react'
import { resolveRegion, searchAddress } from '../api'
import type { AddressSuggestion, ResolvedRegion } from '../types'

interface AddressFieldProps {
  value: string
  inputClassName: string
  onChange: (value: string) => void
  onRegionResolved: (region: ResolvedRegion | null) => void
}

const RESOLVE_DEBOUNCE_MS = 500
const SEARCH_DEBOUNCE_MS = 300
const MIN_SEARCH_LEN = 2

/** 도로명주소 입력 + 자동완성(JUSO API) + 지역 자동감지(V-World+홍수 에이전트).
 *
 * `value`가 어떻게 바뀌든(직접 타이핑·자동완성 선택·프리셋으로 채움) 단일 useEffect가
 * region 감지를 디바운스로 트리거한다 — 트리거 경로를 하나로 모아 "프리셋으로 채운
 * 주소는 감지가 안 됨" 같은 누락을 원천적으로 막는다(DEV_LOG.md 2026-08-18 참조). */
export function AddressField({ value, inputClassName, onChange, onRegionResolved }: AddressFieldProps) {
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [resolving, setResolving] = useState(false)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!value.trim()) {
      onRegionResolved(null)
      return
    }
    onRegionResolved(null) // 주소가 바뀌는 순간 이전 감지 결과부터 무효화(화면에 오래된 뱃지가 안 남게)
    setResolving(true)
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const region = await resolveRegion(value)
        if (!cancelled) onRegionResolved(region)
      } finally {
        if (!cancelled) setResolving(false)
      }
    }, RESOLVE_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const handleTextChange = (text: string) => {
    onChange(text)
    setOpen(true)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    if (text.trim().length < MIN_SEARCH_LEN) {
      setSuggestions([])
      return
    }
    searchTimer.current = setTimeout(async () => {
      const results = await searchAddress(text)
      setSuggestions(results)
    }, SEARCH_DEBOUNCE_MS)
  }

  const handleSelect = (s: AddressSuggestion) => {
    onChange(s.road_address)
    setSuggestions([])
    setOpen(false)
  }

  return (
    <div className="relative">
      <input
        id="address"
        type="text"
        required
        placeholder="예: 경상북도 포항시 남구 인덕로 27"
        className={inputClassName}
        value={value}
        onChange={(e) => handleTextChange(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        autoComplete="off"
      />
      {resolving && <p className="text-muted text-[11px] mt-1">지역 확인 중...</p>}
      {open && suggestions.length > 0 && (
        <ul className="absolute z-10 left-0 right-0 mt-1 bg-surface border border-border rounded-control shadow-card max-h-52 overflow-y-auto text-[13px] py-1">
          {suggestions.map((s) => (
            <li
              key={s.road_address}
              className="py-2 px-3 cursor-pointer hover:bg-surface-alt"
              onMouseDown={() => handleSelect(s)}
            >
              {s.building_name ? `${s.building_name} — ${s.road_address}` : s.road_address}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
