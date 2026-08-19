import { useEffect, useRef, useState } from 'react'
import { fetchPortfolioList, resolveRegion } from '../api'
import { fmtWon } from '../lib/format'
import type { PortfolioListItem, ResolvedRegion } from '../types'

interface PortfolioPickerProps {
  inputClassName: string
  onSelect: (item: PortfolioListItem) => void
  onRegionResolved: (region: ResolvedRegion | null) => void
}

/** "기존 포트폴리오 조회" 탭용 — 316건을 한 번에 불러와 담보ID·주소로 클라이언트
 * 사이드 검색한다(디바운스 불필요, 서버 왕복 없이 즉시 필터링). 선택 시 그 레코드의
 * 실제 주소로 resolveRegion()을 호출해 AddressField와 동일한 소스의 지역 감지 결과를
 * 얻는다(region_code가 이미 레코드에 있지만, coverage·region_name·curated_replay 등
 * 풍부한 정보는 이 API에서만 나와 두 탭의 지역 감지 결과가 어긋나지 않게 한다). */
export function PortfolioPicker({ inputClassName, onSelect, onRegionResolved }: PortfolioPickerProps) {
  const [items, setItems] = useState<PortfolioListItem[]>([])
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<PortfolioListItem | null>(null)
  const [open, setOpen] = useState(false)
  const [resolving, setResolving] = useState(false)
  const loadedRef = useRef(false)

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    fetchPortfolioList().then(setItems)
  }, [])

  const matches =
    keyword.trim().length < 1
      ? []
      : items
          .filter((it) => it.address.includes(keyword) || it.collateral_id.includes(keyword))
          .slice(0, 30)

  const handleSelect = async (item: PortfolioListItem) => {
    // 검색창엔 선택한 라벨을 채우지 않고 비운다 — 채워두면 그 문자열이 어떤 주소·ID와도
    // 다시 매칭이 안 돼서 두 번째 항목을 고를 때 검색 결과가 하나도 안 뜨는 버그가 있었다
    // (사용자 리포트: "담보가액이 다 똑같다" — 사실은 첫 선택 이후 재선택이 조용히
    // 반영 안 되고 있었던 것). 대신 선택된 항목은 아래 별도 캡션으로 보여준다.
    setKeyword('')
    setSelected(item)
    setOpen(false)
    onSelect(item)
    onRegionResolved(null)
    setResolving(true)
    try {
      const region = await resolveRegion(item.address)
      onRegionResolved(region)
    } finally {
      setResolving(false)
    }
  }

  return (
    <div className="relative">
      <input
        type="text"
        placeholder={items.length === 0 ? '포트폴리오 불러오는 중...' : '담보ID·주소로 검색 (예: COL-001, 침산로)'}
        className={inputClassName}
        value={keyword}
        onChange={(e) => {
          setKeyword(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        autoComplete="off"
      />
      {selected && !keyword && (
        <p className="text-[11px] mt-1">
          선택됨: <span className="font-semibold text-ink">{selected.collateral_id}</span> — {selected.address} (
          {fmtWon(selected.collateral_value)})
        </p>
      )}
      {resolving && <p className="text-muted text-[11px] mt-1">지역 확인 중...</p>}
      {open && matches.length > 0 && (
        <ul className="absolute z-10 left-0 right-0 mt-1 bg-surface border border-border rounded-control shadow-card max-h-52 overflow-y-auto text-[13px] py-1">
          {matches.map((it) => (
            <li
              key={it.collateral_id}
              className="py-2 px-3 cursor-pointer hover:bg-surface-alt"
              onMouseDown={() => handleSelect(it)}
            >
              <span className="font-semibold">{it.collateral_id}</span> — {it.address}
              <span className="text-muted ml-1">({it.collateral_type})</span>
            </li>
          ))}
        </ul>
      )}
      {open && keyword.trim().length >= 1 && matches.length === 0 && items.length > 0 && (
        <div className="absolute z-10 left-0 right-0 mt-1 bg-surface border border-border rounded-control shadow-card text-[13px] py-2 px-3 text-muted">
          일치하는 담보가 없어요
        </div>
      )}
    </div>
  )
}
