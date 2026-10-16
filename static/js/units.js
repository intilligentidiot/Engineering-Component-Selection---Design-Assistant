/* Tesla Mechanical Designs — unit conversion for display and input only.
 *
 * The engineering calculations always run in the plan's own units (SI-based).
 * This file converts values only at the edges: when a number is shown, and
 * when an engineer types a number in a different unit. "Show working" keeps the
 * units the calculation actually used.
 *
 * Each unit belongs to a family (force, torque, length…). Conversion goes via
 * the family's base unit: base = value × factor (+ offset for temperatures).
 * Choosing a unit for one value sets the preference for its whole family, so
 * e.g. switching one force to kN switches every force on the page.
 */

(() => {
    const PI = Math.PI;
    // family → { unit: [factor to base, offset] }
    const FAMILIES = {
        length:       { "m": [1], "mm": [1e-3], "cm": [1e-2], "km": [1e3], "µm": [1e-6], "in": [0.0254], "ft": [0.3048], "yd": [0.9144] },
        area:         { "m²": [1], "mm²": [1e-6], "cm²": [1e-4], "in²": [6.4516e-4], "ft²": [0.09290304] },
        volume:       { "m³": [1], "L": [1e-3], "cm³": [1e-6], "mm³": [1e-9], "in³": [1.6387064e-5], "ft³": [0.028316846592] },
        mass:         { "kg": [1], "g": [1e-3], "t": [1e3], "lb": [0.45359237], "short ton": [907.18474] },
        time:         { "s": [1], "ms": [1e-3], "min": [60], "h": [3600] },
        current:      { "A": [1], "mA": [1e-3], "kA": [1e3] },
        temperature:  { "K": [1, 0], "°C": [1, 273.15], "°F": [5 / 9, 459.67 * 5 / 9] },
        amount:       { "mol": [1], "kmol": [1e3] },
        luminous:     { "cd": [1] },
        angle:        { "rad": [1], "deg": [PI / 180], "°": [PI / 180], "rev": [2 * PI] },
        solid_angle:  { "sr": [1] },
        frequency:    { "Hz": [1], "kHz": [1e3] },
        rot_speed:    { "rpm": [2 * PI / 60], "rad/s": [1], "rev/s": [2 * PI] },
        speed:        { "m/s": [1], "m/min": [1 / 60], "km/h": [1 / 3.6], "ft/min": [0.00508], "ft/s": [0.3048], "mm/s": [1e-3] },
        acceleration: { "m/s²": [1], "g₀": [9.80665], "ft/s²": [0.3048] },
        force:        { "N": [1], "kN": [1e3], "MN": [1e6], "kgf": [9.80665], "lbf": [4.4482216152605], "kip": [4448.2216152605] },
        torque:       { "N·m": [1], "kN·m": [1e3], "N·mm": [1e-3], "kgf·m": [9.80665], "lbf·ft": [1.3558179483314], "lbf·in": [0.1129848290276] },
        pressure:     { "Pa": [1], "kPa": [1e3], "MPa": [1e6], "GPa": [1e9], "N/mm²": [1e6], "bar": [1e5], "psi": [6894.757293168], "ksi": [6894757.293168] },
        energy:       { "J": [1], "kJ": [1e3], "MJ": [1e6], "Wh": [3600], "kWh": [3.6e6], "BTU": [1055.05585262] },
        power:        { "W": [1], "kW": [1e3], "MW": [1e6], "hp": [745.69987158227], "PS": [735.49875] },
        charge:       { "C": [1], "mAh": [3.6], "Ah": [3600] },
        voltage:      { "V": [1], "mV": [1e-3], "kV": [1e3] },
        resistance:   { "Ω": [1], "kΩ": [1e3], "MΩ": [1e6] },
        capacitance:  { "F": [1], "µF": [1e-6], "nF": [1e-9], "pF": [1e-12] },
        mag_flux:     { "Wb": [1], "mWb": [1e-3] },
        flux_density: { "T": [1], "mT": [1e-3], "G": [1e-4] },
        inductance:   { "H": [1], "mH": [1e-3], "µH": [1e-6] },
        lum_flux:     { "lm": [1] },
        density:      { "kg/m³": [1], "g/cm³": [1e3], "t/m³": [1e3], "lb/ft³": [16.01846337] },
        mass_flow:    { "kg/s": [1], "kg/h": [1 / 3600], "t/h": [1000 / 3600], "lb/h": [0.45359237 / 3600], "short ton/h": [907.18474 / 3600] },
        linear_mass:  { "kg/m": [1], "g/m": [1e-3], "lb/ft": [1.48816394357] },
        inertia:      { "kg·m²": [1], "kg·mm²": [1e-6], "lb·ft²": [0.0421401100938] },
    };

    // Spellings that mean the same unit
    const ALIASES = {
        "Nm": "N·m", "N.m": "N·m", "N*m": "N·m", "kNm": "kN·m", "Nmm": "N·mm",
        "kg/m3": "kg/m³", "m/s2": "m/s²", "kgm2": "kg·m²", "kg.m2": "kg·m²", "kg·m^2": "kg·m²",
        "m2": "m²", "mm2": "mm²", "m3": "m³", "degC": "°C", "tph": "t/h", "r/min": "rpm", "rev/min": "rpm", "ohm": "Ω",
    };

    const UNIT_FAMILY = {};
    Object.entries(FAMILIES).forEach(([fam, units]) => Object.keys(units).forEach(u => { UNIT_FAMILY[u] = fam; }));

    // Presets: family → preferred display unit (families not listed keep the calculation's unit)
    const PRESETS = {
        "as-calculated": { label: "SI (as calculated)", units: {} },
        "si-eng": { label: "SI engineering (kN, kW, MPa)", units: {
            force: "kN", torque: "kN·m", power: "kW", pressure: "MPa", energy: "kJ", mass_flow: "t/h" } },
        "us": { label: "US customary (lbf, hp, psi, in)", units: {
            length: "in", mass: "lb", force: "lbf", torque: "lbf·ft", power: "hp", pressure: "psi", speed: "ft/min",
            density: "lb/ft³", mass_flow: "short ton/h", linear_mass: "lb/ft", temperature: "°F", inertia: "lb·ft²",
            area: "in²", volume: "ft³", acceleration: "ft/s²", energy: "BTU" } },
    };

    const norm = u => ALIASES[(u || "").trim()] || (u || "").trim();
    const family = u => UNIT_FAMILY[norm(u)] || null;

    function toBase(v, unit) {
        const u = norm(unit), f = FAMILIES[family(u)]?.[u];
        return f ? v * f[0] + (f[1] || 0) : v;
    }
    function fromBase(v, unit) {
        const u = norm(unit), f = FAMILIES[family(u)]?.[u];
        return f ? (v - (f[1] || 0)) / f[0] : v;
    }
    const convert = (v, from, to) => (family(from) && family(from) === family(to)) ? fromBase(toBase(v, from), to) : v;

    // ── Preferences (remembered in this browser only) ────────
    let preset = "as-calculated", famPref = {};
    try {
        preset = localStorage.getItem("tmd.units.preset") || preset;
        famPref = JSON.parse(localStorage.getItem("tmd.units.families") || "{}");
    } catch { /* storage unavailable — defaults are fine */ }
    if (!PRESETS[preset]) preset = "as-calculated";
    const save = () => {
        try { localStorage.setItem("tmd.units.preset", preset); localStorage.setItem("tmd.units.families", JSON.stringify(famPref)); }
        catch { /* ignore */ }
    };

    /** The unit to show for a value calculated in `calcUnit`. */
    function displayUnit(calcUnit) {
        const u = norm(calcUnit), fam = family(u);
        if (!fam) return u;
        return famPref[fam] || PRESETS[preset].units[fam] || u;
    }

    const fmt = x => (x === null || x === undefined || Number.isNaN(x)) ? "—"
        : Math.abs(x) >= 1e4 ? Math.round(x).toLocaleString() : String(Number(Number(x).toPrecision(4)));
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    function unitSelect(calcUnit, shown, cls = "u-sel") {
        const fam = family(calcUnit);
        if (!fam || Object.keys(FAMILIES[fam]).length < 2) return `<span class="u-unit">${esc(shown)}</span>`;
        return `<select class="${cls}" data-family="${fam}" title="Change unit">${
            Object.keys(FAMILIES[fam]).map(u => `<option value="${esc(u)}" ${u === shown ? "selected" : ""}>${esc(u)}</option>`).join("")}</select>`;
    }

    /** A result value with its own unit dropdown. The calculated value and unit are kept in data attributes. */
    function valueHtml(v, calcUnit) {
        const u = norm(calcUnit), shown = displayUnit(u);
        return `<span class="u-val" data-base="${v}" data-unit="${esc(u)}"><span class="u-num">${fmt(convert(v, u, shown))}</span> ${unitSelect(u, shown)}</span>`;
    }

    /** Re-draw every result value on the page in the current preferred units. */
    function refresh(root = document) {
        root.querySelectorAll(".u-val").forEach(el => {
            const u = el.dataset.unit, shown = displayUnit(u), v = Number(el.dataset.base);
            el.querySelector(".u-num").textContent = fmt(convert(v, u, shown));
            const sel = el.querySelector("select.u-sel");
            if (sel) sel.value = shown;
        });
        listeners.forEach(fn => fn());
    }

    const listeners = [];
    function setFamily(fam, unit) { famPref[fam] = unit; save(); refresh(); }
    function setPreset(p) { preset = PRESETS[p] ? p : "as-calculated"; famPref = {}; save(); refresh(); }

    // A unit dropdown on any result value sets the unit for its whole family
    document.addEventListener("change", e => {
        const sel = e.target.closest("select.u-sel");
        if (sel) setFamily(sel.dataset.family, sel.value);
    });

    // Header preset selector
    document.addEventListener("DOMContentLoaded", () => {
        const head = document.getElementById("units-preset");
        if (!head) return;
        head.innerHTML = Object.entries(PRESETS).map(([k, p]) => `<option value="${k}" ${k === preset ? "selected" : ""}>${esc(p.label)}</option>`).join("");
        head.addEventListener("change", () => setPreset(head.value));
    });

    window.Units = {
        FAMILIES, family, norm, convert, toBase, fromBase, displayUnit, valueHtml, unitSelect, refresh,
        setFamily, setPreset, onChange: fn => listeners.push(fn), fmt,
        get preset() { return preset; },
    };
})();
