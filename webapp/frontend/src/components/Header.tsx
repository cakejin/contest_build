/* 2026-09-09 — 토스증권식 얇은 상단 줄(사용자 결정): 왼쪽 회사명(iM뱅크 글자 워드마크 — 로고 파일은
   저작권·공식 서비스 오인 문제로 쓰지 않음) │ 제품명, 가운데 화면 메뉴 2개, 오른쪽 "데모" 라벨.
   제품 설명 문장·데이터 출처 줄은 헤더에서 뺐다(빈 상태 안내·요약 출처 보기·하단 줄에 이미 있음). */

const NAV: { href: string; label: string }[] = [
  { href: '/', label: '담보 심사' },
  { href: '/portfolio-map', label: '포트폴리오 지도' },
]

export function Header() {
  const path = typeof window === 'undefined' ? '/' : window.location.pathname
  return (
    <header className="bg-surface border-b border-surface-alt">
      <div className="max-w-[1600px] mx-auto px-8 h-[52px] flex items-center gap-6">
        <a href="/" className="flex items-center gap-2.5 no-underline">
          <span className="text-[17px] font-extrabold tracking-tight text-title">iM뱅크</span>
          <span className="w-px h-4 bg-border" aria-hidden="true" />
          <span className="text-[14.5px] font-bold text-ink">담보 기후리스크 심사</span>
        </a>
        <nav className="flex items-center gap-1 h-full" aria-label="화면">
          {NAV.map((n) => {
            const on = n.href === '/' ? path === '/' || path === '' : path.startsWith(n.href)
            return (
              <a
                key={n.href}
                href={n.href}
                aria-current={on ? 'page' : undefined}
                className={`h-[52px] flex items-center px-3 text-[13.5px] no-underline border-b-2 ${
                  on ? 'text-ink font-bold border-title' : 'text-muted font-medium border-transparent hover:text-ink'
                }`}
              >
                {n.label}
              </a>
            )
          })}
        </nav>
        <span className="ml-auto text-[11.5px] font-semibold text-muted bg-surface-alt rounded-full px-2.5 py-1 whitespace-nowrap">
          공공데이터 실연동 데모
        </span>
      </div>
    </header>
  )
}
