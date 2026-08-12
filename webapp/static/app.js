/* 담보 기후리스크 여신심사 AI — 데모 프론트엔드.
   진행상황 목록은 미리 정해둔 가짜 스텝이 아니라, 백엔드가 SSE로 실제 단계에
   진입할 때 보낸 메시지를 그대로 순서대로 쌓아 보여준다(포트폴리오 재계산 단계는
   특보 트리거가 있을 때만 실제로 나타남 — 그래서 고정 스켈레톤을 미리 그리지 않는다). */

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
  resultSection.innerHTML = '<div class="card"><h2>결과</h2><p class="muted">진행 중이에요 — 왼쪽 진행상황 패널을 확인하세요.</p></div>';

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
      resultSection.innerHTML = `<div class="card"><h2>결과</h2><div class="error-box">서버 연결이 끊겼어요. 다시 시도해 주세요.</div></div>`;
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

function renderEalChart(bins) {
  if (!bins || bins.length === 0) return '<p class="muted">분포를 산출하지 못했어요(입력 데이터 불충분).</p>';
  const maxCount = Math.max(...bins.map((b) => b.count));
  const ramps = ["var(--ramp-1)", "var(--ramp-2)", "var(--ramp-3)", "var(--ramp-4)", "var(--ramp-5)"];
  const bars = bins
    .map((b) => {
      const heightPct = maxCount > 0 ? Math.max((b.count / maxCount) * 100, b.count > 0 ? 3 : 0) : 0;
      const rampIdx = Math.min(4, Math.floor((b.bin_end / bins[bins.length - 1].bin_end) * 5));
      return `<div class="eal-bar" style="height:${heightPct}%; background:${ramps[rampIdx]}" title="${fmtWon(b.bin_start)} ~ ${fmtWon(b.bin_end)}: ${b.count}회"></div>`;
    })
    .join("");
  return `
    <div id="eal-chart">${bars}</div>
    <div class="eal-caption"><span>${fmtWon(0)}</span><span>${fmtWon(bins[bins.length - 1].bin_end)}</span></div>
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
    resultSection.innerHTML = `<div class="card"><h2>결과</h2><div class="error-box">${escapeHtml(data.error)}</div></div>`;
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
      <h2>침수 위험 판정</h2>
      <span class="badge ${badgeClass}">${escapeHtml(tierLabel || "판정")}</span>
      <div class="kv-row"><span class="k">하천</span><span class="v">${flood.river_name || "—"}</span></div>
      <div class="kv-row"><span class="k">폴리곤까지 거리</span><span class="v">${flood.distance_to_polygon_m ?? "—"} m</span></div>
      <div class="kv-row"><span class="k">빈도</span><span class="v">${flood.freq_label || "—"}</span></div>
    </div>

    <div class="card">
      <h2>건물취약도</h2>
      <div class="kv-row"><span class="k">점수</span><span class="v">${data.building.vulnerability_score ?? "—"} / 100</span></div>
      <div class="kv-row"><span class="k">상태</span><span class="v">${data.building.status}</span></div>
      ${factorRows ? `<table class="factor-table"><thead><tr><th>항목</th><th>원값</th><th>정규화점수</th><th>가중치</th></tr></thead><tbody>${factorRows}</tbody></table>` : ""}
    </div>

    <div class="card">
      <h2>예상 손실액(EAL) 분포</h2>
      <div class="kv-row"><span class="k">평균 EAL</span><span class="v">${fmtWon(data.scenario.eal.EAL_mean)}</span></div>
      <div class="kv-row"><span class="k">p95 / p99</span><span class="v">${fmtWon(data.scenario.eal.EAL_p95)} / ${fmtWon(data.scenario.eal.EAL_p99)}</span></div>
      ${renderEalChart(data.scenario.eal.distribution_histogram_bins)}
      <p class="muted">시드 ${data.scenario.eal.seed}, ${data.scenario.eal.n_iterations.toLocaleString()}회 몬테카를로 시뮬레이션</p>
    </div>

    <div class="card">
      <h2>근거 인용 심사메모</h2>
      ${renderMemo(data.memo)}
    </div>

    <div class="card">
      <h2>기상특보 이력</h2>
      ${renderAdvisory(data.advisory)}
    </div>

    <div class="card">
      <h2>포트폴리오 재심사 알림 · ESG 추천</h2>
      ${renderPortfolio(data.portfolio_batch, data.esg_recommendations)}
    </div>

    <div class="disclosure">${escapeHtml(data.memo.disclosure)}</div>
  `;
}

loadPresets();
