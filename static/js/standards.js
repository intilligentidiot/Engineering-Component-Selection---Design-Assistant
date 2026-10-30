/* Engineering Calculation Assistant — project country and standards.
 *
 * The engineer picks the country the machine is for, then (optionally) the
 * standard the customer requires from that country's list only — or types one
 * that is not listed. Every built-in check names the standard it follows; when
 * a country or customer standard is set, each check also says so and asks the
 * engineer to confirm it is accepted for this project.
 * The tool never claims a different standard was applied.
 *
 * STANDARDS and REGION_NOTES are pending engineering review
 * (docs/ENGINEERING_DEFAULTS_TO_REVIEW.md, section 12).
 */

(() => {
    const $ = id => document.getElementById(id);
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    // Commonly specified machine-design standards, per country: [code, what it covers]
    const STANDARDS = {
        "USA": [
            ["ASME B106.1M", "Design of transmission shafting"],
            ["ANSI/ABMA Std 9", "Load ratings and fatigue life — ball bearings"],
            ["ANSI/ABMA Std 11", "Load ratings and fatigue life — roller bearings"],
            ["ANSI/AGMA 2001", "Rating of spur and helical gear teeth"],
            ["ANSI/AGMA 6013", "Industrial enclosed gear drives"],
            ["NEMA MG 1", "Motors and generators"],
            ["CEMA — Belt Conveyors for Bulk Materials", "Bulk belt conveyor design"],
            ["AISC 360", "Structural steel"],
            ["AWS D1.1", "Structural welding — steel"],
            ["ASME BTH-1", "Below-the-hook lifting devices"],
            ["ASME B30", "Cranes, hoists and rigging (safety)"],
            ["ASME BPVC Section VIII", "Pressure vessels"],
            ["ANSI B11.0", "Safety of machinery"],
            ["NFPA 79", "Electrical standard for industrial machinery"],
            ["OSHA 29 CFR 1910 Subpart O", "Machinery and machine guarding"],
        ],
        "UK": [
            ["BS EN ISO 12100", "Safety of machinery — risk assessment"],
            ["BS EN ISO 13849-1", "Safety-related parts of control systems"],
            ["BS EN 60204-1", "Electrical equipment of machines"],
            ["BS EN 60034-1", "Rotating electrical machines — rating"],
            ["BS ISO 281", "Rolling bearings — rating life"],
            ["BS ISO 6336", "Spur and helical gears — load capacity"],
            ["BS EN 1993-1-1 (Eurocode 3)", "Design of steel structures"],
            ["BS EN 1090-2", "Execution of steel structures"],
            ["BS EN 13001", "Cranes — general design"],
            ["BS EN 620", "Belt conveyors for bulk materials — safety"],
            ["BS EN 13445", "Unfired pressure vessels"],
            ["Supply of Machinery (Safety) Regulations 2008", "UK machinery law (UKCA)"],
        ],
        "Australia": [
            ["AS 1403", "Design of rotating steel shafts"],
            ["AS 4024.1", "Safety of machinery"],
            ["AS 1755", "Conveyors — safety requirements"],
            ["AS 1418", "Cranes, hoists and winches"],
            ["AS 4100", "Steel structures"],
            ["AS/NZS 5131", "Structural steelwork — fabrication and erection"],
            ["AS/NZS 1554.1", "Structural steel welding"],
            ["AS/NZS 1170", "Structural design actions (loads)"],
            ["AS 1210", "Pressure vessels"],
            ["AS/NZS 3000", "Electrical installations (wiring rules)"],
        ],
        "New Zealand": [
            ["AS/NZS 4024.1", "Safety of machinery"],
            ["NZS 3404", "Steel structures"],
            ["AS/NZS 5131", "Structural steelwork — fabrication and erection"],
            ["AS/NZS 1554.1", "Structural steel welding"],
            ["AS/NZS 1170", "Structural design actions (loads)"],
            ["AS/NZS 1200", "Pressure equipment"],
            ["AS/NZS 3000", "Electrical installations (wiring rules)"],
        ],
        "India": [
            ["IS 800", "General construction in steel"],
            ["IS 816", "Metal arc welding for general construction in mild steel"],
            ["IS 875", "Design loads for buildings and structures"],
            ["IS 807", "Design of cranes and hoists"],
            ["IS 3177", "Electric overhead travelling and gantry cranes"],
            ["IS 11592", "Selection and design of belt conveyors"],
            ["IS 325", "Three-phase induction motors"],
            ["IS 2825", "Unfired pressure vessels"],
        ],
        "Canada": [
            ["CSA Z432", "Safeguarding of machinery"],
            ["CSA S16", "Design of steel structures"],
            ["CSA W59", "Welded steel construction"],
            ["CSA B167", "Overhead travelling cranes"],
            ["CSA B51", "Boilers, pressure vessels and pressure piping"],
            ["CSA C22.1", "Canadian Electrical Code, Part I"],
        ],
        "Europe (EU)": [
            ["Machinery Regulation (EU) 2023/1230", "EU machinery law (replaces Directive 2006/42/EC)"],
            ["Machinery Directive 2006/42/EC", "EU machinery law (CE marking)"],
            ["EN ISO 12100", "Safety of machinery — risk assessment"],
            ["EN ISO 13849-1", "Safety-related parts of control systems"],
            ["EN 60204-1", "Electrical equipment of machines"],
            ["DIN 743", "Shafts — load capacity"],
            ["ISO 281", "Rolling bearings — rating life"],
            ["ISO 6336", "Spur and helical gears — load capacity"],
            ["DIN 3990", "Gears — load capacity"],
            ["ISO 5048", "Belt conveyors — power and tensions"],
            ["DIN 22101", "Belt conveyors for bulk materials"],
            ["VDI 2230", "Bolted joints"],
            ["DIN 6892", "Feather keys — calculation"],
            ["EN 1993-1-1 (Eurocode 3)", "Design of steel structures"],
            ["EN 1090-2", "Execution of steel structures"],
            ["EN 13001", "Cranes — general design"],
            ["EN 620", "Belt conveyors for bulk materials — safety"],
            ["EN 13445", "Unfired pressure vessels"],
            ["EN 60034-1", "Rotating electrical machines — rating"],
        ],
        "Middle East": [
            ["Saudi Aramco Engineering Standards (SAES)", "Saudi Aramco projects"],
            ["ISO 12100", "Safety of machinery — risk assessment"],
            ["IEC 60204-1", "Electrical equipment of machines"],
            ["ISO 281", "Rolling bearings — rating life"],
            ["ISO 6336", "Spur and helical gears — load capacity"],
            ["ASME BPVC Section VIII", "Pressure vessels"],
            ["AISC 360", "Structural steel"],
            ["AWS D1.1", "Structural welding — steel"],
        ],
        "Other": [
            ["ISO 12100", "Safety of machinery — risk assessment"],
            ["ISO 13849-1", "Safety-related parts of control systems"],
            ["IEC 60204-1", "Electrical equipment of machines"],
            ["IEC 60034-1", "Rotating electrical machines — rating"],
            ["ISO 281", "Rolling bearings — rating life"],
            ["ISO 6336", "Spur and helical gears — load capacity"],
            ["ISO 5048", "Belt conveyors — power and tensions"],
            ["ISO 4301", "Cranes — classification"],
        ],
    };
    const COUNTRIES = Object.keys(STANDARDS);
    const OTHER = "__other__";
    const GENERAL = "General engineering mechanics";   // explicit choice for work no design standard covers

    // Where a project's country commonly uses a different standard for the same check
    const REGION_NOTES = [
        { match: /ISO 281/i, notes: {
            "USA": "US projects often cite ANSI/ABMA Std 9 (ball) and Std 11 (roller), which use the same basic rating-life method." } },
        { match: /ISO 5048|DIN 22101/i, notes: {
            "USA": "US projects usually follow the CEMA method (Belt Conveyors for Bulk Materials). It differs from ISO 5048, so results will not match exactly.",
            "Canada": "Canadian projects often follow the CEMA method (Belt Conveyors for Bulk Materials). It differs from ISO 5048, so results will not match exactly." } },
        { match: /ASME/i, notes: {
            "Europe (EU)": "European projects often use DIN 743 for shaft strength, which also covers fatigue.",
            "Australia": "Australian projects often use AS 1403 for rotating steel shafts." } },
    ];

    // Suggestions: what the question is about -> which listed standards cover it (matched on their description)
    const TOPICS = [
        { name: "shafts",     ask: /\bshafts?\b|\baxles?\b|\brotors?\b|\bspindles?\b/i,               covers: /shaft/i },
        { name: "bearings",   ask: /\bbearings?\b/i,                                                covers: /bearing/i },
        { name: "gears",      ask: /\bgears?\b|gearbox|\bpinions?\b|\breducers?\b/i,                  covers: /\bgear/i },
        { name: "conveyors",  ask: /conveyor/i,                                                     covers: /conveyor/i },
        { name: "lifting",    ask: /\bcranes?\b|\bhoists?\b|\blift(?:s|ing)?\b|\bwinch|rigging|gantry/i, covers: /crane|hoist|lifting/i },
        { name: "motors",     ask: /\bmotors?\b|shredder|pelleti[sz]er|crusher|\bmixer|\bpumps?\b|\bfans?\b/i, covers: /motor|rotating electrical/i },
        { name: "structure",  ask: /\bframes?\b|chassis|structur|\bbeams?\b|\bcolumns?\b|platform/i,  covers: /steel structures?|structural steel(?! welding)|construction in steel|design loads|design actions/i },
        { name: "welding",    ask: /\bweld/i,                                                       covers: /weld/i },
        { name: "bolts",      ask: /\bbolt/i,                                                       covers: /bolted/i },
        { name: "keys",       ask: /\bkeys?\b|keyway/i,                                             covers: /\bkeys\b/i },
        { name: "pressure",   ask: /pressure vessel|\btanks?\b|boiler|\breceivers?\b/i,             covers: /pressure/i },
        { name: "electrical", ask: /electric|wiring|control panel|\bplc\b/i,                        covers: /electrical/i },
    ];
    // Safety / legal standards apply to any machine: suggested as "also check", never as the calculation standard
    const SAFETY = /safety of machinery|risk assessment|safeguarding|machine guarding|machinery law/i;

    function suggest(text, country) {
        const list = STANDARDS[country] || [];
        const topics = TOPICS.filter(t => t.ask.test(text || ""));
        const design = [], missing = [];
        topics.forEach(t => {
            const hits = list.filter(([code, what]) => t.covers.test(what) && !SAFETY.test(what));
            hits.forEach(h => { if (!design.includes(h)) design.push(h); });
            if (!hits.length) missing.push(t.name);
        });
        const safety = text && text.trim() ? list.filter(([, what]) => SAFETY.test(what)).slice(0, 2) : [];
        return { design, safety, missing };
    }

    function renderSuggest() {
        const box = $("std-suggest"), country = $("std-country")?.value || "";
        if (!box) return;
        const { design, safety, missing } = suggest($("sz-ai-text")?.value, country);
        if (!country || (!design.length && !safety.length && !missing.length)) { box.hidden = true; box.innerHTML = ""; return; }
        const current = get().customer;
        const chip = ([code, what], cls = "") =>
            `<button type="button" class="std-chip ${cls}${code === current ? " is-on" : ""}" data-std="${esc(code)}" title="${esc(what)}">${esc(code)} — ${esc(what)}</button>`;
        box.innerHTML =
            (design.length ? `<div><strong>Suggested for your question (${esc(country)}):</strong> click one to use it.<div class="std-chips">${design.map(d => chip(d)).join("")}</div></div>` : "") +
            (missing.length ? `<div>No ${esc(country)} standard in the list for ${esc(missing.join(", "))} — choose "Other" and type the one the customer uses, or ${esc(GENERAL)}.</div>` : "") +
            (safety.length ? `<div style="margin-top:0.35rem">Also check (safety — no calculations in it):<div class="std-chips">${safety.map(s => chip(s, "is-safety")).join("")}</div></div>` : "");
        box.hidden = false;
    }

    const KEY_C = "tmd.country", KEY_S = "tmd.custstd";
    const load = k => { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } };
    const save = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode: not remembered */ } };

    function get() {
        const sel = $("std-customer"), other = $("std-customer-other");
        const customer = sel?.value === OTHER ? (other?.value || "") : (sel?.value || "");
        return { country: ($("std-country")?.value || "").trim(), customer: customer.trim() };
    }

    // Note under one calculation. standard: what the check follows; ai: the AI chose it
    function noteFor(standard, ai = false) {
        const { country, customer } = get();
        if (!country && !customer) return "";
        const follows = standard ? `This check follows <strong>${esc(standard)}</strong>${ai ? " (chosen by the AI)" : ""}.`
                                 : "This check follows general engineering mechanics, not a named standard.";
        const regional = standard && country ? (REGION_NOTES.find(r => r.match.test(standard))?.notes[country] || "") : "";
        const confirm = customer
            ? `Confirm it meets the customer's required standard (${esc(customer)})${country ? ` and is accepted for ${esc(country)}` : ""}.`
            : `Confirm it is accepted for this ${esc(country)} project.`;
        return `<div class="std-note">${follows} ${regional ? esc(regional) + " " : ""}${confirm}</div>`;
    }

    // The customer's standard uses the same method as this check (ABMA Std 9 / 11 = ISO 281 basic rating life)
    function equivalentFor(standard, bearingType, cust = get().customer) {
        if (!cust || !/ISO 281/i.test(standard || "")) return null;
        if (/ISO 281/i.test(cust)) return { name: cust, note: "" };
        const m = cust.match(/ABMA\s*Std\s*(9|11)\b/i);
        if (!m) return null;
        const wrong = (m[1] === "9" && bearingType === "roller") || (m[1] === "11" && bearingType === "ball");
        const right = bearingType === "roller" ? "ANSI/ABMA Std 11 (roller bearings)" : "ANSI/ABMA Std 9 (ball bearings)";
        return { name: cust,
                 note: `${cust} uses the same basic rating-life method as ISO 281, so this result applies to it.` +
                       (wrong ? ` Note: ${cust} covers ${m[1] === "9" ? "ball" : "roller"} bearings — this is a ${bearingType} bearing, so ${right} is the one that applies.` : "") };
    }

    // A note when the project's country usually uses a different standard for this check
    function regionalFor(standard) {
        const country = get().country;
        return standard && country ? (REGION_NOTES.find(r => r.match.test(standard))?.notes[country] || "") : "";
    }

    // What a listed standard covers ("" for a typed one) — told to the AI so it does not guess
    function scopeOf(country, code) {
        return (STANDARDS[country] || []).find(([c]) => c === code)?.[1] || "";
    }

    function summaryText() {
        const { country, customer } = get();
        return [country && `Country: ${country}`, customer && `Customer standard: ${customer}`].filter(Boolean).join(" · ");
    }

    // ── One selected standard rules every calculation ──
    const NEED_MSG = "Select a standard to calculate. Results depend on the standard you choose.";
    const GATED = "#sz-ai-btn, #as-calc, #pj-calc, #sz-submit-btn";

    // Calculate buttons stay disabled until a standard is selected; `nudge` also points the engineer to the list
    function gate(nudge = false) {
        const ok = !!get().customer;
        document.querySelectorAll(GATED).forEach(b => {
            b.classList.toggle("is-blocked", !ok);
            b.setAttribute("aria-disabled", String(!ok));
            b.title = ok ? "" : NEED_MSG;
        });
        const msg = $("std-required-msg");
        if (msg) { msg.textContent = NEED_MSG; msg.hidden = ok; msg.classList.toggle("nudge", nudge && !ok); }
        if (nudge && !ok) {
            const target = $("std-country")?.value ? $("std-customer") : $("std-country");
            target?.scrollIntoView({ behavior: "smooth", block: "center" });
            target?.focus();
        }
    }

    // A changed standard clears every result made with the old one
    function clearResults(now) {
        const shown = ["as-area", "pj-area", "as-result-panel", "sz-proof-panel", "shared-results"]
            .some(id => $(id) && !$(id).hidden);
        if (!shown) return;
        window.Assistant?.hide();
        window.Project?.hide();
        ["as-result-panel", "sz-proof-panel", "shared-results"].forEach(id => { if ($(id)) $(id).hidden = true; });
        const fb = $("sz-ai-feedback");
        if (fb) {
            fb.className = "sz-note warn";
            fb.innerHTML = now
                ? `<strong>Standard changed to ${esc(now)} — the previous result was cleared.</strong> Press Continue to calculate with ${esc(now)}.`
                : `<strong>The previous result was cleared.</strong> ${esc(NEED_MSG)}`;
            fb.hidden = false;
        }
    }

    // "Calculated using: …" line shown with every result
    function usedLine(detail = "") {
        const s = get().customer;
        return s ? `<div class="used-line">Calculated using: <strong>${esc(s)}</strong>${detail ? ` <span>· ${esc(detail)}</span>` : ""}</div>` : "";
    }

    // Fill the standard list with the chosen country's standards only
    function fillStandards(country, keep) {
        const sel = $("std-customer"), other = $("std-customer-other");
        const list = STANDARDS[country] || [];
        if (!country) {
            sel.innerHTML = `<option value="">Choose a project country first</option>`;
            sel.disabled = true;
        } else {   // no default: the engineer must pick one (General mechanics is a deliberate choice, never pre-selected)
            sel.disabled = false;
            sel.innerHTML = `<option value="" disabled>Select a standard…</option>` +
                `<option value="${esc(GENERAL)}">${esc(GENERAL)} — no design standard</option>` +
                `<optgroup label="${esc(country)}">` +
                list.map(([code, what]) => `<option value="${esc(code)}">${esc(code)} — ${esc(what)}</option>`).join("") +
                `</optgroup><option value="${OTHER}">Other (type it)…</option>`;
        }
        if (keep && (keep === GENERAL || list.some(([code]) => code === keep))) { sel.value = keep; other.value = ""; }
        else if (keep && country) { sel.value = OTHER; other.value = keep; }
        else { sel.value = ""; other.value = ""; }
        other.hidden = sel.value !== OTHER;
    }

    function init() {
        const country = $("std-country"), sel = $("std-customer"), other = $("std-customer-other");
        if (!country || !sel || !other) return;
        country.innerHTML = `<option value="">Not specified</option>` + COUNTRIES.map(c => `<option>${esc(c)}</option>`).join("");
        country.value = COUNTRIES.includes(load(KEY_C)) ? load(KEY_C) : "";
        fillStandards(country.value, load(KEY_S));

        let last = get().customer;
        const changed = () => {
            save(KEY_C, country.value);
            save(KEY_S, get().customer);
            const now = get().customer;
            if (now !== last) clearResults(now);   // a result is never shown next to a different standard
            last = now;
            gate();
            document.dispatchEvent(new Event("standards-change"));
        };
        country.addEventListener("change", () => { fillStandards(country.value, ""); changed(); });   // a new country starts with no standard
        sel.addEventListener("change", () => {
            other.hidden = sel.value !== OTHER;
            if (sel.value === OTHER) other.focus();
            changed();
        });
        other.addEventListener("change", changed);
        other.addEventListener("input", gate);

        // Nothing is calculated until a standard is selected
        document.addEventListener("click", e => {
            const b = e.target.closest(GATED);
            if (!b || get().customer) return;
            e.preventDefault(); e.stopImmediatePropagation();
            gate(true);
        }, true);
        document.addEventListener("submit", e => {
            if (get().customer || !e.target.closest("#sizing-form")) return;
            e.preventDefault(); e.stopImmediatePropagation();
            gate(true);
        }, true);
        gate();

        // Suggested standards follow the question text and the country
        let timer;
        $("sz-ai-text")?.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(renderSuggest, 300); });
        document.addEventListener("standards-change", renderSuggest);
        $("std-suggest")?.addEventListener("click", e => {
            const b = e.target.closest(".std-chip");
            if (!b) return;
            fillStandards(country.value, b.dataset.std);
            changed();
        });
        renderSuggest();
    }

    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
    window.Standards = { get, noteFor, regionalFor, equivalentFor, summaryText, suggest, scopeOf, usedLine, gate,
                         GENERAL, COUNTRIES, STANDARDS };
})();
