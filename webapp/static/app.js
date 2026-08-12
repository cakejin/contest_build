/* 담보 기후리스크 여신심사 AI — 데모 프론트엔드.
   진행상황 목록은 미리 정해둔 가짜 스텝이 아니라, 백엔드가 SSE로 실제 단계에
   진입할 때 보낸 메시지를 그대로 순서대로 쌓아 보여준다(포트폴리오 재계산 단계는
   특보 트리거가 있을 때만 실제로 나타남 — 그래서 고정 스켈레톤을 미리 그리지 않는다). */

/* 카드 헤더용 라인 아이콘(24x24, currentColor) — 섹션 성격을 한눈에 구분하기 위한 시각 보조.
   판정·수치 자체에는 영향 없음(순수 장식). */
const ICONS = {
  result: '<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/>',
  flood: '<path d="M2 8c1.5 1.5 3 1.5 4.5 0s3-1.5 4.5 0 3 1.5 4.5 0 3-1.5 4.5 0"/><path d="M2 14c1.5 1.5 3 1.5 4.5 0s3-1.5 4.5 0 3 1.5 4.5 0 3-1.5 4.5 0"/><path d="M2 20c1.5 1.5 3 1.5 4.5 0s3-1.5 4.5 0 3 1.5 4.5 0 3-1.5 4.5 0"/>',
  building: '<rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 16h1M14 16h1"/>',
  chart: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M2 20h20"/>',
  memo: '<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/><path d="M9 15l2 2 4-4"/>',
  bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  portfolio: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
};

function cardHead(iconKey, title) {
  return `<div class="card-head"><span class="card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[iconKey]}</svg></span><h2>${title}</h2></div>`;
}

const progressList = document.getElementById("progress-list");
const presetSelect = document.getElementById("preset");
const form = document.getElementById("assess-form");
const submitBtn = document.getElementById("submit-btn");
const resultSection = document.getElementById("result-section");

let presets = [];

async function loadPresets() {
  const res = await fetch("/api/regions");
  presets = await res.json();
  presetSelect.innerHTML = presets
    .map((p, i) => `<option value="${i}">${p.label}</option>`)
    .join("");
  applyPreset(0);
}

function applyPreset(index) {
  const p = presets[index];
  if (!p) return;
  document.getElementById("address").value = p.sample_address;
}

presetSelect.addEventListener("change", (e) => applyPreset(Number(e.target.value)));

function resetProgress() {
  progressList.innerHTML = "";
}

function addProgressItem(message) {
  const items = progressList.querySelectorAll("li.active");
  items.forEach((li) => li.classList.replace("active", "done"));

  const li = document.createElement("li");
  li.className = "active";
  li.innerHTML = `<span class="dot"></span><span>${escapeHtml(message)}</span>`;
  progressList.appendChild(li);
}

function finishProgress() {
  progressList.querySelectorAll("li.active").forEach((li) => li.classList.replace("active", "done"));
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const preset = presets[Number(presetSelect.value)] || {};
  const address = document.getElementById("address").value.trim();
  const collateralValue = document.getElementById("collateral-value").value;

  const params = new URLSearchParams({
    address,
    collateral_value: collateralValue,
    region_code: preset.region_code || "47111",
    mode: preset.mode || "replay",
  });
  if (preset.timeline_path) params.set("timeline_path", preset.timeline_path);

  submitBtn.disabled = true;
  submitBtn.textContent = "평가 실행 중...";
  resetProgress();
  resultSection.innerHTML = `<div class="card">${cardHead("result", "결과")}<p class="muted">진행 중이에요 — 왼쪽 진행상황 패널을 확인하세요.</p></div>`;

  const source = new EventSource(`/api/assess?${params.toString()}`);

  source.addEventListener("progress", (ev) => {
    const data = JSON.parse(ev.data);
    addProgressItem(data.message);
  });

  source.addEventListener("result", (ev) => {
    const data = JSON.parse(ev.data);
    finishProgress();
    renderResult(data);
    submitBtn.disabled = false;
    submitBtn.textContent = "평가 실행";
    source.close();
  });

  source.onerror = () => {
    if (submitBtn.disabled) {
      resultSection.innerHTML = `<div class="card">${cardHead("result", "결과")}<div class="error-box">서버 연결이 끊겼어요. 다시 시도해 주세요.</div></div>`;
    }
    submitBtn.disabled = false;
    submitBtn.textContent = "평가 실행";
    source.close();
  };
});

function tierBadgeClass(tier, coverage) {
  if (coverage === "OUT_OF_SCOPE") return "tier-oos";
  return `tier-${tier}`;
}

function fmtWon(n) {
  if (n === null || n === undefined) return "—";
  return Math.round(n).toLocaleString("ko-KR") + "원";
}

function fmtPct(n) {
  const pct = (n * 100).toFixed(1) + "%";
  return n >= 0 ? `<span class="pct-up">+${pct}</span>` : `<span class="pct-down">${pct}</span>`;
}

/* EAL 히스토그램 — 세 가지 보기를 토글로 비교할 수 있게 한다(2026-08-12, 사용자 피드백:
   "0원 구간이 99%대라 나머지가 안 보인다"). 세 보기 전부 같은 원본 20-bin 데이터를 다르게
   변형할 뿐 — 새 계산은 없다. 어느 보기가 나은지는 실제로 띄워보고 같이 판단한다. */
let _currentEalBins = null;
let _ealChartMode = "severity"; // "linear" | "log" | "severity"

const EAL_RAMPS = ["var(--ramp-1)", "var(--ramp-2)", "var(--ramp-3)", "var(--ramp-4)", "var(--ramp-5)"];

function _ealBarDiv(bin, heightPct, lastBinEnd) {
  const rampIdx = Math.min(4, Math.floor((bin.bin_end / lastBinEnd) * 5));
  return `<div class="eal-bar" style="height:${heightPct}%; background:${EAL_RAMPS[rampIdx]}" title="${fmtWon(bin.bin_start)} ~ ${fmtWon(bin.bin_end)}: ${bin.count}회"></div>`;
}

function _renderEalBars(bins, mode) {
  const lastBinEnd = bins[bins.length - 1].bin_end;

  if (mode === "severity") {
    const tail = bins.slice(1); // 0원 구간(사상 미발생 대다수 포함) 제외
    const maxCount = Math.max(0, ...tail.map((b) => b.count));
    return tail.map((b) => _ealBarDiv(b, maxCount > 0 ? (b.count / maxCount) * 100 : 0, lastBinEnd)).join("");
  }

  if (mode === "log") {
    const maxLog = Math.max(...bins.map((b) => Math.log10(b.count + 1)));
    return bins.map((b) => _ealBarDiv(b, maxLog > 0 ? (Math.log10(b.count + 1) / maxLog) * 100 : 0, lastBinEnd)).join("");
  }

  // linear — 원본 그대로, 일부러 보정하지 않는다(왜 읽기 힘든지 그대로 보여주는 게 목적)
  const maxCount = Math.max(...bins.map((b) => b.count));
  return bins.map((b) => _ealBarDiv(b, maxCount > 0 ? (b.count / maxCount) * 100 : 0, lastBinEnd)).join("");
}

function _ealCaption(bins, mode) {
  const total = bins.reduce((sum, b) => sum + b.count, 0);
  const noLoss = bins[0].count;
  const noLossPct = total > 0 ? ((noLoss / total) * 100).toFixed(1) : "0.0";

  if (mode === "severity") {
    return `<p class="muted">${noLoss.toLocaleString()}회(${noLossPct}%)는 손실 없음(0원 구간, 표에서 제외) — 아래는 <strong>손실이 발생한 ${(total - noLoss).toLocaleString()}회만</strong>의 분포입니다.</p>`;
  }
  if (mode === "log") {
    return `<p class="muted">⚠ 로그 스케일 — 막대 높이가 실제 발생 비율에 비례하지 않습니다(0원 구간이 ${noLossPct}%라 압축해서 표시). 정확한 비율은 막대에 마우스를 올려 확인하세요.</p>`;
  }
  return `<p class="muted">0원 구간이 전체의 ${noLossPct}%(${noLoss.toLocaleString()}회)를 차지해 나머지 구간이 잘 안 보일 수 있어요.</p>`;
}

function _renderEalChartBody() {
  const bins = _currentEalBins;
  if (!bins || bins.length === 0) return '<p class="muted">분포를 산출하지 못했어요(입력 데이터 불충분).</p>';
  const rangeStart = _ealChartMode === "severity" ? bins[1]?.bin_start ?? 0 : 0;
  return `
    <div id="eal-chart">${_renderEalBars(bins, _ealChartMode)}</div>
    <div class="eal-caption"><span>${fmtWon(rangeStart)}</span><span>${fmtWon(bins[bins.length - 1].bin_end)}</span></div>
    ${_ealCaption(bins, _ealChartMode)}
  `;
}

function setEalMode(mode) {
  _ealChartMode = mode;
  document.querySelectorAll("#eal-mode-toggle button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  document.getElementById("eal-chart-body").innerHTML = _renderEalChartBody();
}

function renderEalChart(bins) {
  _currentEalBins = bins && bins.length ? bins : null;
  if (!_currentEalBins) return '<p class="muted">분포를 산출하지 못했어요(입력 데이터 불충분).</p>';
  return `
    <div class="segmented" id="eal-mode-toggle">
      <button type="button" data-mode="severity" class="active" onclick="setEalMode('severity')">손실 발생 구간만</button>
      <button type="button" data-mode="log" onclick="setEalMode('log')">전체(로그 스케일)</button>
      <button type="button" data-mode="linear" onclick="setEalMode('linear')">전체(선형, 원본)</button>
    </div>
    <div id="eal-chart-body">${_renderEalChartBody()}</div>
  `;
}

function renderMemo(memo) {
  const sections = memo.sections
    .map(
      (s) => `
      <div class="memo-section">
        ${escapeHtml(s.text)}
        <span class="memo-cite">근거: ${s.citations.join(", ")}</span>
      </div>`
    )
    .join("");
  const rejected = memo.rejected_sentences.length
    ? `<div class="memo-rejected">인용검증 게이트가 반려한 문장 ${memo.rejected_sentences.length}건(근거 없음/미확인 출처라 심사메모에서 자동 제외됨)</div>`
    : "";
  const fallbackNote = memo.fallback_used
    ? `<p class="muted">인용 실패율이 임계치를 넘어 규칙기반 폴백 템플릿으로 대체됐어요(LLM 미사용, 항상 인용률 100%).</p>`
    : "";
  return `${fallbackNote}${sections}${rejected}`;
}

function renderAdvisory(advisory) {
  if (!advisory.active_warnings.length) {
    return `<p class="muted">이 지역·시점엔 발효 중인 특보가 없어요(status: ${advisory.status}).</p>`;
  }
  return advisory.active_warnings
    .map(
      (w) => `<div class="advisory-event"><strong>${escapeHtml(w.type)}</strong> · ${w.issued_at} · <a href="${w.source_url}" target="_blank" rel="noopener">출처</a></div>`
    )
    .join("");
}

function renderPortfolio(portfolioBatch, esgRecs) {
  if (!portfolioBatch) {
    return '<div class="no-alert-note">특보 트리거가 없어 포트폴리오 재계산을 생략했어요(특보가 없으면 배치를 돌리지 않는 것도 설계상 정상 동작입니다).</div>';
  }
  const header = `<div class="kv-row"><span class="k">지역 매칭</span><span class="v">${portfolioBatch.matched_count}건 / 전체 ${portfolioBatch.total_records}건</span></div>`;
  if (!portfolioBatch.alerts.length) {
    return `${header}<div class="no-alert-note">매칭된 담보 ${portfolioBatch.matched_count}건 전부 EAL 변화율이 재심사 임계치 미만이라 알림이 발생하지 않았어요 — 특보가 있어도 실제 손실액 변화가 없으면 알림을 만들어내지 않는 것이 설계 의도입니다.</div>`;
  }
  const rows = portfolioBatch.alerts
    .map((a) => {
      const rec = (esgRecs || []).find((r) => r.collateral_id === a.collateral_id);
      const actions = rec ? rec.actions.map((act) => `<span class="action-chip">${escapeHtml(act)}</span>`).join("") : "";
      return `<tr>
        <td>${a.collateral_id}</td>
        <td>${fmtWon(a.EAL_before)}</td>
        <td>${fmtWon(a.EAL_after)}</td>
        <td>${typeof a.EAL_change_pct === "number" ? fmtPct(a.EAL_change_pct) : a.EAL_change_pct}</td>
        <td>${actions}</td>
      </tr>`;
    })
    .join("");
  return `${header}
    <table class="alert-table">
      <thead><tr><th>담보ID</th><th>EAL(이전)</th><th>EAL(재계산)</th><th>변화율</th><th>ESG 추천 액션</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderResult(data) {
  if (data.error) {
    resultSection.innerHTML = `<div class="card">${cardHead("result", "결과")}<div class="error-box">${escapeHtml(data.error)}</div></div>`;
    return;
  }

  const flood = data.flood.flood;
  const tierLabel = data.coverage_label || (flood.coverage === "OUT_OF_SCOPE" ? "커버리지 밖" : flood.tier);
  const badgeClass = tierBadgeClass(flood.tier, flood.coverage);

  const factorRows = (data.building.contributing_factors || [])
    .map((f) => `<tr><td>${f.name}</td><td>${f.raw_value}</td><td>${f.normalized_score}</td><td>${(f.weight_used * 100).toFixed(1)}%</td></tr>`)
    .join("");

  resultSection.innerHTML = `
    <div class="card">
      ${cardHead("flood", "침수 위험 판정")}
      <span class="badge ${badgeClass}">${escapeHtml(tierLabel || "판정")}</span>
      <div class="kv-row"><span class="k">하천</span><span class="v">${flood.river_name || "—"}</span></div>
      <div class="kv-row"><span class="k">폴리곤까지 거리</span><span class="v">${flood.distance_to_polygon_m ?? "—"} m</span></div>
      <div class="kv-row"><span class="k">빈도</span><span class="v">${flood.freq_label || "—"}</span></div>
    </div>

    <div class="card">
      ${cardHead("building", "건물취약도")}
      <div class="kv-row"><span class="k">점수</span><span class="v">${data.building.vulnerability_score ?? "—"} / 100</span></div>
      <div class="kv-row"><span class="k">상태</span><span class="v">${data.building.status}</span></div>
      ${factorRows ? `<table class="factor-table"><thead><tr><th>항목</th><th>원값</th><th>정규화점수</th><th>가중치</th></tr></thead><tbody>${factorRows}</tbody></table>` : ""}
    </div>

    <div class="card">
      ${cardHead("chart", "예상 손실액(EAL) 분포")}
      <div class="kv-row"><span class="k">평균 EAL</span><span class="v">${fmtWon(data.scenario.eal.EAL_mean)}</span></div>
      <div class="kv-row"><span class="k">p95 / p99</span><span class="v">${fmtWon(data.scenario.eal.EAL_p95)} / ${fmtWon(data.scenario.eal.EAL_p99)}</span></div>
      ${renderEalChart(data.scenario.eal.distribution_histogram_bins)}
      <p class="muted">시드 ${data.scenario.eal.seed}, ${data.scenario.eal.n_iterations.toLocaleString()}회 몬테카를로 시뮬레이션</p>
    </div>

    <div class="card">
      ${cardHead("memo", "근거 인용 심사메모")}
      ${renderMemo(data.memo)}
    </div>

    <div class="card">
      ${cardHead("bell", "기상특보 이력")}
      ${renderAdvisory(data.advisory)}
    </div>

    <div class="card">
      ${cardHead("portfolio", "포트폴리오 재심사 알림 · ESG 추천")}
      ${renderPortfolio(data.portfolio_batch, data.esg_recommendations)}
    </div>

    <div class="disclosure">${escapeHtml(data.memo.disclosure)}</div>
  `;
}

loadPresets();
