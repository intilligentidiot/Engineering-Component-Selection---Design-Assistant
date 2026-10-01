/* Tesla Mechanical Designs — Stage 5: Product Information */

const API = "";

// ── DOM refs ────────────────────────────────────────────────
const statusDot   = document.getElementById("status-dot");
const statusLabel = document.getElementById("api-status-label");
const form        = document.getElementById("selection-form");
const submitBtn   = document.getElementById("submit-btn");
const btnSpinner  = document.getElementById("btn-spinner");
const resultsPanel   = document.getElementById("results-panel");
const resultsSummary = document.getElementById("results-summary");
const resultsContainer = document.getElementById("results-container");
const errorPanel  = document.getElementById("error-panel");
const errorTitle  = document.getElementById("error-title");
const errorMsg    = document.getElementById("error-message");

// ── Health check ────────────────────────────────────────────
async function checkHealth() {
    try {
        const r = await fetch(`${API}/health`);
        if (r.ok) { statusDot.className = "status-dot ok"; statusLabel.textContent = "API Online"; }
        else throw new Error();
    } catch { statusDot.className = "status-dot error"; statusLabel.textContent = "API Offline"; }
}
checkHealth();

// ── Tab switching ────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`tab-content-${btn.dataset.tab}`).classList.add("active");
        if (btn.dataset.tab === "browser") initBrowser();
    });
});

// ── Helpers ──────────────────────────────────────────────────
function setLoading(on) {
    submitBtn.disabled = on;
    submitBtn.querySelector(".btn-text").textContent = on ? "Searching..." : "Find Matching Components";
    btnSpinner.hidden = !on;
}
function showError(title, msg) {
    errorTitle.textContent = title; errorMsg.textContent = msg;
    errorPanel.hidden = false;
}

// ── AI Parser ────────────────────────────────────────────────
const aiParseBtn  = document.getElementById("ai-parse-btn");
const aiText      = document.getElementById("ai-text");
const aiFeedback  = document.getElementById("ai-feedback");

if (aiParseBtn) {
    aiParseBtn.addEventListener("click", async () => {
        const text = aiText.value.trim();
        if (!text) return;

        aiParseBtn.textContent = "Parsing...";
        aiParseBtn.disabled = true;
        aiFeedback.style.display = "none";
        aiFeedback.innerHTML = "";

        try {
            const r = await fetch(`${API}/api/parse-requirements`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text })
            });
            const data = await r.json();

            // Populate form
            const reqs = data.requirements;
            if (reqs.required_speed_rpm !== null) document.getElementById("speed").value = reqs.required_speed_rpm;
            if (reqs.required_torque_nm !== null) document.getElementById("torque").value = reqs.required_torque_nm;
            if (reqs.max_voltage_v !== null) document.getElementById("voltage").value = reqs.max_voltage_v;
            if (reqs.service_factor !== null) document.getElementById("service_factor").value = reqs.service_factor;

            // Show feedback
            aiFeedback.style.display = "block";
            let feedbackHtml = `<strong>Status:</strong> ${data.parser_status}<br>`;
            if (reqs.application) feedbackHtml += `<strong>Application:</strong> ${reqs.application}<br>`;
            
            if (data.clarifications && data.clarifications.length > 0) {
                feedbackHtml += `<br><span style="color:var(--text-danger)"><strong>Clarification Needed:</strong></span><br>`;
                data.clarifications.forEach(c => feedbackHtml += `• ${c}<br>`);
            }
            if (data.missing_fields && data.missing_fields.length > 0) {
                feedbackHtml += `<br><strong>Missing Fields:</strong> ${data.missing_fields.join(", ")}`;
            }
            aiFeedback.innerHTML = feedbackHtml;
        } catch (e) {
            aiFeedback.style.display = "block";
            aiFeedback.innerHTML = `<span style="color:var(--text-danger)">Error parsing requirements: ${e.message}</span>`;
        } finally {
            aiParseBtn.textContent = "Parse Requirements";
            aiParseBtn.disabled = false;
        }
    });
}

// ── Selection form ───────────────────────────────────────────
form.addEventListener("submit", async e => {
    e.preventDefault();
    resultsPanel.hidden = true; errorPanel.hidden = true;
    setLoading(true);

    const payload = {
        required_speed_rpm: +document.getElementById("speed").value,
        required_torque_nm: +document.getElementById("torque").value,
        max_voltage_v:      +document.getElementById("voltage").value,
        service_factor:     +document.getElementById("service_factor").value,
        top_n:              +document.getElementById("top_n").value,
        include_internet_results: document.getElementById("include_internet")?.checked || false
    };

    try {
        const res  = await fetch(`${API}/api/recommend`, {
            method: "POST", headers: {"Content-Type":"application/json"},
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) { showError("Validation Error", data.detail || "Unexpected error"); return; }

        if (data.count === 0 && (!data.internet_results || data.internet_results.length === 0)) {
            showError("No Matching Components Found",
                `No verified combination satisfies: ${payload.required_speed_rpm} RPM, ` +
                `${payload.required_torque_nm} Nm × SF ${payload.service_factor} at ≤${payload.max_voltage_v} V. ` +
                `Try relaxing voltage, reducing torque, or lowering the service factor.`);
            return;
        }
        renderResults(data);
    } catch { showError("Connection Error", "Could not reach the FastAPI server."); }
    finally { setLoading(false); }
});

form.addEventListener("reset", () => { resultsPanel.hidden = true; errorPanel.hidden = true; });

// ── Results renderer ─────────────────────────────────────────
function statusBadge(s) {
    return `<span class="data-status ${s}">${s.replace(/_/g," ")}</span>`;
}

function renderResults(data) {
    // ── Stage 6.1: Build discovery status label ────────────────────────────────────────────
    const ds = data.discovery_status || "NOT_REQUESTED";
    let internetSuffix = "";
    if (data.internet_count) {
        if (ds === "COMPLETED_FROM_CACHE") {
            internetSuffix = ` · ${data.internet_count} internet discovered (cached)`;
        } else if (ds === "COMPLETED_LIVE") {
            internetSuffix = ` · ${data.internet_count} internet discovered (live search)`;
        } else {
            internetSuffix = ` · ${data.internet_count} internet discovered product${data.internet_count !== 1 ? "s" : ""}`;
        }
    }

    resultsSummary.textContent =
        `${data.count} verified local pairing${data.count !== 1 ? "s" : ""}` +
        internetSuffix +
        ` — evaluated deterministically by engineering calculation engine.`;

    resultsContainer.innerHTML = "";

    // SECTION A: Source A Verified Local Database
    const secA = document.createElement("div");
    secA.className = "source-section";
    secA.innerHTML = `<h3 class="source-title" style="color:var(--accent-green); margin:1.5rem 0 1rem 0; display:flex; align-items:center; gap:0.5rem">
        <span>●</span> SOURCE A — Verified Local Database (${data.count} candidates)
    </h3>`;

    const gridA = document.createElement("div");
    gridA.className = "results-grid";

    data.results.forEach((rec, i) => {
        const marginPct = ((rec.performance.torque_margin_factor - 1) * 100).toFixed(0);
        const effPct    = Math.round((rec.gearbox.efficiency || 0.8) * 100);
        const trace     = rec.calculation_trace || {};

        const card = document.createElement("div");
        card.className = "result-card";
        card.style.animationDelay = `${i * 0.06}s`;

        const motorSourceLink = rec.motor.source_url 
            ? `<a class="source-link" href="${rec.motor.source_url}" target="_blank">📄 View Motor Datasheet (${rec.motor.source})</a>` 
            : `<span class="source-text">Source: ${rec.motor.source || "Local DB"}</span>`;

        const gbSourceLink = rec.gearbox.source_url 
            ? `<a class="source-link" href="${rec.gearbox.source_url}" target="_blank">📄 View Gearbox Datasheet (${rec.gearbox.source})</a>` 
            : `<span class="source-text">Source: ${rec.gearbox.source || "Local DB"}</span>`;

        card.innerHTML = `
        <div class="result-card-header" id="card-hdr-a-${i}">
            <div class="rank-number ${i === 0 ? "top" : ""}">${i + 1}</div>

            <div class="comp-summary">
                <h4>⚡ Motor</h4>
                <div class="comp-name">${rec.motor.part_number}</div>
                <div class="comp-sub">${rec.motor.manufacturer} · ${rec.motor.voltage_v} V · ${rec.motor.power_w} W</div>
            </div>

            <div class="comp-summary">
                <h4>⚙ Gearbox</h4>
                <div class="comp-name">${rec.gearbox.part_number}</div>
                <div class="comp-sub">${rec.gearbox.manufacturer} · ${rec.gearbox.ratio}:1</div>
            </div>

            <div class="perf-summary">
                <div class="perf-row"><span class="perf-label">Speed</span><span class="perf-value">${rec.performance.output_speed_rpm} RPM</span></div>
                <div class="perf-row"><span class="perf-label">Torque</span><span class="perf-value">${rec.performance.output_torque_nm} Nm</span></div>
                <div class="perf-row"><span class="perf-label">Margin</span><span class="perf-value"><span class="margin-pill">+${marginPct}%</span></span></div>
                <button class="expand-btn" data-target="card-detail-a-${i}" style="margin-top:0.5rem">▼ Full Details & Calculations</button>
            </div>
        </div>

        <div class="result-card-detail" id="card-detail-a-${i}">
            <div class="detail-section">
                <h5>⚡ Motor Specifications</h5>
                <table class="spec-table">
                    <tr><td>Part Number</td><td><strong>${rec.motor.part_number}</strong></td></tr>
                    <tr><td>Manufacturer</td><td>${rec.motor.manufacturer}</td></tr>
                    <tr><td>Voltage</td><td>${rec.motor.voltage_v} V</td></tr>
                    <tr><td>Continuous Power</td><td>${rec.motor.power_w} W</td></tr>
                    <tr><td>Nominal Speed</td><td>${rec.motor.nominal_speed_rpm ?? "—"} RPM</td></tr>
                    <tr><td>Nominal Torque</td><td>${rec.motor.nominal_torque_nm ?? "—"} Nm</td></tr>
                    <tr><td>Data Status</td><td>${statusBadge(rec.motor.data_status || "ENGINEERING_VERIFIED")}</td></tr>
                </table>
                <div style="margin-top:0.5rem">${motorSourceLink}</div>
            </div>
            <div class="detail-section">
                <h5>⚙ Gearbox Specifications</h5>
                <table class="spec-table">
                    <tr><td>Part Number</td><td><strong>${rec.gearbox.part_number}</strong></td></tr>
                    <tr><td>Manufacturer</td><td>${rec.gearbox.manufacturer}</td></tr>
                    <tr><td>Gear Ratio</td><td>${rec.gearbox.ratio}:1</td></tr>
                    <tr><td>Efficiency</td><td>${effPct}%</td></tr>
                    <tr><td>Max Input Speed</td><td>${rec.gearbox.max_input_speed_rpm ?? "—"} RPM</td></tr>
                    <tr><td>Max Output Torque</td><td>${rec.gearbox.max_torque_nm} Nm</td></tr>
                    <tr><td>Data Status</td><td>${statusBadge(rec.gearbox.data_status || "ENGINEERING_VERIFIED")}</td></tr>
                </table>
                <div class="eff-bar-wrap" style="margin-top:0.5rem">
                    <div style="font-size:0.76rem;color:var(--silver-400);margin-bottom:0.3rem">Gearbox Efficiency</div>
                    <div class="eff-bar-bg"><div class="eff-bar-fill" style="width:0%" data-eff="${effPct}"></div></div>
                </div>
                <div style="margin-top:0.5rem">${gbSourceLink}</div>
            </div>
            <div class="detail-section" style="grid-column: span 2">
                <h5>📐 Candidate-Specific Calculation Trace (Engineering Proof)</h5>
                <div style="font-size:0.82rem; font-family:'JetBrains Mono', monospace; background:rgba(0,0,0,0.3); padding:0.75rem; border-radius:6px; border:1px solid var(--border-color); line-height:1.6">
                    <div><strong>1. Design Torque Requirement:</strong></div>
                    <div style="color:var(--silver-300)">${trace.design_torque?.formula || "T_design = T_required × SF"}</div>
                    <div style="color:var(--silver-400)">${trace.design_torque?.comparison || ""}</div>
                    
                    <div style="margin-top:0.5rem"><strong>2. Required Mechanical Output Power:</strong></div>
                    <div style="color:var(--silver-300)">${trace.required_power?.formula || "P = T × RPM / 9550"}</div>
                    <div style="color:var(--silver-400)">${trace.required_power?.substitution || ""} ⇒ ${trace.required_power?.comparison || ""}</div>
                    
                    <div style="margin-top:0.5rem"><strong>3. Gearbox Output Torque:</strong></div>
                    <div style="color:var(--silver-300)">${trace.gearbox_output_torque?.formula || "T_out = T_motor × Ratio × Efficiency"}</div>
                    <div style="color:var(--silver-400)">Substitution: ${trace.gearbox_output_torque?.substitution || ""}</div>
                    <div>Comparison: ${trace.gearbox_output_torque?.comparison || ""} &nbsp;<span class="data-status ${trace.gearbox_output_torque?.status || "MEETS"}">${trace.gearbox_output_torque?.status || "MEETS"}</span></div>
                    
                    <div style="margin-top:0.5rem"><strong>4. Final Output Speed:</strong></div>
                    <div style="color:var(--silver-300)">${trace.output_speed?.formula || "Output Speed = Motor RPM / Ratio"}</div>
                    <div style="color:var(--silver-400)">Substitution: ${trace.output_speed?.substitution || ""}</div>
                    <div>Comparison: ${trace.output_speed?.comparison || ""} &nbsp;<span class="data-status ${trace.output_speed?.status || "MEETS"}">${trace.output_speed?.status || "MEETS"}</span></div>
                </div>
            </div>
        </div>`;

        gridA.appendChild(card);
    });

    secA.appendChild(gridA);
    resultsContainer.appendChild(secA);

    // SECTION B: Source B Internet Discovery Components
    if (data.internet_results && data.internet_results.length > 0) {
        const ds           = data.discovery_status || "";
        const isCached     = ds === "COMPLETED_FROM_CACHE";
        const isLive       = ds === "COMPLETED_LIVE";
        const isMock       = ds === "COMPLETED_MOCK_FALLBACK";

        // Get cache timestamp from the first result that has one
        const firstCacheSource = (data.internet_results.find(r => r.cache_source) || {}).cache_source || null;
        const cacheDateLabel   = firstCacheSource ? new Date(firstCacheSource).toLocaleString() : null;

        let sourceTagHtml = "";
        if (isCached) {
            sourceTagHtml = `<span style="display:inline-flex;align-items:center;gap:0.35rem;font-size:0.72rem;font-weight:600;color:#f0b429;background:rgba(240,180,41,0.12);border:1px solid rgba(240,180,41,0.35);padding:0.18rem 0.55rem;border-radius:999px;vertical-align:middle">&#128190; Cached${cacheDateLabel ? " &middot; " + cacheDateLabel : ""}</span>`;
        } else if (isLive) {
            sourceTagHtml = `<span style="display:inline-flex;align-items:center;gap:0.35rem;font-size:0.72rem;font-weight:600;color:#4ae3b5;background:rgba(74,227,181,0.1);border:1px solid rgba(74,227,181,0.3);padding:0.18rem 0.55rem;border-radius:999px;vertical-align:middle">&#127757; Live Search</span>`;
        } else if (isMock) {
            sourceTagHtml = `<span style="display:inline-flex;align-items:center;gap:0.35rem;font-size:0.72rem;font-weight:600;color:var(--silver-400);background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);padding:0.18rem 0.55rem;border-radius:999px;vertical-align:middle">&#129302; Mock Provider</span>`;
        }

        const secB = document.createElement("div");
        secB.className = "source-section";
        secB.style.marginTop = "2.5rem";
        secB.innerHTML = `<h3 class="source-title" style="color:var(--accent-blue); margin:1.5rem 0 1rem 0; display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap">
            <span>&#127760;</span> SOURCE B — Internet Discovered Components (${data.internet_results.length} candidates)
            ${sourceTagHtml}
            <span style="font-weight:400; font-size:0.8rem; color:var(--silver-400)">(External discovery feed — evaluated by deterministic calculation engine)</span>
        </h3>`;

        const gridB = document.createElement("div");
        gridB.className = "results-grid";

        data.internet_results.forEach((rec, i) => {
            const card = document.createElement("div");
            card.className = "result-card";
            card.style.borderColor = "rgba(74, 158, 255, 0.4)";
            card.style.animationDelay = `${i * 0.06}s`;

            const imgHtml = rec.image_url 
                ? `<img src="${rec.image_url}" alt="${rec.product_name}" style="max-height:80px; object-fit:contain; background:#fff; padding:4px; border-radius:4px; margin-bottom:0.5rem">`
                : `<div style="font-size:0.75rem; color:var(--silver-400); margin-bottom:0.5rem">No Image Available</div>`;

            const dsHtml = rec.datasheet_url
                ? `<a class="source-link" href="${rec.datasheet_url}" target="_blank">📄 Product Datasheet</a>`
                : `<span style="font-size:0.75rem; color:var(--silver-400); display:inline-block; padding:0.25rem 0.5rem; background:rgba(255,255,255,0.05); border-radius:4px">Datasheet not found</span>`;

            const webHtml = rec.product_url
                ? `<a class="source-link" href="${rec.product_url}" target="_blank">🔗 Product Webpage</a>`
                : `<span style="font-size:0.75rem; color:var(--silver-400); display:inline-block; padding:0.25rem 0.5rem; background:rgba(255,255,255,0.05); border-radius:4px">Webpage not found</span>`;

            const cadHtml = rec.cad?.available
                ? `<span style="font-size:0.75rem; color:var(--accent-green); font-weight:600">📐 CAD Available</span>`
                : `<span style="font-size:0.75rem; color:var(--silver-400)">CAD Not Confirmed</span>`;

            const priceHtml = rec.price?.amount
                ? `${rec.price.currency} \$${rec.price.amount}`
                : `Price Not Stated`;

            const trace = rec.calculation_trace || {};

            card.innerHTML = `
            <div class="result-card-header" id="card-hdr-b-${i}">
                <div class="rank-number" style="background:var(--accent-blue)">B${i + 1}</div>

                <div class="comp-summary" style="flex:1.5">
                    ${imgHtml}
                    <h4>🌐 ${rec.manufacturer}</h4>
                    <div class="comp-name">${rec.product_name}</div>
                    <div class="comp-sub">PN: ${rec.part_number ?? "N/A"} · Source: ${rec.source}</div>
                </div>

                <div class="perf-summary">
                    <div class="perf-row"><span class="perf-label">Status</span><span class="perf-value">${statusBadge(rec.verification.data_status)}</span></div>
                    <div class="perf-row"><span class="perf-label">Eng Match</span><span class="perf-value"><span class="data-status ${rec.engineering_status}">${rec.engineering_status}</span></span></div>
                    <div class="perf-row"><span class="perf-label">Price</span><span class="perf-value">${priceHtml}</span></div>
                    <button class="expand-btn" data-target="card-detail-b-${i}" style="margin-top:0.5rem">▼ Full Details & Spec</button>
                </div>
            </div>

            <div class="result-card-detail" id="card-detail-b-${i}">
                <div class="detail-section">
                    <h5>⚙ Specifications</h5>
                    <table class="spec-table">
                        <tr><td>Voltage</td><td>${rec.specs.voltage_v ?? "—"} V</td></tr>
                        <tr><td>Power</td><td>${rec.specs.power_w ?? "—"} W</td></tr>
                        <tr><td>Nominal Speed</td><td>${rec.specs.nominal_speed_rpm ?? "—"} RPM</td></tr>
                        <tr><td>Gear Ratio</td><td>${rec.specs.gear_ratio ?? "—"}:1</td></tr>
                        <tr><td>Efficiency</td><td>${rec.specs.efficiency ? Math.round(rec.specs.efficiency * 100) + "%" : "—"}</td></tr>
                        <tr><td>Max Torque</td><td>${rec.specs.max_output_torque_nm ?? "—"} Nm</td></tr>
                    </table>
                </div>
                <div class="detail-section">
                    <h5>🔍 Commercial & Source Provenance</h5>
                    <table class="spec-table">
                        <tr><td>Source Provider</td><td>${rec.source}</td></tr>
                        <tr><td>Availability</td><td><span class="data-status ENGINEERING_VERIFIED">${rec.availability.status}</span></td></tr>
                        <tr><td>CAD Model</td><td>${cadHtml}</td></tr>
                        <tr><td>Discovered At</td><td>${rec.verification.discovered_at}</td></tr>
                        ${rec.specification_source ? `<tr><td>Spec Source</td><td>${rec.specification_source}</td></tr>` : ''}
                        ${rec.specification_source_url ? `<tr><td>Spec URL</td><td><a href="${rec.specification_source_url}" target="_blank" style="color:var(--accent-blue)">View Source</a></td></tr>` : ''}
                        ${rec.extracted_at ? `<tr><td>Extracted At</td><td>${new Date(rec.extracted_at).toLocaleString()}</td></tr>` : ''}
                        <tr><td>Data Source</td><td>${
                            rec.cache_hit
                            ? `<span style="color:#f0b429;font-weight:600">&#128190; Cached &middot; ${rec.cache_source ? new Date(rec.cache_source).toLocaleString() : '—'}</span>`
                            : `<span style="color:#4ae3b5;font-weight:600">&#127757; Live Search</span>`
                        }</td></tr>
                    </table>
                    <div style="margin-top:0.75rem; display:flex; gap:0.5rem; flex-wrap:wrap">
                        ${webHtml}
                        ${dsHtml}
                    </div>
                </div>

                <div class="detail-section" style="grid-column: span 2">
                    <h5>📐 Candidate Engineering Calculation Proof</h5>
                    <div style="font-size:0.82rem; font-family:'JetBrains Mono', monospace; background:rgba(0,0,0,0.3); padding:0.75rem; border-radius:6px; border:1px solid var(--border-color); line-height:1.6">
                        ${trace.gearbox_output_torque ? `
                            <div><strong>Output Torque Check:</strong> ${trace.gearbox_output_torque.formula}</div>
                            <div style="color:var(--silver-400)">Substitution: ${trace.gearbox_output_torque.substitution}</div>
                            <div>Result: ${trace.gearbox_output_torque.comparison} &nbsp;<span class="data-status ${trace.gearbox_output_torque.status}">${trace.gearbox_output_torque.status}</span></div>
                            <div style="margin-top:0.5rem"><strong>Speed Check:</strong> ${trace.output_speed.formula}</div>
                            <div style="color:var(--silver-400)">Substitution: ${trace.output_speed.substitution}</div>
                            <div>Result: ${trace.output_speed.comparison} &nbsp;<span class="data-status ${trace.output_speed.status}">${trace.output_speed.status}</span></div>
                        ` : `<div style="color:var(--silver-400)">${trace.error || "Essential specs missing for deterministic calculation."} Status: <span class="data-status DATA_INCOMPLETE">DATA_INCOMPLETE</span></div>`}
                    </div>
                </div>
            </div>`;

            gridB.appendChild(card);
        });

        secB.appendChild(gridB);
        resultsContainer.appendChild(secB);
    }

    // Universal expand/collapse handlers
    resultsContainer.querySelectorAll(".expand-btn").forEach(btn => {
        btn.addEventListener("click", e => {
            e.stopPropagation();
            const targetId = btn.dataset.target;
            const detail   = document.getElementById(targetId);
            if (!detail) return;
            const open     = detail.classList.toggle("open");
            btn.textContent = open ? "▲ Hide Details" : "▼ Full Details & Calculations";
            if (open) {
                detail.querySelectorAll(".eff-bar-fill").forEach(bar => {
                    setTimeout(() => { bar.style.width = bar.dataset.eff + "%"; }, 50);
                });
            }
        });
    });

    resultsPanel.hidden = false;
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Component Browser ─────────────────────────────────────────
let browsersLoaded = { motors: null, gearboxes: null, manufacturers: null };
let browseMode = null;

document.getElementById("browse-motors-btn").addEventListener("click",    () => loadBrowser("motors"));
document.getElementById("browse-gearboxes-btn").addEventListener("click", () => loadBrowser("gearboxes"));
document.getElementById("filter-manufacturer").addEventListener("change", () => { if (browseMode) loadBrowser(browseMode); });
document.getElementById("filter-voltage").addEventListener("change",      () => { if (browseMode === "motors") loadBrowser("motors"); });

async function initBrowser() {
    if (browsersLoaded.manufacturers) return;
    try {
        const res  = await fetch(`${API}/api/manufacturers`);
        const data = await res.json();
        browsersLoaded.manufacturers = data;
        const sel = document.getElementById("filter-manufacturer");
        data.forEach(m => {
            const opt = document.createElement("option");
            opt.value = m.id; opt.textContent = m.name;
            sel.appendChild(opt);
        });
    } catch { console.error("Could not load manufacturers"); }
}

async function loadBrowser(type) {
    browseMode = type;
    // Toggle active button style
    document.getElementById("browse-motors-btn").classList.toggle("active-filter", type === "motors");
    document.getElementById("browse-gearboxes-btn").classList.toggle("active-filter", type === "gearboxes");

    const mfgId   = document.getElementById("filter-manufacturer").value;
    const voltage = document.getElementById("filter-voltage").value;
    const container = document.getElementById("browser-container");
    container.innerHTML = `<p class="browser-empty">Loading...</p>`;

    let url = `${API}/api/${type}?`;
    if (mfgId)   url += `manufacturer_id=${mfgId}&`;
    if (voltage && type === "motors") url += `max_voltage_v=${voltage}&`;

    try {
        const res  = await fetch(url);
        const data = await res.json();
        if (!data.length) { container.innerHTML = `<p class="browser-empty">No components match the selected filters.</p>`; return; }
        renderBrowserTable(data, type, container);
    } catch { container.innerHTML = `<p class="browser-empty">Error loading data.</p>`; }
}

function renderBrowserTable(data, type, container) {
    const wrap = document.createElement("div");
    wrap.className = "browser-table-wrap";

    let headers, rowFn;
    if (type === "motors") {
        headers = ["Part Number","Manufacturer","Voltage","Power","Nom. Speed","Nom. Torque","Max Torque","Status"];
        rowFn = m => `
            <td class="pn">${m.part_number}</td>
            <td>${m.manufacturer.name}</td>
            <td>${m.voltage_v} V</td>
            <td>${m.continuous_power_w} W</td>
            <td>${m.nominal_speed_rpm} RPM</td>
            <td>${m.nominal_torque_nm} Nm</td>
            <td>${m.max_torque_nm ?? "—"} Nm</td>
            <td>${statusBadge(m.data_status)}</td>`;
    } else {
        headers = ["Part Number","Manufacturer","Ratio","Efficiency","Max Input RPM","Max Output Torque","Status"];
        rowFn = g => `
            <td class="pn">${g.part_number}</td>
            <td>${g.manufacturer.name}</td>
            <td>${g.gear_ratio}:1</td>
            <td>${(g.efficiency * 100).toFixed(0)}%</td>
            <td>${g.max_input_speed_rpm ?? "—"} RPM</td>
            <td>${g.max_output_torque_nm} Nm</td>
            <td>${statusBadge(g.data_status)}</td>`;
    }

    wrap.innerHTML = `
    <table class="browser-table">
        <thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
        <tbody>${data.map(row => `<tr>${rowFn(row)}</tr>`).join("")}</tbody>
    </table>`;

    container.innerHTML = "";
    container.appendChild(wrap);
}
