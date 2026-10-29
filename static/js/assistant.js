/* Tesla Mechanical Designs — answers from the main box that are not motor sizing
 *
 *   bearing_life → checked ISO 281 module (/api/bearing-life)
 *   general      → method chosen by the AI, evaluated step by step by the tool
 *                  (/api/evaluate-method). Always labelled "check before use".
 *
 * Motor sizing stays in sizing.js. sizing.js calls window.Assistant.show(data)
 * for the other topics. No engineering maths happens in this file.
 */

(() => {
    const $ = id => document.getElementById(id);
    const area = $("as-area");
    if (!area) return;

    const banner = $("as-banner"), understood = $("as-understood"), neededWrap = $("as-needed-wrap"),
          neededTitle = $("as-needed-title"), form = $("as-form"), calcBtn = $("as-calc"),
          panel = $("as-result-panel"), title = $("as-result-title"), sub = $("as-result-sub"), body = $("as-result");

    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const fmt = x => (x === null || x === undefined) ? "—"
        : Math.abs(x) >= 1e4 ? Math.round(x).toLocaleString() : String(Number(Number(x).toPrecision(4)));
    const post = async (url, payload) => {
        const r = await fetch(`${API}${url}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const d = await r.json();
        if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Some inputs are not valid.");
        return d;
    };

    let topic = null, plan = null;
    let values = {}, quotes = {}, typical = {};   // key -> value / user's words / suggestion note

    // ── Bearing field definitions ────────────────────────────
    const BEARING = {
        bearing_type: { label: "Bearing type", type: "select", options: [["ball", "Ball bearing"], ["roller", "Roller bearing"]] },
        radial_load_n: { label: "Radial load (Fr)", unit: "N", hint: "Load pushing sideways on the bearing." },
        axial_load_n: { label: "Axial load (Fa)", unit: "N", hint: "Load along the shaft. Leave blank if none.", optional: true },
        x_factor: { label: "Radial factor X", hint: "From the bearing catalogue, for your Fa/Fr ratio." },
        y_factor: { label: "Axial factor Y", hint: "From the bearing catalogue, for your Fa/Fr ratio." },
        speed_rpm: { label: "Shaft speed", unit: "rpm" },
        dynamic_rating_kn: { label: "Dynamic load rating (C)", unit: "kN", hint: "From the bearing catalogue. Leave blank and give the required life to get the minimum C instead.", optional: true },
        required_life_h: { label: "Required life", unit: "h", hint: "How many running hours it must last.", optional: true },
        reliability_pct: { label: "Reliability", type: "select", optional: true,
                           options: [["90", "90 % (standard L10)"], ["95", "95 %"], ["96", "96 %"], ["97", "97 %"], ["98", "98 %"], ["99", "99 %"]] },
    };

    // Plan inputs become field definitions too
    const defsFor = () => topic === "bearing_life"
        ? Object.fromEntries(Object.entries(BEARING).map(([k, d]) => [k, { key: k, ...d }]))
        : Object.fromEntries((plan?.inputs || []).map(i => {
            const fromStd = /enter from your copy/i.test(`${i.typical_note || ""} ${i.source_hint || ""}`);
            const note = i.typical_value == null ? (i.typical_note || i.source_hint || "") : "";
            return [i.symbol, { key: i.symbol, label: i.name, unit: i.unit, fromStd,
                hint: note.replace(/\s*[—-]\s*enter from your copy of the standard\.?/i, "") }];
        }));

    function fieldHtml(d, highlight) {
        const v = values[d.key];
        const input = d.type === "select"
            ? `<select data-as-key="${d.key}">${(v === undefined || v === "") ? `<option value="" selected disabled>— choose —</option>` : ""}${
                d.options.map(([o, t]) => `<option value="${o}" ${String(v) === o ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`
            : `<input type="number" step="any" data-as-key="${d.key}" value="${esc(v ?? "")}">`;
        const cls = (highlight ? " missing" : "") + (typical[d.key] ? " suggested" : "");
        return `<div class="field-group${cls}">
            <label>${esc(d.label)}${d.optional ? ' <span class="opt-tag">optional</span>' : ""}</label>
            <div class="input-row">${input}${d.unit ? `<span class="unit-badge">${esc(d.unit)}</span>` : ""}</div>
            ${typical[d.key] ? `<p class="field-hint sug-hint">${esc(typical[d.key])}</p>` : ""}
            ${d.hint ? `<p class="field-hint">${esc(d.hint)}</p>` : ""}
        </div>`;
    }

    const filled = k => values[k] !== undefined && values[k] !== null && values[k] !== "";

    // ── Show / hide ──────────────────────────────────────────
    function hide() {
        window.Project?.hide();
        area.hidden = true; panel.hidden = true;
        topic = null; plan = null; values = {}; quotes = {}; typical = {};
    }

    async function show(data) {
        hide();
        if (data.topic === "project" && data.status === "OK") { await window.Project.show(data); return; }
        topic = data.topic;
        area.hidden = false;
        if (data.status !== "OK") {
            banner.innerHTML = `<div class="sz-note warn"><strong>${esc(data.message || "This question could not be handled.")}</strong>
                ${data.status === "AI_NOT_CONFIGURED" ? `<div class="sz-ai-actions" style="margin-top:0.6rem"><button type="button" class="btn-secondary" data-goto-tab="selection">Open Advanced: Torque &amp; RPM</button></div>` : ""}</div>`;
            understood.innerHTML = ""; neededWrap.hidden = true; calcBtn.hidden = true;
            area.classList.add("as-failed");
            return;
        }
        calcBtn.hidden = false;
        area.classList.remove("as-failed");
        if (topic === "bearing_life") {
            (data.bearing_values || []).forEach(v => { values[v.field] = v.value; quotes[v.field] = v.quote; });
            if (values.reliability_pct !== undefined) values.reliability_pct = String(values.reliability_pct);
            banner.innerHTML = `<div class="as-head">
                <div class="as-head-tags"><span class="tag tag-ok">Checked calculation</span><span class="tag tag-std">${esc(std())}</span></div>
                <h2 class="as-head-title">Bearing life</h2>
                <p class="as-head-sum">Basic rating life of a rolling bearing, built into the tool.</p></div>`;
            calcBtn.textContent = "Calculate bearing life";
        } else {
            plan = data.plan;
            plan.inputs.forEach(i => {
                if (i.value !== null && i.value !== undefined) { values[i.symbol] = i.value; quotes[i.symbol] = i.quote; }
                else if (i.typical_value !== null && i.typical_value !== undefined) {
                    values[i.symbol] = i.typical_value; typical[i.symbol] = i.typical_note || "typical value";
                }
            });
            banner.innerHTML = `<div class="as-head">
                <div class="as-head-tags"><span class="tag tag-ai">AI method — check before use</span><span class="tag tag-std">${esc(std())}</span></div>
                <h2 class="as-head-title">${esc(plan.title)}</h2>
                <p class="as-head-sum">${esc(plan.summary)}</p>
                <p class="as-head-note">The AI chose the method; the tool does every calculation from your numbers and shows each step.</p></div>`;
            calcBtn.textContent = "Calculate";
        }
        await refresh(false);
        area.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // What we understood + only the missing questions
    async function refresh(highlight) {
        const defs = defsFor();
        const given = Object.keys(quotes).filter(k => defs[k] && filled(k));
        understood.innerHTML = given.length
            ? given.map(k => `<span class="sz-chip" title="From your text: “${esc(quotes[k])}”"><span>${esc(defs[k].label)}</span> ${
                esc(defs[k].type === "select" ? (defs[k].options.find(o => o[0] === String(values[k])) || [0, values[k]])[1] : values[k])}${defs[k].unit ? " " + esc(defs[k].unit) : ""}</span>`).join("")
            : `<span class="field-hint">Nothing picked out yet — answer the questions below.</span>`;

        let ask = [], missingCount;
        if (topic === "bearing_life") {
            const r = await post("/api/bearing-life", buildBearing());
            const miss = new Set((r.missing_inputs || []).map(m => m.field));
            ask = Object.keys(defs).filter(k => !quotes[k] && (miss.has(k)
                || (k === "required_life_h" && miss.has("dynamic_rating_kn"))));
            missingCount = miss.size;   // "C or required life" counts as one question
        } else {
            ask = Object.keys(defs).filter(k => !quotes[k] && (!filled(k) || typical[k]));
            missingCount = ask.filter(k => !filled(k)).length;
        }
        const either = topic === "bearing_life" && ask.includes("dynamic_rating_kn") && ask.includes("required_life_h")
            ? `<p class="field-hint" style="grid-column: 1 / -1">Give <strong>either</strong> the bearing's rating C (to get its life) <strong>or</strong> the life you need (to get the minimum C).</p>` : "";
        if (topic === "bearing_life") {
            form.innerHTML = either + ask.map(k => fieldHtml(defs[k], highlight && !filled(k))).join("");
        } else {   // group: what only the engineer knows, factors from the standard, and the AI's suggestions
            const groups = [
                ["Needed", "", ask.filter(k => !typical[k] && !defs[k].fromStd)],
                [`From ${plan.standard || "the standard"}`, "Enter these from your copy of the standard.", ask.filter(k => defs[k].fromStd)],
                ["Suggested — please check", "Typical values the AI suggested. Change them to your material or catalogue data.", ask.filter(k => typical[k])],
            ];
            form.innerHTML = groups.filter(g => g[2].length).map(([h, note, keys]) =>
                `<div class="fg-head"><strong>${esc(h)}</strong>${note ? ` <span>${esc(note)}</span>` : ""}</div>` +
                keys.map(k => fieldHtml(defs[k], highlight && !filled(k))).join("")).join("");
        }
        neededTitle.textContent = missingCount === 0 ? (ask.length ? "Check the suggested values" : "")
            : missingCount === 1 ? "Just one more thing" : `Just ${missingCount} more things`;
        neededWrap.hidden = ask.length === 0;
        return missingCount;
    }

    form.addEventListener("input", e => {
        const k = e.target.dataset.asKey;
        if (!k) return;
        values[k] = e.target.value;
        delete typical[k];
        const g = e.target.closest(".field-group");
        g?.classList.remove("missing", "suggested"); g?.querySelector(".sug-hint")?.remove();
    });
    form.addEventListener("change", async e => {   // a new axial load may bring up X / Y
        if (topic === "bearing_life" && e.target.dataset.asKey === "axial_load_n") await refresh(false);
    });
    form.addEventListener("submit", e => { e.preventDefault(); calcBtn.click(); });
    $("as-reset").addEventListener("click", () => {
        hide();
        $("sz-ai-text").value = ""; $("sz-ai-feedback").hidden = true; $("sz-ai-text").focus();
    });

    function buildBearing() {
        const req = {};
        Object.keys(BEARING).forEach(k => {
            if (!filled(k)) return;
            req[k] = k === "bearing_type" ? values[k] : Number(values[k]);
        });
        return req;
    }

    // ── Calculate ────────────────────────────────────────────
    calcBtn.addEventListener("click", async () => {
        calcBtn.disabled = true;
        const sentStd = std();
        const stale = () => sentStd !== std() || area.hidden;   // the standard changed meanwhile: never show this result
        try {
            if (topic === "bearing_life") {
                const r = await post("/api/bearing-life", buildBearing());
                if (stale()) return;
                if (r.status === "REQUIREMENTS_INCOMPLETE" || r.status === "INVALID_INPUT") {
                    await refresh(true);
                    if (r.errors?.length) showProblems(r.errors);
                    return;
                }
                renderBearing(r);
            } else {
                const vals = Object.fromEntries(plan.inputs.map(i => [i.symbol, filled(i.symbol) ? Number(values[i.symbol]) : null]));
                const r = await post("/api/evaluate-method", { plan, values: vals });
                if (stale()) return;
                if (r.status === "REQUIREMENTS_INCOMPLETE") { await refresh(true); return; }
                if (r.status !== "CALCULATED") { showProblems(r.errors || ["The calculation could not be completed."]); return; }
                renderMethod(r);
            }
        } catch (err) {
            showProblems([err.message || "Could not reach the server."]);
        } finally {
            calcBtn.disabled = false;
        }
    });

    function showProblems(list) {
        title.textContent = "Some values need fixing"; sub.textContent = "";
        body.innerHTML = `<div class="sz-note danger"><ul>${list.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
        panel.hidden = false;
    }

    // Main answer: big number, its name, and a short line under it
    const card = (label, val, unit, subtext, cls = "") => `<div class="rs-key ${cls}"><div class="rs-key-label">${esc(label)}</div>
        <div class="rs-key-val">${Units.family(unit) ? Units.valueHtml(val, unit) : `${fmt(val)} <span class="rs-unit">${esc(unit)}</span>`}</div>
        ${subtext ? `<div class="rs-key-sub">${esc(subtext)}</div>` : ""}</div>`;
    // Each step: what it is, the formula as an engineer writes it, the numbers put in, the result
    const std = () => window.Standards ? Standards.get().customer : "";
    const stepsHtml = steps => `<ol class="rs-steps">${steps.map((s, i) => `
        <li class="rs-step">
            <div class="rs-step-n">${i + 1}</div>
            <div class="rs-step-body">
                <div class="rs-step-name">${esc(s.label || s.name)} <span class="tag tag-std step-std">${esc(std())}</span>${s.note ? `<span class="rs-step-note">${esc(s.note)}</span>` : ""}</div>
                ${MathFmt.block(s.formula, "rs-formula")}
                ${MathFmt.block(s.substitution, "rs-subst")}
                ${Units.stepConversionHtml([], s.symbol || s.key || "", s.result, s.unit)}
            </div>
        </li>`).join("")}</ol>${Units.legendHtml(steps.map(s => s.unit))}`;
    const section = (heading, inner, extra = "") => inner ? `<section class="rs-section"><h3>${esc(heading)}${extra ? ` <span>${esc(extra)}</span>` : ""}</h3>${inner}</section>` : "";
    const details = inner => `<details class="calc-details"><summary>Show calculation details</summary><div class="calc-details-body">${inner}</div></details>`;
    const fold = (heading, items) => items.length ? `<details class="rs-fold"><summary>${esc(heading)} <span>(${items.length})</span></summary><ul>${items.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : "";

    // Every input the calculation used, with where its value came from
    function inputsTable() {
        const defs = defsFor();
        const rows = (plan?.inputs || []).filter(i => filled(i.symbol)).map(i => {
            const d = defs[i.symbol];
            const src = quotes[i.symbol] ? `<span class="src src-you" title="From your text: “${esc(quotes[i.symbol])}”">Your text</span>`
                : typical[i.symbol] ? `<span class="src src-sug" title="${esc(typical[i.symbol])}">AI suggestion</span>`
                : d.fromStd ? `<span class="src src-std" title="${esc(d.hint)}">From the standard</span>`
                : `<span class="src">Entered</span>`;
            const val = Units.family(i.unit) ? Units.valueHtml(Number(values[i.symbol]), i.unit) : `${fmt(Number(values[i.symbol]))} ${esc(i.unit || "")}`;
            return `<tr><td>${esc(i.name)} <span class="rs-sym">${MathFmt.html(i.symbol)}</span></td><td class="num">${val}</td><td>${src}</td></tr>`;
        });
        return rows.length ? `<table class="rs-table"><thead><tr><th>Input</th><th class="num">Value</th><th>Source</th></tr></thead><tbody>${rows.join("")}</tbody></table>` : "";
    }

    // Redraw the last result when the units change, so "in your units" lines follow
    let lastShown = null;
    function redraw() {
        if (!lastShown || panel.hidden) return;
        const open = [...body.querySelectorAll("details")].map(d => d.open);
        lastShown[0](lastShown[1], true);
        body.querySelectorAll("details").forEach((d, i) => { if (open[i]) d.open = true; });
    }
    Units.onChange(redraw);
    const usedLine = detail => window.Standards ? Standards.usedLine(detail) : "";

    function renderBearing(r, quiet = false) {
        lastShown = [renderBearing, r];
        const badge = { MEETS: "MEETS", DOES_NOT_MEET: "DOES_NOT_MEET" }[r.status];
        title.innerHTML = r.min_dynamic_rating_kn != null ? "Minimum bearing rating needed"
            : `Bearing life${badge ? ` &nbsp;<span class="data-status ${badge}">${badge.replace(/_/g, " ")}</span>` : ""}`;
        sub.textContent = "Basic rating life — checked calculation built into the tool.";
        const named = t => String(t).replace(/ISO 281/g, std() || "ISO 281");
        body.innerHTML = `
            <div class="rs-keys">
                ${r.life_h != null ? card("Expected life", r.life_h, "h", `at ${values.reliability_pct || 90} % reliability`, "main") : ""}
                ${r.min_dynamic_rating_kn != null ? card("Minimum rating C", r.min_dynamic_rating_kn, "kN", "choose a bearing with at least this C", "main") : ""}
                ${card("Equivalent load P", r.equivalent_load_n, "N")}
            </div>
            ${usedLine("basic rating life")}
            ${(() => { const eq = window.Standards?.equivalentFor("ISO 281", values.bearing_type);
                       return eq?.note && /covers/.test(eq.note) ? `<div class="std-note">${esc(eq.note.replace(/^.*?(Note:)/, "$1"))}</div>` : ""; })()}
            ${details(section("Calculation", stepsHtml(r.steps), `${r.steps.length} steps`))}
            ${fold("Notes", (r.notes || []).map(named))}`;
        panel.hidden = false;
        if (!quiet) panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function renderMethod(r, quiet = false) {
        lastShown = [renderMethod, r];
        title.textContent = plan.title;
        sub.innerHTML = `<span class="tag tag-ai">AI method — check before use</span>`;
        const suggested = Object.keys(typical).filter(filled).length;
        body.innerHTML = `
            <div class="rs-keys">${r.results.map(s => card(s.name, s.result, s.unit, "", "main")).join("")}</div>
            ${usedLine(plan.standard && plan.standard !== std() ? plan.standard : "")}
            <div class="rs-check"><strong>Check before use.</strong> The AI wrote these formulas from ${esc(std())}; the tool calculated every number.
                Verify the method, units${suggested ? ` and the ${suggested} AI-suggested value${suggested > 1 ? "s" : ""}` : ""} before relying on the result.</div>
            ${details(section("Inputs used", inputsTable()) + section("Calculation", stepsHtml(r.steps), `${r.steps.length} steps`))}
            ${fold("Limitations of this method", plan.limitations || [])}`;
        panel.hidden = false;
        if (!quiet) panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // Buttons elsewhere (e.g. "Open Advanced: Torque & RPM") switch tabs
    document.addEventListener("click", e => {
        const t = e.target.closest("[data-goto-tab]");
        if (!t) return;
        document.querySelector(`.tab-btn[data-tab="${t.dataset.gotoTab}"]`)?.click();
        window.scrollTo({ top: 0, behavior: "smooth" });
    });

    window.Assistant = { show, hide };
})();
