"use strict";
(() => {
    const source = document.getElementById("private-pdf");
    const frame = document.querySelector("[data-pdf-frame]");
    if (!source || !frame) return;
    const raw = atob(JSON.parse(source.textContent));
    const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type: "application/pdf"}));
    document.querySelector("[data-download-pdf]").href = url;
    function print() {
        try { frame.contentWindow.focus(); frame.contentWindow.print(); }
        catch (_) { /* Native viewer controls remain available. */ }
    }
    frame.addEventListener("load", () => window.setTimeout(print, 350), {once: true});
    document.querySelector("[data-print-pdf]").addEventListener("click", print);
    frame.src = url;
    window.addEventListener("pagehide", () => URL.revokeObjectURL(url), {once: true});
})();
