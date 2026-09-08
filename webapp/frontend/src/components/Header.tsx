/* 2026-09-09 — 보고서형 미니멀(사용자 결정): 그라데이션 배너·상단 회색 줄·그림자를 걷어내고
   바탕 위에 제목 한 줄만 둔다. 데이터 출처·지도 링크는 같은 줄 오른쪽으로. 브랜드 민트는 아이콘·링크에만. */
export function Header() {
  return (
    <header className="max-w-[1600px] mx-auto px-8 pt-7 pb-2 flex items-center gap-3.5">
      <span className="flex-none w-9 h-9 rounded-full bg-accent-soft text-title flex items-center justify-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
          <path d="M12 2l8 4v6c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6l8-4z" />
          <path d="M9 12l2 2 4-4" />
        </svg>
      </span>
      <div>
        <h1 className="m-0 text-[19px] font-extrabold tracking-tight text-ink">담보 기후리스크 여신심사 AI</h1>
        <p className="mt-0.5 mb-0 text-[12.5px] text-muted">물건 단위 조기경보와 심사메모 자동화 — 공공데이터 실연동 데모</p>
      </div>
      <div className="ml-auto text-[11.5px] text-muted flex items-center gap-4 max-[900px]:hidden">
        <span>데이터 출처: 기상청 특보 API · V-World · 건축HUB · 국토부 홍수위험지도</span>
        <a href="/portfolio-map" className="text-title font-semibold no-underline hover:underline">
          포트폴리오 지도 →
        </a>
      </div>
    </header>
  )
}
