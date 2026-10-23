/* Engineering Calculation Assistant — project country and standards.
 *
 * The engineer picks the country the machine is for and, optionally, the
 * standard the customer requires. Every built-in check names the standard it
 * follows; when a country or customer standard is set, each check also says
 * so and asks the engineer to confirm it is accepted for this project.
 * The tool never claims a different standard was applied.
 *
 * REGION_NOTES are pending engineering review (docs/ENGINEERING_DEFAULTS_TO_REVIEW.md).
 */

(() => {
    const $ = id => document.getElementById(id);
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    const COUNTRIES = ["USA", "UK", "Australia", "New Zealand", "India", "Canada", "Europe (EU)", "Middle East", "Other"];

    // Where a project's country commonly uses a different standard for the same check
    const REGION_NOTES = [
        { match: /ISO 281/i, notes: {
            "USA": "US projects often cite ANSI/ABMA Std 9 (ball) and Std 11 (roller), which use the same basic rating-life method." } },
        { match: /ISO 5048|DIN 22101/i, notes: {
            "USA": "US projects usually follow the CEMA method (Belt Conveyors for Bulk Materials). It differs from ISO 5048, so results will not match exactly.",
            "Canada": "Canadian projects often follow the CEMA method (Belt Conveyors for Bulk Materials). It differs from ISO 5048, so results will not match exactly." } },
        { match: /ASME/i, notes: {
            "Europe (EU)": "European projects often use DIN 743 for shaft strength, which also covers fatigue." } },
    ];

    const KEY_C = "tmd.country", KEY_S = "tmd.custstd";
    const load = k => { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } };
    const save = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode: not remembered */ } };

    function get() {
        return { country: ($("std-country")?.value || "").trim(), customer: ($("std-customer")?.value || "").trim() };
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

    function summaryText() {
        const { country, customer } = get();
        return [country && `Country: ${country}`, customer && `Customer standard: ${customer}`].filter(Boolean).join(" · ");
    }

    function init() {
        const sel = $("std-country"), cust = $("std-customer");
        if (!sel || !cust) return;
        sel.innerHTML = `<option value="">Not specified</option>` + COUNTRIES.map(c => `<option>${esc(c)}</option>`).join("");
        sel.value = COUNTRIES.includes(load(KEY_C)) ? load(KEY_C) : "";
        cust.value = load(KEY_S);
        const changed = () => { save(KEY_C, sel.value); save(KEY_S, cust.value.trim()); document.dispatchEvent(new Event("standards-change")); };
        sel.addEventListener("change", changed);
        cust.addEventListener("change", changed);
    }

    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
    window.Standards = { get, noteFor, summaryText, COUNTRIES };
})();
