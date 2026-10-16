/* Tesla Mechanical Designs — Stage 8: Application-based sizing (primary workflow)
 *
 * Simple view:  describe the machine → "what we understood" → answer only the
 *               missing questions → Calculate (pressing Calculate is the user's
 *               confirmation of the values read from their text).
 * Full form:    every field, with optional ones folded under "More details".
 *
 * The backend does all the work: /api/parse-sizing reads the text, /api/size
 * calculates the requirement (and reports what is missing), /api/recommend
 * selects components. No engineering maths happens in this file.
 */

(() => {
    const sizingForm  = document.getElementById("sizing-form");
    if (!sizingForm) return;

    const $ = id => document.getElementById(id);
    const szBtn = $("sz-submit-btn"), szSpinner = $("sz-spinner");
    const proofPanel = $("sz-proof-panel"), proofTitle = $("sz-proof-title"), proofSub = $("sz-proof-sub"), proofBody = $("sz-proof");
    const appSelect = $("sz-application");
    const aiBtn = $("sz-ai-btn"), aiText = $("sz-ai-text"), aiFeedback = $("sz-ai-feedback");
    const guided = $("sz-guided"), review = $("sz-review"), understood = $("sz-understood");
    const neededWrap = $("sz-needed-wrap"), needed = $("sz-needed"), neededTitle = $("sz-needed-title");
    const full = $("sz-full"), run = $("sz-run"), toggleFull = $("sz-toggle-full"), internet = $("sz-internet");

    const DEFAULT_VALUES = { "part.quantity": 1, "limits.speed_tolerance_pct": 50, "limits.top_n": 5 };
    // Current form values, keyed by request path (e.g. "params.speed_m_s")
    const values = { ...DEFAULT_VALUES };
    let missingPaths = new Set();
    // Values read from the user's text (path -> the user's own words); removed when the user edits that field
    const aiQuotes = new Map();
    let appConfirmed = false;      // machine type stated in the text or picked by the user
    // Values filled from the suggestion list (path -> note); removed when the user edits that field
    const suggested = new Map();
    let machineAsWritten = null;   // the user's own name for the machine, e.g. "belt feeder"
    let machineExplanation = null; // why it was treated as that motion (from the AI)
    let mode = "start";            // start | review | full

    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    // 4 significant figures, without dropping the zeros of whole numbers (2000 stays 2000)
    const fmt = x => (x === null || x === undefined) ? "—"
        : Math.abs(x) >= 1e4 ? Math.round(x).toLocaleString() : String(Number(Number(x).toPrecision(4)));
    const post = async (url, body) => {
        const r = await fetch(`${API}${url}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        const data = await r.json();
        if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Some inputs are not valid.");
        return data;
    };

    // ── Field definitions ────────────────────────────────────
    const num = (path, label, unit, hint, extra = {}) => ({ path, label, unit, hint, type: "number", ...extra });
    const opt = (path, label, unit, hint) => num(path, label, unit, hint, { optional: true });
    const sel = (path, label, options, hint, extra = {}) => ({ path, label, options, hint, type: "select", rerender: true, ...extra });

    const speed  = label => num("params.speed_m_s", label, "m/s", "How fast it moves at full speed.");
    const accel  = num("params.accel_time_s", "Time to reach full speed", "s", "How quickly it gets up to speed from standing still.");
    const effOpt = opt("params.drive_efficiency", "Extra drive stage efficiency", "0–1", "Only if a chain/belt sits between the gearbox and the machine.");
    const procF  = opt("params.process_force_n", "Process force", "N", "Pressing, cutting or pushing force during the move.");

    const materialFields = () => [
        { path: "material.name", label: "Material name", type: "text", hint: "For example: polyurethane, steel, PET film.", optional: true },
        num("material.density_kg_m3", "Material density", "kg/m³", "From the material datasheet. Needed to work out the weight.",
            { optional: values["part.shape"] === "mass" && values["_app"] !== "winding" }),
        sel("material.hardness_scale", "Hardness scale", [["", "— not given —"], ["Shore A", "Shore A"], ["Shore D", "Shore D"], ["Other", "Other"]],
            "Recorded for reference only.", { optional: true, rerender: false }),
        opt("material.hardness_value", "Hardness value", "", "Shown in the report but not used in the calculation."),
    ];

    const partFields = () => {
        const shape = values["part.shape"];
        const f = [sel("part.shape", "What do you know about the part?", [
            ["block", "Its size — rectangular block"], ["cylinder", "Its size — round bar / cylinder"], ["tube", "Its size — tube / pipe"],
            ["sphere", "Its size — ball"], ["volume", "Its volume (from CAD)"], ["mass", "Its weight"],
        ], "Weight is easiest if you know it.")];
        if (shape === "block") f.push(num("part.length_mm", "Length", "mm"), num("part.width_mm", "Width", "mm"), num("part.height_mm", "Height", "mm"));
        if (shape === "cylinder") f.push(num("part.diameter_mm", "Diameter", "mm"), num("part.length_mm", "Length", "mm"));
        if (shape === "tube") f.push(num("part.outer_diameter_mm", "Outer diameter", "mm"), num("part.inner_diameter_mm", "Inner diameter", "mm"), num("part.length_mm", "Length", "mm"));
        if (shape === "sphere") f.push(num("part.diameter_mm", "Diameter", "mm"));
        if (shape === "volume") f.push(num("part.volume_cm3", "Volume", "cm³"));
        if (shape === "mass") f.push(num("part.mass_kg", "Weight of one part", "kg"));
        f.push(num("part.quantity", "Number of parts moved at once", "pcs", "All parts on the belt / table / carriage at the same time."));
        f.push(opt("part.carrier_mass_kg", "Pallet / fixture / carriage weight", "kg", "Anything else that moves with the parts."));
        return f;
    };

    const appFields = () => {
        const app = values["_app"];
        if (app === "conveyor") return [
            speed("Belt speed"), accel,
            num("params.drive_diameter_mm", "Drive pulley / roller diameter", "mm"),
            num("params.incline_deg", "Incline angle", "deg", "Enter 0 for a flat conveyor."),
            num("params.friction_coefficient", "Friction coefficient", "μ", "How much the belt drags on its bed. Ask your belt/roller supplier — it is never guessed."),
            opt("params.belt_mass_kg", "Belt / chain weight", "kg"),
            opt("params.extra_force_n", "Extra resisting force", "N", "Scrapers, pushers, product drag."),
            effOpt,
        ];
        if (app === "hoist") return [
            speed("Lifting speed"), accel,
            num("params.drum_diameter_mm", "Drum diameter (to rope centre)", "mm"),
            opt("params.rope_falls", "Number of rope falls", "", "1 for a single line."),
            opt("params.rope_efficiency", "Rope / pulley efficiency", "0–1"),
            opt("params.hook_mass_kg", "Hook / carriage weight", "kg"),
            opt("params.counterweight_kg", "Counterweight", "kg"),
        ];
        if (app === "rotary_table") {
            const arr = values["params.load_arrangement"], mode_ = values["params.motion_mode"];
            const f = [sel("params.load_arrangement", "How the load sits on the table", [
                ["parts_at_radius", "Parts placed around a circle"], ["solid_disc", "One solid round load in the centre"],
                ["custom_inertia", "I know the load inertia (from CAD)"],
            ], "")];
            if (arr === "custom_inertia") f.push(num("params.load_inertia_kg_m2", "Load inertia", "kg·m²"));
            else if (arr) f.push(num("params.load_radius_mm", arr === "solid_disc" ? "Load radius" : "Radius of the circle of parts", "mm"));
            f.push(sel("params.motion_mode", "How it moves", [["continuous", "Turns continuously"], ["index", "Moves in steps (indexing)"]], ""));
            if (mode_ === "index") f.push(num("params.index_angle_deg", "Angle per step", "deg"), num("params.index_time_s", "Time for one step", "s"));
            else if (mode_ === "continuous") f.push(num("params.target_speed_rpm", "Table speed", "rpm"), accel);
            f.push(opt("params.table_inertia_kg_m2", "Table's own inertia", "kg·m²", "From CAD. Leave blank only if the table is very light."));
            f.push(opt("params.friction_torque_nm", "Bearing friction torque", "N·m"), effOpt);
            return f;
        }
        if (app === "screw_axis") return [
            speed("Travel speed"), accel,
            num("params.axis_angle_deg", "Axis angle", "deg", "0 = horizontal, 90 = vertical."),
            num("params.guide_friction", "Guide friction coefficient", "μ", "From the linear guide datasheet."),
            num("params.screw_lead_mm", "Screw lead", "mm/turn", "How far it moves per turn of the screw."),
            num("params.screw_efficiency", "Screw efficiency", "0–1", "From the screw datasheet. Never assumed."),
            opt("params.screw_inertia_kg_m2", "Screw inertia", "kg·m²"),
            procF,
        ];
        if (app === "rack_pinion_axis") return [
            speed("Travel speed"), accel,
            num("params.axis_angle_deg", "Axis angle", "deg", "0 = horizontal, 90 = vertical."),
            num("params.guide_friction", "Guide friction coefficient", "μ", "From the linear guide datasheet."),
            num("params.pinion_diameter_mm", "Pinion / pulley pitch diameter", "mm"),
            procF, effOpt,
        ];
        if (app === "winding") return [
            num("params.web_tension_n", "Web tension", "N", "Set by your process or material supplier."),
            speed("Line speed"), accel,
            num("params.core_diameter_mm", "Core diameter", "mm"),
            num("params.full_roll_diameter_mm", "Full roll diameter", "mm"),
            num("params.roll_width_mm", "Roll width", "mm"),
            opt("params.core_inertia_kg_m2", "Core / shaft inertia", "kg·m²"),
        ];
        return [];
    };

    const dutyFields = () => {
        const app = values["_app"];
        const index = app === "rotary_table" && values["params.motion_mode"] === "index";
        const f = [
            sel("duty.load_class", "How smooth is the work?", [
                ["uniform", "Smooth — steady, even load"], ["moderate", "Some bumps or frequent starts"], ["heavy", "Heavy shocks or jams"],
            ], "Used to choose the safety margin.", { rerender: false }),
            num("duty.hours_per_day", "Running hours per day", "h"),
            opt("duty.service_factor_override", "Service factor override", "SF", "Leave blank to use the standard table."),
        ];
        if (app !== "winding" && !index) f.push(opt("duty.run_time_s", "Run time per cycle", "s", "Only if it stops and starts repeatedly."));
        if (app !== "winding") f.push(opt("duty.dwell_time_s", "Stopped time per cycle", "s", index ? "Pause between steps." : "Only used together with run time."));
        return f;
    };

    const limitFields = () => [
        num("limits.max_voltage_v", "Supply voltage (maximum)", "V", "For example 24 V or 48 V."),
        opt("limits.speed_tolerance_pct", "Allowed extra speed", "%", "How much faster than required the drive may run (default 50 %)."),
        opt("limits.top_n", "Results to show", "#"),
    ];

    // ── Field rendering ──────────────────────────────────────
    function fieldHtml(d) {
        const v = values[d.path];
        const cls = (missingPaths.has(d.path) ? " missing" : "") + (aiQuotes.has(d.path) ? " ai-filled" : "")
                  + (suggested.has(d.path) ? " suggested" : "");
        const lbl = `${esc(d.label)}${d.optional ? ' <span class="opt-tag">optional</span>' : ""}`;
        const aiHint = aiQuotes.has(d.path) ? `<p class="field-hint ai-hint">From your text: “${esc(aiQuotes.get(d.path))}”</p>` : "";
        let input;
        if (d.type === "select") {
            const empty = v === undefined || v === null || v === "";
            const placeholder = (!d.optional && empty) ? `<option value="" selected disabled>— choose —</option>` : "";
            input = `<select data-path="${d.path}" ${d.rerender ? 'data-rerender="1"' : ""}>${placeholder}${
                d.options.map(([val, txt]) => `<option value="${esc(val)}" ${String(v ?? "") === val ? "selected" : ""}>${esc(txt)}</option>`).join("")}</select>`;
        } else {
            input = `<input type="${d.type}" data-path="${d.path}" step="any" value="${esc(v ?? "")}">`;
        }
        return `
            <div class="field-group${cls}" data-field="${d.path}">
                <label>${lbl}</label>
                <div class="input-row">${input}${d.unit ? `<span class="unit-badge">${esc(d.unit)}</span>` : ""}</div>
                ${aiHint}
                ${suggested.has(d.path) ? `<p class="field-hint sug-hint">Suggested: ${esc(suggested.get(d.path))}</p>` : ""}
                ${d.hint && !suggested.has(d.path) ? `<p class="field-hint">${esc(d.hint)}</p>` : ""}
            </div>`;
    }

    const isFilled = d => { const v = values[d.path]; return v !== undefined && v !== null && String(v) !== ""; };

    let visible = [];
    function render() {
        values["_app"] = appSelect.value;
        const app = values["_app"];
        const hidePart = app === "winding" || (app === "rotary_table" && values["params.load_arrangement"] === "custom_inertia");
        $("sz-part-block").hidden = hidePart;
        const off = hidePart ? 1 : 0;
        $("sz-motion-num").textContent = 4 - off;
        $("sz-duty-num").textContent = 5 - off;
        $("sz-limits-num").textContent = 6 - off;

        const groups = [
            ["sz-material-fields", materialFields()],
            ["sz-part-fields", hidePart ? [] : partFields()],
            ["sz-app-fields", appFields()],
            ["sz-duty-fields", dutyFields()],
            ["sz-limit-fields", limitFields()],
        ];
        visible = [];
        groups.forEach(([id, defs]) => {
            const req = defs.filter(d => !d.optional), extra = defs.filter(d => d.optional);
            const open = extra.some(d => isFilled(d) || missingPaths.has(d.path)) ? "open" : "";
            $(id).innerHTML = req.map(fieldHtml).join("") + (extra.length ? `
                <details class="sz-more" ${open}>
                    <summary>More details (optional) — ${extra.length}</summary>
                    <div class="form-grid">${extra.map(fieldHtml).join("")}</div>
                </details>` : "");
            visible.push(...defs);
        });
    }

    // ── Mode switching ───────────────────────────────────────
    function setMode(m) {
        mode = m;
        guided.hidden = m === "full";
        review.hidden = m !== "review";
        full.hidden = m !== "full";
        run.hidden = m === "start";
        toggleFull.textContent = m === "full" ? "Back to simple view" : "Edit all details";
    }

    toggleFull.addEventListener("click", async () => {
        if (mode === "full") { setMode(aiQuotes.size || appConfirmed ? "review" : "start"); if (mode === "review") await refreshReview(); }
        else { appConfirmed = true; render(); setMode("full"); }
    });
    $("sz-manual-btn").addEventListener("click", () => { appConfirmed = true; render(); setMode("full"); });

    // ── Input handling (shared by the review questions and the full form) ──
    sizingForm.addEventListener("input", e => {
        const p = e.target.dataset.path;
        if (!p) return;
        values[p] = e.target.value;
        sizingForm.querySelectorAll(`[data-field="${p}"]`).forEach(g => {
            g.classList.remove("missing");
            if (aiQuotes.has(p)) { g.classList.remove("ai-filled"); g.querySelector(".ai-hint")?.remove(); }
            if (suggested.has(p)) { g.classList.remove("suggested"); g.querySelector(".sug-hint")?.remove(); }
        });
        missingPaths.delete(p);
        aiQuotes.delete(p);   // edited by the user → no longer "read from text"
        suggested.delete(p);  // … and no longer a suggestion
    });
    sizingForm.addEventListener("change", async e => {
        if (e.target.id === "sz-pick-app") {
            appSelect.value = e.target.value; appConfirmed = true; aiQuotes.delete("application");
            render(); await refreshReview(); return;
        }
        if (!e.target.dataset.rerender) return;
        render();
        if (mode === "review") await refreshReview();
    });
    appSelect.addEventListener("change", () => { appConfirmed = true; missingPaths.clear(); aiQuotes.delete("application"); render(); });

    sizingForm.addEventListener("reset", () => {
        setTimeout(() => {
            Object.keys(values).forEach(k => delete values[k]);
            Object.assign(values, DEFAULT_VALUES);
            missingPaths.clear(); aiQuotes.clear(); suggested.clear(); appConfirmed = false;
            machineAsWritten = null; machineExplanation = null;
            appSelect.value = "conveyor"; aiText.value = "";
            aiFeedback.hidden = true; proofPanel.hidden = true; window.Assistant?.hide(); resultsPanel.hidden = true; errorPanel.hidden = true;
            render(); setMode("start");
        });
    });

    // ── Step 1: read the description ─────────────────────────
    aiBtn.addEventListener("click", async () => {
        const text = aiText.value.trim();
        if (!text) { aiText.focus(); return; }
        aiBtn.disabled = true; aiBtn.textContent = "Reading...";
        try {
            // One entry point decides the kind of calculation; only motor sizing is handled here
            const asked = await post("/api/ask", { text });
            if (asked.topic !== "motor_sizing") {
                setMode("start"); aiFeedback.hidden = true;
                proofPanel.hidden = true; resultsPanel.hidden = true; errorPanel.hidden = true;
                await window.Assistant.show(asked);
                return;
            }
            window.Assistant?.hide();
            const data = asked.sizing;
            [...aiQuotes.keys(), ...suggested.keys()].forEach(p => { if (p !== "application") delete values[p]; });  // replace the previous reading
            aiQuotes.clear(); suggested.clear();
            machineAsWritten = data.machine_as_written || null;
            machineExplanation = data.machine_explanation || null;
            (data.values || []).forEach(v => {
                if (v.path === "application") { appSelect.value = v.value; appConfirmed = true; }
                else values[v.path] = v.value;
                aiQuotes.set(v.path, v.quote);
            });
            missingPaths.clear();
            render();

            const notes = [...(data.clarifications || [])];
            if (data.unsupported_message) {
                const isBearing = /bearing/i.test(data.unsupported_machine || "");
                aiFeedback.className = "sz-note warn";
                aiFeedback.innerHTML = `<strong>${esc(data.unsupported_message)}</strong>
                    <div class="sz-ai-actions" style="margin-top:0.6rem">
                        <button type="button" class="btn-secondary" data-goto-tab="${isBearing ? "bearing" : "selection"}">
                            ${isBearing ? "Open Bearing Life" : "Open Advanced: Torque & RPM"}</button></div>` +
                    (notes.length ? `<ul>${notes.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : "");
                aiFeedback.hidden = false;
                if (data.parser_status === "UNSUPPORTED_MACHINE") { setMode("start"); return; }
            } else {
                if ((data.values || []).length === 0) notes.unshift("We couldn't pick out any values. You can answer the questions below instead.");
                aiFeedback.className = "sz-note warn";
                aiFeedback.innerHTML = notes.length ? `<ul>${notes.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : "";
                aiFeedback.hidden = notes.length === 0;
            }
            await refreshReview();
            setMode("review");
        } catch (err) {
            aiFeedback.className = "sz-note danger";
            aiFeedback.innerHTML = `<strong>Could not read the text.</strong> ${esc(err.message || "")} You can fill in the full form instead.`;
            aiFeedback.hidden = false;
        } finally {
            aiBtn.disabled = false; aiBtn.textContent = "Continue";
        }
    });

    // ── Step 2: show what we understood + ask only what is missing ──
    const defFor = p => visible.find(d => d.path === p);

    function displayValue(p) {
        if (p === "application") {
            const name = appSelect.options[appSelect.selectedIndex].text.split(" — ")[0];
            const said = machineAsWritten && !name.toLowerCase().includes(machineAsWritten.toLowerCase())
                ? ` <em>(you said “${esc(machineAsWritten)}”)</em>` : "";
            return esc(name) + said;
        }
        const d = defFor(p), v = values[p];
        if (!d) return esc(v);
        if (d.type === "select") return esc((d.options.find(([val]) => val === v) || [v, v])[1]);
        return `${esc(v)}${d.unit ? " " + esc(d.unit) : ""}`;
    }
    const SHORT_LABELS = {
        application: "Machine", "part.shape": "Part", "part.quantity": "Parts at once",
        "limits.max_voltage_v": "Supply", "duty.hours_per_day": "Hours per day", "duty.load_class": "Work",
    };
    const chipLabel = p => SHORT_LABELS[p] || (defFor(p) || { label: p }).label;

    async function refreshReview(highlight = false) {
        // Ask the backend what the calculation still needs. Anything it has a suggestion for is
        // filled in (and shown as "Suggested"); only what is left is asked as a question.
        let missing = [], errors = [];
        if (!appConfirmed) {
            missing = ["_app"];
        } else {
            for (let pass = 0; pass < 2; pass++) {
                const { body, limits } = buildPayload();
                let sized;
                try { sized = await post("/api/size", body); } catch (err) { errors = [err.message]; break; }
                const table = sized.suggestions || {};
                missing = (sized.missing_inputs || []).map(m => m.field);
                errors = sized.errors || [];
                if (!limits.max_voltage_v) missing.push("limits.max_voltage_v");
                let filled = false;
                missing.forEach(p => {
                    const v = values[p];
                    if (table[p] && (v === undefined || v === null || v === "")) {
                        values[p] = table[p].value; suggested.set(p, table[p].note); filled = true;
                    }
                });
                if (!filled) break;
                render();
            }
        }
        missing = [...new Set(missing)].filter(p => !suggested.has(p));

        // Understood: every value that will be used — read from the text, answered, or a visible default
        const used = visible.filter(d => isFilled(d) && !suggested.has(d.path) && (aiQuotes.has(d.path) || !d.optional)).map(d => d.path);
        const chips = [...(appConfirmed ? ["application"] : []), ...used];
        understood.innerHTML = (chips.length
            ? chips.map(p => {
                const src = p === "application" && machineExplanation ? machineExplanation
                          : aiQuotes.has(p) ? `From your text: “${aiQuotes.get(p)}”` : "Entered or assumed — change it under Edit all details";
                return `<span class="sz-chip${aiQuotes.has(p) ? "" : " plain"}" title="${esc(src)}"><span>${esc(chipLabel(p))}</span> ${displayValue(p)}</span>`;
            }).join("")
            : `<span class="field-hint">Nothing yet — answer the questions below.</span>`)
            + (appConfirmed && machineExplanation ? `<p class="field-hint sz-why">${esc(machineExplanation)}</p>` : "");

        const questions = missing.map(p => {
            if (p === "_app") return `
                <div class="field-group${highlight ? " missing" : ""}" style="grid-column: 1 / -1">
                    <label>What kind of machine is it?</label>
                    <div class="input-row"><select id="sz-pick-app"><option value="" selected disabled>— choose —</option>${
                        [...appSelect.options].map(o => `<option value="${o.value}">${esc(o.text)}</option>`).join("")}</select></div>
                </div>`;
            const d = defFor(p);
            if (!d) return "";
            if (highlight) missingPaths.add(p);
            return fieldHtml(d);
        }).join("");

        const sugDefs = [...suggested.keys()].map(defFor).filter(Boolean);
        const sugBlock = sugDefs.length ? `
            <div class="sz-sug-head" style="grid-column: 1 / -1">
                <strong>We filled these in with typical values</strong> — check them and change any you know better.
            </div>${sugDefs.map(fieldHtml).join("")}` : "";

        needed.innerHTML = questions + sugBlock + (errors.length
            ? `<div class="sz-note danger" style="grid-column: 1 / -1"><strong>Please correct:</strong><ul>${errors.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "");
        const n = missing.length;
        neededTitle.textContent = n === 0 ? (sugDefs.length ? "Ready to calculate" : "") : n === 1 ? "Just one more thing" : `Just ${n} more things`;
        neededWrap.hidden = n === 0 && errors.length === 0 && sugDefs.length === 0;
        return { missing, errors };
    }

    // ── Build request from the fields that apply ─────────────
    function buildPayload() {
        const body = { application: values["_app"], material: {}, part: {}, params: {}, duty: {} };
        const limits = {};
        visible.forEach(d => {
            let v = values[d.path];
            if (v === undefined || v === null || String(v).trim() === "") return;
            if (d.type === "number") v = Number(v);
            const [grp, key] = d.path.split(".");
            (grp === "limits" ? limits : body[grp])[key] = v;
        });
        body.suggested = [...suggested.keys()].filter(p => !p.startsWith("limits."));
        if (machineAsWritten) body.machine_text = machineAsWritten;
        return { body, limits };
    }

    function setBusy(on, text) {
        szBtn.disabled = on;
        szBtn.querySelector(".btn-text").textContent = text || "Calculate & Find Motors";
        szSpinner.hidden = !on;
    }

    // ── Step 3: calculate (pressing this confirms the values shown) ──
    sizingForm.addEventListener("submit", async e => {
        e.preventDefault();
        proofPanel.hidden = true; resultsPanel.hidden = true; errorPanel.hidden = true;

        if (mode === "review") {
            setBusy(true, "Checking...");
            const { missing, errors } = await refreshReview(true);
            setBusy(false);
            if (missing.length || errors.length) {
                neededWrap.scrollIntoView({ behavior: "smooth", block: "center" });
                return;
            }
        }
        const { body, limits } = buildPayload();

        setBusy(true, "Calculating...");
        let sized;
        try {
            sized = await post("/api/size", body);
        } catch (err) {
            setBusy(false);
            showError("Could not calculate", err.message || "Could not reach the server.");
            return;
        }

        const missing = (sized.missing_inputs || []).map(m => m.field);
        if (!limits.max_voltage_v) missing.push("limits.max_voltage_v");
        if (sized.status !== "SIZED" || missing.length) {
            setBusy(false);
            renderProblems(sized, missing);
            missingPaths = new Set(missing);
            render();
            sizingForm.querySelector(".field-group.missing")?.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
        }
        renderProof(sized, body);

        setBusy(true, "Finding motors...");
        const req = sized.requirement;
        const payload = {
            required_speed_rpm: req.required_speed_rpm,
            required_torque_nm: req.required_torque_nm,
            peak_torque_nm: req.peak_torque_nm,
            service_factor: req.service_factor,
            max_voltage_v: limits.max_voltage_v,
            speed_tolerance_pct: limits.speed_tolerance_pct ?? 50,
            top_n: limits.top_n || 5,
            include_internet_results: internet.checked,
        };
        try {
            const res = await fetch(`${API}/api/recommend`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
            const data = await res.json();
            if (!res.ok) { showError("Selection error", typeof data.detail === "string" ? data.detail : "Unexpected error"); return; }
            if (data.count === 0 && (!data.internet_results || data.internet_results.length === 0)) {
                showError("No matching motor + gearbox found",
                    `None of the motors we searched can deliver ${fmt(req.design_torque_nm)} N·m at ${fmt(req.required_speed_rpm)} rpm ` +
                    `on ${payload.max_voltage_v} V. Your requirement above is still correct — try ticking "Also search the internet", ` +
                    `or a higher supply voltage.`);
                return;
            }
            renderResults(data);
        } catch {
            showError("Connection Error", "Could not reach the server.");
        } finally {
            setBusy(false);
        }
    });

    // ── Proof rendering ──────────────────────────────────────
    function renderProblems(sized, missing) {
        proofTitle.textContent = sized.status === "INVALID_INPUT" ? "Some values need fixing" : "A few more details are needed";
        proofSub.textContent = "Nothing is guessed. Fill in the highlighted boxes and press Calculate again.";
        const labels = [...new Set(missing)].map(p => {
            const fromApi = (sized.missing_inputs || []).find(m => m.field === p);
            return fromApi ? fromApi.label : (defFor(p) || { label: p }).label;
        });
        proofBody.innerHTML = `
            ${labels.length ? `<div class="sz-note warn"><strong>Missing:</strong><ul>${labels.map(l => `<li>${esc(l)}</li>`).join("")}</ul></div>` : ""}
            ${(sized.errors || []).length ? `<div class="sz-note danger"><strong>Please correct:</strong><ul>${sized.errors.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}`;
        proofPanel.hidden = false;
    }

    function renderProof(sized, body) {
        const r = sized.requirement;
        const appName = appSelect.options[appSelect.selectedIndex].text.split(" — ")[0];
        proofTitle.textContent = "What your machine needs";
        proofSub.textContent = `${appName}${body.material?.name ? " · " + body.material.name : ""} — calculated only from your inputs, physical constants and the defaults listed below.`;

        const card = (label, val, unit, sub, cls = "") => `<div class="sz-req ${cls}"><div class="sz-req-label">${label}</div><div class="sz-req-val">${Units.family(unit) ? Units.valueHtml(val, unit) : `${fmt(val)} <span>${unit}</span>`}</div>${sub ? `<div class="sz-req-sub">${sub}</div>` : ""}</div>`;

        const points = sized.operating_points.length > 1 ? `
            <h4 class="sz-sub">Operating points</h4>
            <table class="spec-table sz-points"><tr><td><strong>Point</strong></td><td><strong>Speed</strong></td><td><strong>Running torque</strong></td><td><strong>Peak torque</strong></td></tr>
            ${sized.operating_points.map(p => `<tr><td>${esc(p.label)}</td><td>${Units.valueHtml(p.speed_rpm, "rpm")}</td><td>${Units.valueHtml(p.run_torque_nm, "N·m")}</td><td>${Units.valueHtml(p.peak_torque_nm, "N·m")}</td></tr>`).join("")}
            </table>` : "";

        const steps = sized.steps.map((s, i) => {
            const defaults = Object.entries(s.inputs || {}).filter(([, inp]) => inp.origin === "DEFAULT");
            return `
            <li class="sz-stepline">
                <div class="sz-step-head"><span class="sz-step-n">${i + 1}</span> ${esc(s.label)}</div>
                <div class="sz-formula">${esc(s.formula)}</div>
                <div class="sz-subst">${esc(s.substitution)}</div>
                ${defaults.length ? `<div class="sz-step-note default">Uses default: ${defaults.map(([k, inp]) => `${esc(k)} = ${esc(inp.value)} ${esc(inp.unit)}`).join(", ")}</div>` : ""}
                ${s.note ? `<div class="sz-step-note">${esc(s.note)}</div>` : ""}
            </li>`;
        }).join("");

        const list = (items, cls, title) => items.length ? `<div class="sz-note ${cls}"><strong>${title}</strong><ul>${items.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";

        proofBody.innerHTML = `
            <div class="sz-req-grid main">
                ${card("Output speed", r.required_speed_rpm, "rpm", "How fast the gearbox shaft must turn")}
                ${card("Turning force (torque)", r.design_torque_nm, "N·m", `Includes a ${fmt(r.service_factor)}× safety margin`, "key")}
                ${card("Power", r.required_power_w, "W", "At the gearbox output")}
            </div>
            ${list(sized.warnings, "danger", "Safety notes")}
            ${list([...(sized.suggested_used || []),
                    ...(suggested.has("limits.max_voltage_v") ? [`Supply voltage: ${values["limits.max_voltage_v"]} V (suggested) — ${suggested.get("limits.max_voltage_v")}`] : [])],
                   "info", "Typical values we used because you didn't give them — please check")}
            ${list(sized.assumptions, "warn", "Things we assumed because you didn't mention them — change them under “Edit all details” if wrong")}
            <details class="sz-details">
                <summary>Show the full calculation (${sized.steps.length} steps)</summary>
                <div class="sz-req-grid">
                    ${card("Continuous torque", r.required_torque_nm, "N·m", "before safety margin")}
                    ${card("Peak torque", r.peak_torque_nm, "N·m", "while speeding up")}
                    ${card("Safety margin (SF)", r.service_factor, "×")}
                    ${card("Design peak torque", r.design_peak_torque_nm, "N·m", "peak × SF")}
                </div>
                ${list(sized.material_notes, "info", "Material")}
                ${points}
                <ol class="sz-steps">${steps}</ol>
                <p class="field-hint" style="margin-top:1rem">Engineering defaults version: ${esc(sized.defaults_version)} (awaiting engineering sign-off — see docs/ENGINEERING_DEFAULTS_TO_REVIEW.md).</p>
            </details>`;
        proofPanel.hidden = false;
        proofPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    render();
    setMode("start");
})();
