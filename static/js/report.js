/* Engineering Calculation Assistant — printable calculation report.
 *
 * "Print / Save as PDF" prints only the result being looked at (a project
 * plan, a motor sizing, or a bearing / AI-method answer) as a clean light
 * report: a report header with the question, date and units, the results,
 * every calculation step with its working, assumptions and notes.
 * The browser's print dialog offers "Save as PDF".
 */

(() => {
    const $ = id => document.getElementById(id);
    const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

    const TITLES = {
        project: () => document.querySelector("#pj-area .pj-title")?.textContent || "Project calculation plan",
        sizing: () => {
            const app = $("sz-application");
            const name = app ? app.options[app.selectedIndex].text.split(" — ")[0] : "Machine";
            return `${name} — drive sizing and motor selection`;
        },
        assistant: () => $("as-result-title")?.textContent.replace(/\s+/g, " ").trim() || "Calculation",
    };

    let opened = [];

    function prepare(kind) {
        const now = new Date();
        const units = $("units-preset");
        $("rh-title").textContent = TITLES[kind]();
        $("rh-meta").innerHTML =
            `Date: <strong>${esc(now.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }))}</strong>` +
            ` · Units shown: <strong>${esc(units?.selectedOptions[0]?.text || "SI")}</strong>` +
            (window.Standards && Standards.summaryText() ? ` · <strong>${esc(Standards.summaryText())}</strong>` : "");
        const question = ($("sz-ai-text")?.value || "").trim();
        $("rh-question").innerHTML = question
            ? `<div class="rh-label">Question / description</div><div class="rh-qtext">${esc(question)}</div>` : "";
        document.body.dataset.print = kind;

        // Open every "show working" and detail section so the report carries the full working
        opened = [];
        document.querySelectorAll("details").forEach(d => { if (!d.open) { d.open = true; opened.push(d); } });
        document.querySelectorAll(".result-card-detail:not(.open)").forEach(d => { d.classList.add("open"); opened.push(d); });
    }

    function restore() {
        opened.forEach(d => { if (d.tagName === "DETAILS") d.open = false; else d.classList.remove("open"); });
        opened = [];
        delete document.body.dataset.print;
    }

    window.addEventListener("afterprint", restore);

    document.addEventListener("click", e => {
        const btn = e.target.closest("[data-print-report]");
        if (!btn) return;
        prepare(btn.dataset.printReport);
        window.print();
        // Some browsers do not fire afterprint reliably
        setTimeout(() => { if (document.body.dataset.print) restore(); }, 1000);
    });

    window.Report = { prepare, restore };
})();
