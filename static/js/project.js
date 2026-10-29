/* Tesla Mechanical Designs — whole-project calculation plan
 *
 * Shows, for a machine project, the information needed (have / missing / where
 * to get it) and every calculation in order. /api/project-evaluate runs the
 * calculations; results flow from one step to the next. No maths here.
 */

(() => {
    const $ = id => document.getElementById(id);
    const area = $("pj-area");
    if (!area) return;

    const head = $("pj-head"), info = $("pj-info"), calcs = $("pj-calcs"), calcBtn = $("pj-calc"), progress = $("pj-progress");
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const fmt = x => (x === null || x === undefined) ? "—"
        : Math.abs(x) >= 1e4 ? Math.round(x).toLocaleString() : String(Number(Number(x).toPrecision(4)));

    let plan = null, values = {}, quotes = {}, typical = {}, estimated = {};
    let lastResult = null, known = {};   // known: symbol -> { value, unit } for every input and result   // estimated: symbol -> how it was estimated

    function hide() { area.hidden = true; plan = null; values = {}; quotes = {}; typical = {}; estimated = {}; }

    async function show(data) {
        hide();
        plan = data.project;
        plan.inputs.forEach(i => {
            if (i.value !== null && i.value !== undefined) { values[i.symbol] = i.value; quotes[i.symbol] = i.quote; }
            else if (i.typical_value !== null && i.typical_value !== undefined) { values[i.symbol] = i.typical_value; typical[i.symbol] = i.typical_note || "typical value"; }
        });
        const ai = plan.origin === "AI";
        head.innerHTML = `<div class="as-head">
            <div class="as-head-tags">${ai ? `<span class="tag tag-ai">AI plan — check before use</span>`
                : `<span class="tag tag-ok">Built-in plan</span><span class="tag">pending engineering approval</span>`}</div>
            <h2 class="as-head-title pj-title">${esc(plan.title)}</h2>
            <p class="as-head-sum">${esc(plan.summary)}</p>
            <p class="as-head-note">${ai ? "The AI chose the methods; the tool does every calculation and shows each step."
                : "Motor + gearbox selection and bearing life use the tool's checked calculations."}</p>
            <div id="pj-std-summary"></div></div>`;
        stdSummary();
        renderInfo();
        $("pj-limits").innerHTML = (plan.limitations || []).length
            ? `<details class="rs-fold"><summary>Limitations of this plan <span>(${plan.limitations.length})</span></summary><ul>${plan.limitations.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : "";
        area.hidden = false;
        await evaluate();
        area.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // Project country / customer standard (static/js/standards.js)
    function stdSummary() {
        const el = $("pj-std-summary");
        const s = window.Standards ? Standards.summaryText() : "";
        if (el) el.innerHTML = s ? `<div class="std-note">${esc(s)}. Each calculation names the standard it follows — confirm they are accepted for this project.</div>` : "";
    }
    document.addEventListener("standards-change", () => {
        if (!plan || area.hidden) return;
        stdSummary();
        if (lastResult) renderCalcs(lastResult);
    });

    // A value with its unit as plain text (for sentences — no unit selector)
    const plain = (v, u) => v == null ? "—" : `${Units.fmt(Units.convert(v, u, Units.displayUnit(u)))} ${Units.displayUnit(u)}`;

    // ── 1. Information needed ────────────────────────────────
    function statusTag(i) {
        if (quotes[i.symbol] && values[i.symbol] !== "" && values[i.symbol] !== undefined) return `<span class="pj-tag have" title="From your text: “${esc(quotes[i.symbol])}”">✓ from your text</span>`;
        if (typical[i.symbol]) return `<span class="pj-tag sug" title="${esc(typical[i.symbol])}">suggested</span>`;
        if (estimated[i.symbol]) return `<span class="pj-tag est" title="${esc(estimated[i.symbol])}">estimate</span>`;
        if (values[i.symbol] !== undefined && values[i.symbol] !== "") return `<span class="pj-tag have">✓ entered</span>`;
        return i.optional ? `<span class="pj-tag opt">optional</span>` : `<span class="pj-tag need">needed</span>`;
    }

    function renderInfo() {
        const have = plan.inputs.filter(i => values[i.symbol] !== undefined && values[i.symbol] !== "").length;
        info.innerHTML = `<p class="field-hint pj-count">You have <strong>${have}</strong> of <strong>${plan.inputs.length}</strong>. Fill in what you can — every calculation that has its information runs straight away.</p>` +
            plan.inputs.map(i => `
            <div class="pj-row${typical[i.symbol] ? " suggested" : ""}${estimated[i.symbol] ? " estimated" : ""}" data-row="${i.symbol}">
                <div class="pj-name">${esc(i.name)} ${statusTag(i)}
                    <div class="pj-src">${typical[i.symbol] ? "Suggested: " + esc(typical[i.symbol])
                        : estimated[i.symbol] ? esc(estimated[i.symbol]) : "Where to get it: " + esc(i.source_hint)}</div>
                    ${i.estimate && !quotes[i.symbol] ? `<button type="button" class="link-btn pj-est-btn" data-est="${i.symbol}">${estimated[i.symbol] ? "Change estimate" : "Don't have it? Estimate it"}</button>` : ""}</div>
                <div class="input-row pj-input"><input type="number" step="any" data-pj="${i.symbol}" value="${esc(shownValue(i))}">${
                    i.unit ? (Units.family(i.unit) ? `<span class="unit-badge u-badge">${Units.unitSelect(i.unit, Units.displayUnit(i.unit))}</span>` : `<span class="unit-badge">${esc(i.unit)}</span>`) : ""}</div>
                <div class="pj-est" id="pj-est-${i.symbol}" hidden></div>
            </div>`).join("");
    }

    // Values are stored in the plan's unit; the box shows them in the engineer's chosen unit
    function shownValue(i) {
        const v = values[i.symbol];
        if (v === undefined || v === null || v === "") return "";
        return String(Number(Units.convert(Number(v), i.unit, Units.displayUnit(i.unit)).toPrecision(6)));
    }
    Units.onChange(() => {
        if (!plan || area.hidden) return;
        renderInfo();
        if (lastResult) renderCalcs(lastResult);
    });

    info.addEventListener("input", e => {
        const k = e.target.dataset.pj;
        if (!k) return;
        const inpDef = plan.inputs.find(x => x.symbol === k);
        values[k] = e.target.value === "" ? "" : Units.convert(Number(e.target.value), Units.displayUnit(inpDef.unit), inpDef.unit);
        delete quotes[k]; delete typical[k]; delete estimated[k];
        const row = e.target.closest(".pj-row");
        row.classList.remove("suggested", "estimated");
        const i = plan.inputs.find(x => x.symbol === k);
        row.querySelector(".pj-tag").outerHTML = statusTag(i);
        row.querySelector(".pj-src").textContent = "Where to get it: " + i.source_hint;
    });
    info.addEventListener("keydown", e => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        if (!e.target.dataset.estIn) calcBtn.click();
    });

    // ── Estimate helpers: work out a value from easier inputs (the tool does the maths) ──
    info.addEventListener("click", async e => {
        const open = e.target.closest("[data-est]");
        if (open) { toggleEstimate(open.dataset.est); return; }
        const use = e.target.closest("[data-est-use]");
        if (use) await useEstimate(use.dataset.estUse);
    });

    function toggleEstimate(sym) {
        const box = $(`pj-est-${sym}`);
        if (!box.hidden) { box.hidden = true; return; }
        const est = plan.inputs.find(i => i.symbol === sym).estimate;
        box.innerHTML = `
            <div class="pj-est-title">${esc(est.title)}</div>
            <div class="field-hint">${esc(est.note)}</div>
            <div class="pj-est-grid">${est.inputs.map(x => {
                const pre = x.from_input && values[x.from_input] !== undefined && values[x.from_input] !== "" ? values[x.from_input]
                          : (x.typical_value ?? "");
                return `<div class="field-group">
                    <label>${esc(x.name)}${x.typical_value != null ? ' <span class="opt-tag">suggested</span>' : ""}</label>
                    <div class="input-row"><input type="number" step="any" data-est-in="${sym}" data-k="${x.symbol}" value="${esc(pre)}">${x.unit ? `<span class="unit-badge">${esc(x.unit)}</span>` : ""}</div>
                    ${x.typical_note ? `<p class="field-hint sug-hint">${esc(x.typical_note)}</p>` : ""}
                </div>`; }).join("")}</div>
            <div class="sz-ai-actions"><button type="button" class="btn-secondary" data-est-use="${sym}">Use this estimate</button>
                <span class="field-hint pj-est-msg" id="pj-est-msg-${sym}"></span></div>`;
        box.hidden = false;
    }

    async function useEstimate(sym) {
        const inp = plan.inputs.find(i => i.symbol === sym), est = inp.estimate;
        const vals = {};
        info.querySelectorAll(`[data-est-in="${sym}"]`).forEach(el => { vals[el.dataset.k] = el.value === "" ? null : Number(el.value); });
        const method = { title: est.title, summary: est.note,
            inputs: est.inputs.map(x => ({ symbol: x.symbol, name: x.name, unit: x.unit })),
            steps: [{ symbol: sym, name: inp.name, unit: inp.unit, expression: est.expression }],
            result_symbols: [sym] };
        const msg = $(`pj-est-msg-${sym}`);
        try {
            const res = await fetch(`${API}/api/evaluate-method`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan: method, values: vals }) });
            const r = await res.json();
            if (r.status === "REQUIREMENTS_INCOMPLETE") { msg.textContent = "Fill in: " + r.missing_inputs.map(m => m.label).join(", "); return; }
            if (r.status !== "CALCULATED") { msg.textContent = (r.errors || ["Could not calculate the estimate."]).join(" "); return; }
            const step = r.steps[0];
            values[sym] = Number(step.result.toPrecision(4));
            delete quotes[sym]; delete typical[sym];
            estimated[sym] = `Estimate — replace with the datasheet value. ${step.substitution}`;
            await evaluate();
        } catch (err) { msg.textContent = err.message || "Could not reach the server."; }
    }

    // ── 2. Calculations ──────────────────────────────────────
    async function evaluate() {
        const vals = Object.fromEntries(plan.inputs.map(i => [i.symbol, values[i.symbol] === undefined || values[i.symbol] === "" ? null : Number(values[i.symbol])]));
        let r;
        try {
            const res = await fetch(`${API}/api/project-evaluate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan, values: vals, include_internet: $("pj-internet").checked }) });
            r = await res.json();
            if (!res.ok) throw new Error(typeof r.detail === "string" ? r.detail : "The plan could not be calculated.");
        } catch (err) {
            calcs.innerHTML = `<div class="sz-note danger">${esc(err.message)}</div>`; return;
        }
        if (r.status !== "EVALUATED") { calcs.innerHTML = `<div class="sz-note danger"><ul>${(r.errors || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`; return; }
        renderInfo();
        renderAsked(r);
        const done = r.calculations.filter(c => c.status === "DONE").length;
        progress.textContent = `${done} of ${r.calculations.length} calculations done`;
        renderCalcs(r);
    }

    // "You asked for": each result the user listed, with its answer or what it is waiting for
    function renderAsked(r) {
        const box = $("pj-asked");
        // Nothing listed by the user → show the main result of every calculation as "Key results"
        const listed = (plan.requested || []).length > 0;
        const stepName = {};
        plan.calculations.forEach(c => (c.steps || []).forEach(s => { stepName[s.symbol] = s.name; }));
        const items = listed ? plan.requested
            : (plan.key_symbols || []).length
                ? plan.key_symbols.filter(sym => stepName[sym]).map(sym => ({ text: stepName[sym], symbol: sym }))
                : plan.calculations.filter(c => c.kind === "formula" && c.steps.length)
                      .map(c => ({ text: c.steps[c.steps.length - 1].name, symbol: c.steps[c.steps.length - 1].symbol }));
        if (!items.length) { box.innerHTML = ""; return; }
        const results = {}, from = {};
        plan.calculations.forEach((c, idx) => {
            const cr = r.calculations[idx];
            (c.steps || []).forEach(s => { from[s.symbol] = { calc: c, res: cr }; });
            (cr.steps || []).forEach(s => { results[s.symbol] = s; });
        });
        const rows = items.map(q => {
            if (!q.symbol) return `<div class="pj-res"><span>${esc(q.text)}</span><strong class="pj-none">not calculated by this plan</strong></div>`;
            const s = results[q.symbol];
            if (s) return `<div class="pj-res"><span>${esc(q.text)}</span><strong>${Units.valueHtml(s.result, s.unit)}</strong></div>`;
            const inp = plan.inputs.find(i => i.symbol === q.symbol);
            if (inp && values[q.symbol] !== undefined && values[q.symbol] !== "")
                return `<div class="pj-res"><span>${esc(q.text)}</span><strong>${Units.valueHtml(Number(values[q.symbol]), inp.unit)}</strong></div>`;
            const f = from[q.symbol];
            const needs = f && f.res.status === "WAITING" ? f.res.waiting_for : [];
            const pill = needs.length ? `<span class="pill-wait" title="Waiting for: ${esc(needs.join(", "))}">needs ${needs.length} more input${needs.length > 1 ? "s" : ""}</span>`
                                      : `<span class="pill-wait">waiting for information</span>`;
            return `<div class="pj-res"><span>${esc(q.text)}</span><strong class="pj-none">${pill}</strong></div>`;
        });
        const done = items.filter(q => q.symbol && results[q.symbol]).length;
        box.innerHTML = `<div class="pj-asked"><div class="pj-asked-head">${listed ? "You asked for" : "Key results"}
            <span class="pj-meter" title="${done} of ${items.length}"><span style="width:${items.length ? Math.round(100 * done / items.length) : 0}%"></span></span>
            <span class="pj-progress">${done} of ${items.length} ${listed ? "answered" : "calculated"}</span></div>${rows.join("")}</div>`;
    }

    const badge = s => ({ DONE: `<span class="data-status MEETS">DONE</span>`, WAITING: `<span class="data-status DISCOVERED">WAITING</span>`,
                          ERROR: `<span class="data-status DOES_NOT_MEET">CHECK INPUTS</span>` }[s] || "");

    function renderCalcs(r) {
        lastResult = r;
        known = {};
        plan.inputs.forEach(i => {
            if (values[i.symbol] !== undefined && values[i.symbol] !== "") known[i.symbol] = { value: Number(values[i.symbol]), unit: i.unit };
        });
        r.calculations.forEach(cr => (cr.steps || []).forEach(s => { known[s.symbol] = { value: s.result, unit: s.unit }; }));
        // keep open "Show working" sections open when redrawing
        const open = [...calcs.querySelectorAll("details.sz-details")].map(d => d.open);
        calcs.innerHTML = plan.calculations.map((c, idx) => card(c, r.calculations[idx], idx + 1)).join("");
        calcs.querySelectorAll("details.sz-details").forEach((d, i) => { if (open[i]) d.open = true; });
    }

    // Under each step: the values it used and its result in the engineer's units, with the exact factor
    const NOT_SYMBOLS = new Set(["sqrt", "exp", "log", "log10", "ln", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
                                 "radians", "degrees", "abs", "min", "max", "ceil", "floor", "pow", "pi", "g"]);
    function inYourUnitsLine(s) {
        const used = [...new Set((s.formula.split("=").slice(1).join("=").match(/[A-Za-z_][A-Za-z0-9_]*/g) || [])
            .filter(x => !NOT_SYMBOLS.has(x) && known[x]))];
        const parts = used.map(x => { const t = Units.inYourUnits(known[x].value, known[x].unit); return t ? `${esc(x)}: ${esc(t)}` : ""; })
            .filter(Boolean);
        const res = Units.inYourUnits(s.result, s.unit);
        if (res) parts.push(`<strong>${esc(s.symbol)} = ${esc(Units.fmt(Units.convert(s.result, s.unit, Units.displayUnit(s.unit))))} ${esc(Units.displayUnit(s.unit))}</strong>
            <span class="u-factor">(${esc(Units.factorText(s.unit, Units.displayUnit(s.unit)))})</span>`);
        return parts.length ? `<div class="u-conv">In your units — ${parts.join(" · ")}</div>` : "";
    }
    function stepUnits(steps) {
        const out = [];
        steps.forEach(s => {
            out.push(s.unit);
            ((s.formula.split("=").slice(1).join("=").match(/[A-Za-z_][A-Za-z0-9_]*/g)) || []).forEach(x => { if (known[x]) out.push(known[x].unit); });
        });
        return out.filter(Boolean);
    }

    function card(c, r, n) {
        let bodyHtml = "";
        if (r.status === "WAITING") {
            bodyHtml = `<div class="pj-wait"><span>Waiting for</span> ${r.waiting_for.map(x => `<span class="need-chip">${esc(x)}</span>`).join("")}</div>`;
        } else if (r.status === "ERROR") {
            bodyHtml = `<div class="sz-note danger"><ul>${r.errors.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
        } else if (c.kind === "formula") {
            bodyHtml = `<div class="pj-results">${r.steps.map(s => `<div class="pj-res"><span>${esc(s.name)}</span><strong>${Units.valueHtml(s.result, s.unit)}</strong></div>`).join("")}</div>
                <details class="sz-details"><summary>Show working <span class="u-note">(the formula uses the calculation's units so the arithmetic can be checked; your units are shown under each step)</span></summary><ol class="sz-steps">${r.steps.map((s, i) => `
                    <li class="sz-stepline"><div class="sz-step-head"><span class="sz-step-n">${i + 1}</span> ${esc(s.name)}</div>
                    ${MathFmt.block(s.formula, "sz-formula")}${MathFmt.block(s.substitution, "sz-subst")}
                    ${inYourUnitsLine(s)}
                    ${s.note ? `<div class="sz-step-note">${esc(s.note)}</div>` : ""}</li>`).join("")}</ol>
                    ${Units.legendHtml(stepUnits(r.steps))}</details>`;
        } else if (c.kind === "bearing_life") {
            const b = r.bearing, u = r.used || {};
            const st = { MEETS: `<span class="data-status MEETS">MEETS</span>`, DOES_NOT_MEET: `<span class="data-status DOES_NOT_MEET">DOES NOT MEET</span>` }[b.status] || "";
            const exp = (b.steps || []).find(s => s.key === "exponent");
            // Every value the check used, then every result, then the working — nothing hidden
            const row = (label, html) => `<tr><td>${esc(label)}</td><td class="num">${html}</td></tr>`;
            const usedRows = [
                row("Bearing type", esc(c.bearing_type === "ball" ? "Ball bearing" : "Roller bearing")),
                u.radial_load_n != null ? row("Radial load Fr", Units.valueHtml(u.radial_load_n, "N")) : "",
                row("Axial load Fa", u.axial_load_n ? Units.valueHtml(u.axial_load_n, "N") : "none"),
                u.speed_rpm != null ? row("Shaft speed n", Units.valueHtml(u.speed_rpm, "rpm")) : "",
                u.required_life_h != null ? row("Required life", Units.valueHtml(u.required_life_h, "h")) : "",
                row("Dynamic load rating C", u.dynamic_rating_kn != null ? Units.valueHtml(u.dynamic_rating_kn, "kN") : "not given — the minimum C is calculated"),
                row("Reliability", "90 % (L10, a₁ = 1)"),
            ].join("");
            const resRows = [
                b.life_h != null ? row(`Expected life L10h (${c.bearing_type} bearing)`, `${Units.valueHtml(b.life_h, "h")} ${st}`) : "",
                b.min_dynamic_rating_kn != null ? row("Minimum dynamic load rating C", `<strong>${Units.valueHtml(b.min_dynamic_rating_kn, "kN")}</strong>`) : "",
                row("Equivalent dynamic load P", Units.valueHtml(b.equivalent_load_n, "N")),
                exp ? row("Life exponent p", esc(exp.substitution.replace(/^p\s*/, ""))) : "",
            ].join("");
            bodyHtml = `<div class="pj-bearing">
                <div><h4>Values used</h4><table class="rs-table">${usedRows}</table></div>
                <div><h4>Results</h4><table class="rs-table">${resRows}</table>
                    ${b.min_dynamic_rating_kn != null ? `<p class="pj-bearing-tip">Choose a bearing whose catalogue C is at least ${esc(plain(b.min_dynamic_rating_kn, "kN"))}.</p>` : ""}
                    ${b.status === "MEETS" ? `<p class="pj-bearing-tip">Expected life is at least the required ${esc(plain(u.required_life_h, "h"))}.</p>` : ""}
                    ${b.status === "DOES_NOT_MEET" ? `<p class="pj-bearing-tip bad">Expected life is below the required ${esc(plain(u.required_life_h, "h"))} — choose a bearing with a higher C.</p>` : ""}</div></div>
                <details class="sz-details" open><summary>Working (${b.steps.length} steps)</summary><ol class="rs-steps">${b.steps.map((s, i) => `
                    <li class="rs-step"><div class="rs-step-n">${i + 1}</div><div class="rs-step-body"><div class="rs-step-name">${esc(s.label)}</div>
                    ${MathFmt.block(s.formula, "rs-formula")}${MathFmt.block(s.substitution, "rs-subst")}</div></li>`).join("")}</ol>
                    ${(b.notes || []).filter(x => !/^Choose a bearing/.test(x)).map(x => `<p class="field-hint" style="margin-top:0.5rem">${esc(x)}</p>`).join("")}</details>`;
        } else {
            const m = r.motors || [];
            const net = r.internet;
            const netHtml = net == null ? "" : `
                <div class="pj-net-head">Internet search ${r.internet_source === "MOCK" ? `<span class="data-status DISCOVERED">SAMPLE DATA — no search key set</span>`
                    : r.internet_source === "UNAVAILABLE" ? `<span class="data-status DOES_NOT_MEET">UNAVAILABLE</span>` : ""}</div>
                ${net.length ? `<div class="pj-results">${net.map(x => `<div class="pj-res"><span>${esc(x.manufacturer)} ${esc(x.product || "")} ${x.part_number ? "· " + esc(x.part_number) : ""}
                        ${x.url ? ` <a class="source-link" href="${esc(x.url)}" target="_blank" rel="noopener">product page</a>` : ""}</span>
                    <strong>${x.output_torque_nm != null ? Units.valueHtml(x.output_torque_nm, "N·m") + " @ " + Units.valueHtml(x.output_speed_rpm, "rpm") + " " : ""}<span class="data-status ${esc(x.status)}">${esc((x.status || "").replace(/_/g, " "))}</span>
                    ${x.fit != null ? `<span class="fit-pill">${x.fit}% fit</span>` : ""}</strong></div>`).join("")}</div>`
                  : `<div class="pj-wait">No internet product met the requirement.</div>`}`;
            bodyHtml = m.length
                ? `<div class="pj-results">${m.map((x, i) => `<div class="pj-res"><span>${i + 1}. ${esc(x.motor)} (${esc(x.motor_maker)}) + ${esc(x.gearbox)} ${x.ratio}:1</span>
                    <strong>${Units.valueHtml(x.output_torque_nm, "N·m")} @ ${Units.valueHtml(x.output_speed_rpm, "rpm")} ${x.fit != null ? `<span class="fit-pill">${x.fit}% fit</span>` : ""}</strong></div>`).join("")}</div>${netHtml}`
                : `<div class="pj-wait">No motor + gearbox in the built-in list can deliver ${esc(plain(r.used.required_torque_nm, "N·m"))} × ${fmt(r.used.service_factor ?? 1)} (service factor) at ${esc(plain(r.used.required_speed_rpm, "rpm"))} on ${esc(plain(r.used.max_voltage_v, "V"))}.
                    Tick "Also search the internet" above, or use these requirements with a supplier.</div>${netHtml}`;
        }
        // The customer's standard when it uses the same method (e.g. ABMA Std 11 = ISO 281), else a regional note
        const eq = window.Standards && c.standard ? Standards.equivalentFor(c.standard, c.bearing_type) : null;
        const stdLine = eq ? eq.note : (window.Standards && c.standard ? Standards.regionalFor(c.standard) : "");
        const noMatch = c.kind === "motor_selection" && r.status === "DONE" && !(r.motors || []).length;
        const tag = noMatch ? `<span class="data-status DATA_INCOMPLETE">NO MATCH IN LIST</span>` : badge(r.status);
        return `<div class="pj-card ${noMatch ? "waiting" : r.status.toLowerCase()}">
            <div class="pj-card-head"><span class="pj-n">${n}</span><div><div class="pj-card-title">${esc(eq ? c.title.replace(/\(ISO 281\)/, `(${eq.name})`) : c.title)} ${tag}</div>
                <div class="pj-card-meta">${esc(c.purpose)}${c.standard ? ` <span class="tag tag-std">${eq ? `${esc(eq.name)} — same method as ${esc(c.standard)}` : esc(c.standard)}</span>` : ""}${c.kind !== "formula" ? ` <span class="tag tag-ok">checked calculation</span>` : ""}</div>
                ${c.note ? `<div class="field-hint">${esc(c.note)}</div>` : ""}
                ${stdLine ? `<div class="std-note">${esc(stdLine)}</div>` : ""}</div></div>
            ${bodyHtml}</div>`;
    }

    calcBtn.addEventListener("click", async () => {
        calcBtn.disabled = true; calcBtn.textContent = "Calculating...";
        try { await evaluate(); } finally { calcBtn.disabled = false; calcBtn.textContent = "Calculate the project"; }
        $("pj-calcs-head").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("pj-reset").addEventListener("click", () => {
        hide(); $("sz-ai-text").value = ""; $("sz-ai-text").focus();
    });

    window.Project = { show, hide };
})();
