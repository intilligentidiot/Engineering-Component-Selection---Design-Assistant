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
        : Object.fromEntries((plan?.inputs || []).map(i => [i.symbol, { key: i.symbol, label: i.name, unit: i.unit }]));

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
            ${typical[d.key] ? `<p class="field-hint sug-hint">Suggested by the AI: ${esc(typical[d.key])}</p>` : ""}
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
                <div class="sz-ai-actions" style="margin-top:0.6rem"><button type="button" class="btn-secondary" data-goto-tab="selection">Open Advanced: Torque &amp; RPM</button></div></div>`;
            understood.innerHTML = ""; neededWrap.hidden = true; calcBtn.hidden = true;
            return;
        }
        calcBtn.hidden = false;
        if (topic === "bearing_life") {
            (data.bearing_values || []).forEach(v => { values[v.field] = v.value; quotes[v.field] = v.quote; });
            if (values.reliability_pct !== undefined) values.reliability_pct = String(values.reliability_pct);
            banner.innerHTML = `<div class="sz-note info"><strong>Bearing life check — ISO 281.</strong> ${esc(data.reason)}
                This is a checked calculation built into the tool.</div>`;
            calcBtn.textContent = "Calculate bearing life";
        } else {
            plan = data.plan;
            plan.inputs.forEach(i => {
                if (i.value !== null && i.value !== undefined) { values[i.symbol] = i.value; quotes[i.symbol] = i.quote; }
                else if (i.typical_value !== null && i.typical_value !== undefined) {
                    values[i.symbol] = i.typical_value; typical[i.symbol] = i.typical_note || "typical value";
                }
            });
            banner.innerHTML = `<div class="sz-note ai-method">
                <strong>⚠ Method chosen by AI — check before use.</strong>
                The tool has no checked calculation for this yet, so the AI chose the method below. The tool does all the
                arithmetic itself from your numbers and shows every step, but the method and formulas must be checked by an engineer.
                <div class="as-plan-title">${esc(plan.title)}${plan.standard ? ` <span>· ${esc(plan.standard)}</span>` : ""}</div>
                <div>${esc(plan.summary)}</div></div>`;
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
        form.innerHTML = either + ask.map(k => fieldHtml(defs[k], highlight && !filled(k))).join("");
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
        try {
            if (topic === "bearing_life") {
                const r = await post("/api/bearing-life", buildBearing());
                if (r.status === "REQUIREMENTS_INCOMPLETE" || r.status === "INVALID_INPUT") {
                    await refresh(true);
                    if (r.errors?.length) showProblems(r.errors);
                    return;
                }
                renderBearing(r);
            } else {
                const vals = Object.fromEntries(plan.inputs.map(i => [i.symbol, filled(i.symbol) ? Number(values[i.symbol]) : null]));
                const r = await post("/api/evaluate-method", { plan, values: vals });
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

    const card = (label, val, unit, subtext, cls = "") => `<div class="sz-req ${cls}"><div class="sz-req-label">${esc(label)}</div><div class="sz-req-val">${fmt(val)} <span>${esc(unit)}</span></div>${subtext ? `<div class="sz-req-sub">${esc(subtext)}</div>` : ""}</div>`;
    const stepsHtml = steps => `<ol class="sz-steps">${steps.map((s, i) => `
        <li class="sz-stepline">
            <div class="sz-step-head"><span class="sz-step-n">${i + 1}</span> ${esc(s.label || s.name)}</div>
            <div class="sz-formula">${esc(s.formula)}</div>
            <div class="sz-subst">${esc(s.substitution)}</div>
            ${s.note ? `<div class="sz-step-note">${esc(s.note)}</div>` : ""}
        </li>`).join("")}</ol>`;
    const typicalUsed = () => Object.entries(typical).filter(([k]) => filled(k))
        .map(([k, note]) => `${(defsFor()[k] || { label: k }).label}: ${values[k]} — ${note}`);
    const list = (items, cls, heading) => items.length ? `<div class="sz-note ${cls}"><strong>${esc(heading)}</strong><ul>${items.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";

    function renderBearing(r) {
        const badge = { MEETS: "MEETS", DOES_NOT_MEET: "DOES_NOT_MEET" }[r.status];
        title.innerHTML = r.min_dynamic_rating_kn != null ? "Minimum bearing rating needed"
            : `Bearing life${badge ? ` &nbsp;<span class="data-status ${badge}">${badge.replace(/_/g, " ")}</span>` : ""}`;
        sub.textContent = "ISO 281 basic rating life — checked calculation built into the tool.";
        body.innerHTML = `
            <div class="sz-req-grid main">
                ${r.life_h != null ? card("Expected life", r.life_h, "h", `at ${values.reliability_pct || 90} % reliability`, "key") : ""}
                ${r.min_dynamic_rating_kn != null ? card("Minimum rating C", r.min_dynamic_rating_kn, "kN", "look for a bearing with at least this C", "key") : ""}
                ${card("Equivalent load P", r.equivalent_load_n, "N")}
            </div>
            ${list(r.notes || [], "info", "Notes")}
            <details class="sz-details"><summary>Show the full calculation (${r.steps.length} steps)</summary>${stepsHtml(r.steps)}</details>`;
        panel.hidden = false;
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function renderMethod(r) {
        title.innerHTML = `${esc(plan.title)} <span class="data-status DISCOVERED">AI METHOD — CHECK</span>`;
        sub.textContent = plan.standard ? `Method: ${plan.standard} (chosen by AI). Numbers calculated by the tool from your inputs.`
                                        : "Method chosen by AI. Numbers calculated by the tool from your inputs.";
        body.innerHTML = `
            <div class="sz-req-grid main">${r.results.map(s => card(s.name, s.result, s.unit, "", "key")).join("")}</div>
            <div class="sz-note ai-method"><strong>⚠ Check before use.</strong> The formulas below were chosen by the AI, not
                taken from a checked module. Every number was calculated by the tool — verify the method and units against the
                standard before relying on the result.</div>
            ${list(typicalUsed(), "info", "Typical values suggested by the AI that were used — please check")}
            ${list(plan.limitations || [], "warn", "Limitations of this method")}
            <details class="sz-details" open><summary>Show the full calculation (${r.steps.length} steps)</summary>${stepsHtml(r.steps)}</details>`;
        panel.hidden = false;
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
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
