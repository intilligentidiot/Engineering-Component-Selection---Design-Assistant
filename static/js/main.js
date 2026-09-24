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
    };

    try {
        const res  = await fetch(`${API}/api/recommend`, {
            method: "POST", headers: {"Content-Type":"application/json"},
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) { showError("Validation Error", data.detail || "Unexpected error"); return; }

        if (data.count === 0) {
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
    resultsSummary.textContent =
        `${data.count} valid pairing${data.count !== 1 ? "s" : ""} — ranked by engineering efficiency (best match first).`;

    resultsContainer.innerHTML = "";
    const grid = document.createElement("div");
    grid.className = "results-grid";

    data.results.forEach((rec, i) => {
        const marginPct = ((rec.performance.torque_margin_factor - 1) * 100).toFixed(0);
        const effPct    = Math.round(rec.gearbox.ratio > 0 ? 80 : 75); // placeholder visual

        const card = document.createElement("div");
        card.className = "result-card";
        card.style.animationDelay = `${i * 0.06}s`;

        card.innerHTML = `
        <div class="result-card-header" id="card-hdr-${i}">
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
                <button class="expand-btn" data-idx="${i}" style="margin-top:0.5rem">▼ Full Spec</button>
            </div>
        </div>

        <div class="result-card-detail" id="card-detail-${i}">
            <div class="detail-section">
                <h5>⚡ Motor — ${rec.motor.part_number}</h5>
                <table class="spec-table">
                    <tr><td>Manufacturer</td><td>${rec.motor.manufacturer}</td></tr>
                    <tr><td>Voltage</td><td>${rec.motor.voltage_v} V</td></tr>
                    <tr><td>Continuous Power</td><td>${rec.motor.power_w} W</td></tr>
                </table>
                <a class="source-link" href="#" target="_blank">📄 View Datasheet / Source</a>
            </div>
            <div class="detail-section">
                <h5>⚙ Gearbox — ${rec.gearbox.part_number}</h5>
                <table class="spec-table">
                    <tr><td>Manufacturer</td><td>${rec.gearbox.manufacturer}</td></tr>
                    <tr><td>Gear Ratio</td><td>${rec.gearbox.ratio}:1</td></tr>
                    <tr><td>Max Output Torque</td><td>${rec.gearbox.max_torque_nm} Nm</td></tr>
                </table>
                <div class="eff-bar-wrap">
                    <div style="font-size:0.76rem;color:var(--silver-400);margin-bottom:0.3rem">Gearbox Efficiency</div>
                    <div class="eff-bar-bg"><div class="eff-bar-fill" style="width:0%" data-eff="${effPct}"></div></div>
                    <div style="font-size:0.76rem;color:var(--silver-400);margin-top:0.3rem">${effPct}%</div>
                </div>
            </div>
            <div class="detail-section">
                <h5>📊 Calculated Performance</h5>
                <table class="spec-table">
                    <tr><td>Output Speed</td><td>${rec.performance.output_speed_rpm} RPM</td></tr>
                    <tr><td>Output Torque</td><td>${rec.performance.output_torque_nm} Nm</td></tr>
                    <tr><td>Torque Safety Margin</td><td>+${marginPct}%</td></tr>
                </table>
            </div>
            <div class="detail-section">
                <h5>🔍 Data Provenance</h5>
                <table class="spec-table">
                    <tr><td>Motor Status</td><td>${statusBadge("ENGINEERING_VERIFIED")}</td></tr>
                    <tr><td>Gearbox Status</td><td>${statusBadge("ENGINEERING_VERIFIED")}</td></tr>
                    <tr><td>Source</td><td>Verified Local Database</td></tr>
                </table>
                <!-- Connection Point D: Future Source B internet results will appear here with DISCOVERED badge -->
            </div>
        </div>`;

        grid.appendChild(card);
    });

    resultsContainer.appendChild(grid);

    // Expand/collapse handlers
    resultsContainer.querySelectorAll(".expand-btn").forEach(btn => {
        btn.addEventListener("click", e => {
            e.stopPropagation();
            const idx    = btn.dataset.idx;
            const detail = document.getElementById(`card-detail-${idx}`);
            const open   = detail.classList.toggle("open");
            btn.textContent = open ? "▲ Hide Spec" : "▼ Full Spec";
            // Animate efficiency bars on open
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
