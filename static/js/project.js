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

    let plan = null, values = {}, quotes = {}, typical = {}, estimated = {};   // estimated: symbol -> how it was estimated

    function hide() { area.hidden = true; plan = null; values = {}; quotes = {}; typical = {}; estimated = {}; }

    async function show(data) {
        hide();
        plan = data.project;
        plan.inputs.forEach(i => {
            if (i.value !== null && i.value !== undefined) { values[i.symbol] = i.value; quotes[i.symbol] = i.quote; }
            else if (i.typical_value !== null && i.typical_value !== undefined) { values[i.symbol] = i.typical_value; typical[i.symbol] = i.typical_note || "typical value"; }
        });
        const ai = plan.origin === "AI";
        head.innerHTML = `
            <div class="sz-note ${ai ? "ai-method" : "info"}">
                <strong>${ai ? "⚠ Plan and methods chosen by AI — check before use." : "Built-in calculation plan (not yet approved by an engineer)."}</strong>
                ${ai ? "Every number is calculated by the tool from your inputs and every step is shown, but the method must be checked by an engineer." : ""}
                ${ai ? "" : "Motor + gearbox selection and bearing life use the tool's checked calculations."}
            </div>
            <h2 class="pj-title">${esc(plan.title)}</h2>
            <p class="field-hint">${esc(plan.summary)}</p>`;
        renderInfo();
        $("pj-limits").innerHTML = (plan.limitations || []).length
            ? `<div class="sz-note warn"><strong>Limitations of this plan</strong><ul>${plan.limitations.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
        area.hidden = false;
        await evaluate();
        area.scrollIntoView({ behavior: "smooth", block: "start" });
    }

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
    Units.onChange(() => { if (plan && !area.hidden) renderInfo(); });

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
        calcs.innerHTML = plan.calculations.map((c, idx) => card(c, r.calculations[idx], idx + 1)).join("");
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
            const why = f && f.res.status === "WAITING" ? `waiting for: ${f.res.waiting_for.join(", ")}` : "waiting for information";
            return `<div class="pj-res"><span>${esc(q.text)}</span><strong class="pj-none">${esc(why)}</strong></div>`;
        });
        const done = items.filter(q => q.symbol && results[q.symbol]).length;
        box.innerHTML = `<div class="pj-asked"><div class="pj-asked-head">${listed ? "You asked for" : "Key results"} <span class="pj-progress">${done} of ${items.length} ${listed ? "answered" : "calculated"}</span></div>${rows.join("")}</div>`;
    }

    const badge = s => ({ DONE: `<span class="data-status MEETS">DONE</span>`, WAITING: `<span class="data-status DISCOVERED">WAITING</span>`,
                          ERROR: `<span class="data-status DOES_NOT_MEET">CHECK INPUTS</span>` }[s] || "");

    function card(c, r, n) {
        let bodyHtml = "";
        if (r.status === "WAITING") {
            bodyHtml = `<div class="pj-wait">Needs: ${r.waiting_for.map(esc).join(", ")}</div>`;
        } else if (r.status === "ERROR") {
            bodyHtml = `<div class="sz-note danger"><ul>${r.errors.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
        } else if (c.kind === "formula") {
            bodyHtml = `<div class="pj-results">${r.steps.map(s => `<div class="pj-res"><span>${esc(s.name)}</span><strong>${Units.valueHtml(s.result, s.unit)}</strong></div>`).join("")}</div>
                <details class="sz-details"><summary>Show working <span class="u-note">(in the units used for the calculation)</span></summary><ol class="sz-steps">${r.steps.map((s, i) => `
                    <li class="sz-stepline"><div class="sz-step-head"><span class="sz-step-n">${i + 1}</span> ${esc(s.name)}</div>
                    <div class="sz-formula">${esc(s.formula)}</div><div class="sz-subst">${esc(s.substitution)}</div>
                    ${s.note ? `<div class="sz-step-note">${esc(s.note)}</div>` : ""}</li>`).join("")}</ol></details>`;
        } else if (c.kind === "bearing_life") {
            const b = r.bearing;
            const st = { MEETS: badge("DONE").replace("DONE", "MEETS"), DOES_NOT_MEET: `<span class="data-status DOES_NOT_MEET">DOES NOT MEET</span>` }[b.status] || "";
            bodyHtml = `<div class="pj-results">
                ${b.life_h != null ? `<div class="pj-res"><span>Expected life (${esc(c.bearing_type)} bearing)</span><strong>${Units.valueHtml(b.life_h, "h")} ${st}</strong></div>` : ""}
                ${b.min_dynamic_rating_kn != null ? `<div class="pj-res"><span>Minimum dynamic load rating C</span><strong>${Units.valueHtml(b.min_dynamic_rating_kn, "kN")}</strong></div>` : ""}
                <div class="pj-res"><span>Equivalent load P</span><strong>${Units.valueHtml(b.equivalent_load_n, "N")}</strong></div></div>
                <details class="sz-details"><summary>Show working</summary><ol class="sz-steps">${b.steps.map((s, i) => `
                    <li class="sz-stepline"><div class="sz-step-head"><span class="sz-step-n">${i + 1}</span> ${esc(s.label)}</div>
                    <div class="sz-formula">${esc(s.formula)}</div><div class="sz-subst">${esc(s.substitution)}</div></li>`).join("")}</ol>
                    ${(b.notes || []).map(x => `<p class="field-hint">${esc(x)}</p>`).join("")}</details>`;
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
                : `<div class="pj-wait">No motor + gearbox in the built-in list can deliver ${Units.valueHtml(r.used.required_torque_nm, "N·m")} × ${fmt(r.used.service_factor ?? 1)} at ${Units.valueHtml(r.used.required_speed_rpm, "rpm")} on ${Units.valueHtml(r.used.max_voltage_v, "V")}.
                    Tick "Also search the internet" above, or use these requirements with a supplier.</div>${netHtml}`;
        }
        const noMatch = c.kind === "motor_selection" && r.status === "DONE" && !(r.motors || []).length;
        const tag = noMatch ? `<span class="data-status DATA_INCOMPLETE">NO MATCH IN LIST</span>` : badge(r.status);
        return `<div class="pj-card ${noMatch ? "waiting" : r.status.toLowerCase()}">
            <div class="pj-card-head"><span class="pj-n">${n}</span><div><div class="pj-card-title">${esc(c.title)} ${tag}</div>
                <div class="field-hint">${esc(c.purpose)}${c.standard ? ` · <em>${esc(c.standard)}</em>` : ""}${c.kind !== "formula" ? " · checked calculation" : ""}</div>
                ${c.note ? `<div class="field-hint">${esc(c.note)}</div>` : ""}</div></div>
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
