/* Tesla Mechanical Designs — Bearing life check (ISO 281 basic rating life)
 *
 * Collects loads, speed and the catalogue rating (or required life) and asks
 * /api/bearing-life for the result with the full calculation. No maths here.
 */

(() => {
    const form = document.getElementById("bearing-form");
    if (!form) return;

    const $ = id => document.getElementById(id);
    const fields = $("br-fields"), panel = $("br-result-panel"), title = $("br-result-title"),
          sub = $("br-result-sub"), body = $("br-result");
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const fmt = x => (x === null || x === undefined) ? "—"
        : Math.abs(x) >= 1e4 ? Math.round(x).toLocaleString() : String(Number(Number(x).toPrecision(4)));

    const values = { reliability_pct: "90" };
    let missing = new Set();

    const defs = () => {
        const f = [
            { key: "bearing_type", label: "Bearing type", type: "select", options: [["ball", "Ball bearing"], ["roller", "Roller bearing"]] },
            { key: "speed_rpm", label: "Shaft speed", unit: "rpm" },
            { key: "radial_load_n", label: "Radial load (Fr)", unit: "N", hint: "Load pushing sideways on the bearing." },
            { key: "axial_load_n", label: "Axial load (Fa)", unit: "N", hint: "Load along the shaft. Leave blank if none.", optional: true },
        ];
        if (Number(values.axial_load_n) > 0) f.push(
            { key: "x_factor", label: "Radial factor X", hint: "From the bearing catalogue, for your Fa/Fr ratio." },
            { key: "y_factor", label: "Axial factor Y", hint: "From the bearing catalogue, for your Fa/Fr ratio." });
        f.push(
            { key: "dynamic_rating_kn", label: "Dynamic load rating (C)", unit: "kN", hint: "From the bearing catalogue. Leave blank to find the minimum C you need.", optional: true },
            { key: "required_life_h", label: "Required life", unit: "h", hint: "How many running hours it must last.", optional: true },
            { key: "reliability_pct", label: "Reliability", type: "select",
              options: [["90", "90 % (standard L10)"], ["95", "95 %"], ["96", "96 %"], ["97", "97 %"], ["98", "98 %"], ["99", "99 %"]] });
        return f;
    };

    function render() {
        fields.innerHTML = defs().map(d => {
            const v = values[d.key];
            const input = d.type === "select"
                ? `<select data-key="${d.key}">${!v ? `<option value="" selected disabled>— choose —</option>` : ""}${
                    d.options.map(([o, t]) => `<option value="${o}" ${String(v) === o ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>`
                : `<input type="number" step="any" data-key="${d.key}" value="${esc(v ?? "")}">`;
            return `<div class="field-group${missing.has(d.key) ? " missing" : ""}">
                <label>${esc(d.label)}${d.optional ? ' <span class="opt-tag">optional</span>' : ""}</label>
                <div class="input-row">${input}${d.unit ? `<span class="unit-badge">${d.unit}</span>` : ""}</div>
                ${d.hint ? `<p class="field-hint">${esc(d.hint)}</p>` : ""}
            </div>`;
        }).join("");
    }

    form.addEventListener("input", e => {
        const k = e.target.dataset.key;
        if (!k) return;
        values[k] = e.target.value;
        missing.delete(k);
        e.target.closest(".field-group")?.classList.remove("missing");
        if (k === "axial_load_n") {   // X / Y appear only when there is an axial load
            const had = fields.querySelector('[data-key="x_factor"]') !== null;
            if (had !== (Number(values.axial_load_n) > 0)) { render(); fields.querySelector('[data-key="axial_load_n"]').focus(); }
        }
    });
    form.addEventListener("reset", () => setTimeout(() => {
        Object.keys(values).forEach(k => delete values[k]);
        values.reliability_pct = "90"; missing.clear(); panel.hidden = true; render();
    }));

    form.addEventListener("submit", async e => {
        e.preventDefault();
        const req = {};
        defs().forEach(d => {
            const v = values[d.key];
            if (v === undefined || v === "") return;
            req[d.key] = d.key === "bearing_type" ? v : Number(v);
        });
        let r;
        try {
            const res = await fetch(`${API}/api/bearing-life`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
            r = await res.json();
            if (!res.ok) throw new Error(typeof r.detail === "string" ? r.detail : "Some inputs are not valid.");
        } catch (err) {
            title.textContent = "Could not calculate"; sub.textContent = err.message; body.innerHTML = ""; panel.hidden = false; return;
        }
        if (r.status === "REQUIREMENTS_INCOMPLETE" || r.status === "INVALID_INPUT") {
            missing = new Set((r.missing_inputs || []).map(m => m.field));
            render();
            title.textContent = r.status === "INVALID_INPUT" ? "Some values need fixing" : "A few more details are needed";
            sub.textContent = "Nothing is guessed — C, X and Y must come from the bearing catalogue.";
            body.innerHTML = `${(r.missing_inputs || []).length ? `<div class="sz-note warn"><strong>Missing:</strong><ul>${r.missing_inputs.map(m => `<li>${esc(m.label)}</li>`).join("")}</ul></div>` : ""}
                ${(r.errors || []).length ? `<div class="sz-note danger"><strong>Please correct:</strong><ul>${r.errors.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}`;
            panel.hidden = false;
            return;
        }

        const card = (label, val, unit, subtext, cls = "") => `<div class="sz-req ${cls}"><div class="sz-req-label">${label}</div><div class="sz-req-val">${fmt(val)} <span>${unit}</span></div>${subtext ? `<div class="sz-req-sub">${subtext}</div>` : ""}</div>`;
        const badge = { MEETS: "MEETS", DOES_NOT_MEET: "DOES_NOT_MEET" }[r.status];
        title.innerHTML = r.min_dynamic_rating_kn != null ? "Minimum bearing rating needed"
            : `Bearing life${badge ? ` &nbsp;<span class="data-status ${badge}">${badge.replace(/_/g, " ")}</span>` : ""}`;
        sub.textContent = "ISO 281 basic rating life — every step is shown below.";
        body.innerHTML = `
            <div class="sz-req-grid main">
                ${r.life_h != null ? card("Expected life", r.life_h, "h", `at ${values.reliability_pct} % reliability`, "key") : ""}
                ${r.min_dynamic_rating_kn != null ? card("Minimum rating C", r.min_dynamic_rating_kn, "kN", "look for a bearing with at least this C", "key") : ""}
                ${card("Equivalent load P", r.equivalent_load_n, "N")}
            </div>
            ${(r.notes || []).length ? `<div class="sz-note info"><ul>${r.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul></div>` : ""}
            <details class="sz-details" open>
                <summary>Show the full calculation (${r.steps.length} steps)</summary>
                <ol class="sz-steps">${r.steps.map((s, i) => `
                    <li class="sz-stepline">
                        <div class="sz-step-head"><span class="sz-step-n">${i + 1}</span> ${esc(s.label)}</div>
                        <div class="sz-formula">${esc(s.formula)}</div>
                        <div class="sz-subst">${esc(s.substitution)}</div>
                        ${s.note ? `<div class="sz-step-note">${esc(s.note)}</div>` : ""}
                    </li>`).join("")}</ol>
            </details>`;
        panel.hidden = false;
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    // Buttons elsewhere (e.g. "Open Bearing Life") switch tabs
    document.addEventListener("click", e => {
        const t = e.target.closest("[data-goto-tab]");
        if (!t) return;
        document.querySelector(`.tab-btn[data-tab="${t.dataset.gotoTab}"]`)?.click();
        window.scrollTo({ top: 0, behavior: "smooth" });
    });

    render();
})();
