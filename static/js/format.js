/* Engineering Calculation Assistant — display helpers (no maths here)
 *
 * Math.html(text): shows a formula or substitution the way an engineer writes it
 *   sqrt(M**2 + 0.75 * T**2)  →  √(M² + 0.75 · T²)
 *   sigma_w_zul               →  σ with subscript "w,zul"
 * Only the look changes: the text the tool evaluated is kept in the title (hover / copy).
 */

(() => {
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const GREEK = { alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", eta: "η", theta: "θ", lambda: "λ",
                    mu: "μ", nu: "ν", rho: "ρ", sigma: "σ", tau: "τ", phi: "φ", psi: "ψ", omega: "ω",
                    Delta: "Δ", Sigma: "Σ", Omega: "Ω", Phi: "Φ" };
    const SUP = { "2": "²", "3": "³", "4": "⁴" };

    // One name: greek letter + subscript (sigma_w_zul → σ<sub>w,zul</sub>, d_mm → d<sub>mm</sub>)
    function name(n) {
        if (n === "pi") return "π";
        if (n === "sqrt") return "√";
        const [head, ...rest] = n.split("_");
        const h = GREEK[head] || head;
        return rest.length ? `${esc(h)}<sub>${esc(rest.filter(Boolean).join(","))}</sub>` : esc(h);
    }

    function html(text) {
        let s = String(text ?? "");
        // powers first, on the raw text: x**(1/3) → x^{1/3}, x**2 → x², x**0.5 → x^{0.5}
        const marks = [];
        s = s.replace(/\*\*\s*\(([^()]+)\)/g, (_, p) => { marks.push(p.replace(/\s+/g, "")); return `\u0001${marks.length - 1}\u0002`; })
             .replace(/\*\*\s*(-?[\d.]+)/g, (_, p) => SUP[p] ? `\u0003${p}\u0004` : (marks.push(p), `\u0001${marks.length - 1}\u0002`));
        // tokens: names become symbols, operators get engineering spacing
        let out = "";
        const re = /([A-Za-z][A-Za-z0-9_]*)|(\u0001\d+\u0002)|(\u0003\d\u0004)|(\s*\*\s*)|(\s*\/\s*)|([^A-Za-z\u0001\u0003*\/]+)/g;
        let m;
        while ((m = re.exec(s))) {
            if (m[1]) out += /^(sqrt|pi)$/.test(m[1]) || /^[A-Za-z]/.test(m[1]) ? `<span class="mx-v">${name(m[1])}</span>` : esc(m[1]);
            else if (m[2]) out += `<sup>${esc(marks[Number(m[2].slice(1, -1))])}</sup>`;
            else if (m[3]) out += SUP[m[3][1]];
            else if (m[4]) out += " · ";
            else if (m[5]) out += " / ";
            else out += esc(m[6]);
        }
        return out.replace(/ {2,}/g, " ").replace(/\s+(<sup>|[²³⁴])/g, "$1")
                  .replace(/<span class="mx-v">√<\/span>\s*\(/g, "√(")
                  .replace(/<span class="mx-v">(sin|cos|tan|exp|log|ln|log10|abs|min|max|ceil|floor|asin|acos|atan|atan2|radians|degrees)<\/span>/g, '<span class="mx-f">$1</span>');
    }

    // The formula/substitution as a block, with the evaluated text kept for hover and copy
    const block = (text, cls = "") => `<div class="mx ${cls}" title="${esc(text)}">${html(text)}</div>`;

    window.MathFmt = { html, block, name };

    // Example questions under the main box fill it in
    document.addEventListener("click", e => {
        const chip = e.target.closest("[data-example]");
        const box = document.getElementById("sz-ai-text");
        if (!chip || !box) return;
        box.value = chip.dataset.example;
        box.dispatchEvent(new Event("input", { bubbles: true }));
        box.focus();
    });
})();
