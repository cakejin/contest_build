export function Header() {
  return (
    <>
      <div className="bg-surface border-b border-border py-1.5 px-8 text-[11.5px] text-muted flex justify-end gap-4">
        <span>데이터 출처: 기상청 특보 API · V-World · 건축HUB · 국토부 홍수위험지도</span>
      </div>
      <header className="relative text-white py-[26px] px-8 flex items-center gap-3.5 shadow-[0_4px_18px_-8px_rgba(0,40,34,0.45)] bg-[linear-gradient(120deg,#00c9a0_0%,var(--color-title)_55%,#005e50_100%)] after:content-[''] after:absolute after:left-0 after:right-0 after:-bottom-[3px] after:h-[3px] after:bg-[linear-gradient(90deg,var(--color-accent)_0%,var(--color-accent-soft)_100%)]">
        <div className="flex-none w-11 h-11 rounded-xl bg-white/14 border border-white/28 flex items-center justify-center">
          <svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6">
            <path d="M12 2l8 4v6c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6l8-4z" />
            <path d="M9 12l2 2 4-4" />
          </svg>
        </div>
        <div>
          <h1 className="m-0 text-[21px] font-extrabold tracking-tight">담보 기후리스크 여신심사 AI</h1>
          <p className="mt-1.5 mb-0 text-[13px] font-medium text-[#d7ede8]">물건 단위 조기경보와 심사메모 자동화 — 공공데이터 실연동 데모</p>
        </div>
      </header>
    </>
  )
}
