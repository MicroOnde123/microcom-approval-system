(function () {
    "use strict";
    const DEBOUNCE_MS = 350;

    function initializeAutoFilters(form) {
        if (form.method.toLowerCase() !== "get" || form.dataset.autoFiltersInitialized) return;
        const results = document.getElementById("live-filter-results");
        if (!results) return;
        form.dataset.autoFiltersInitialized = "true";
        let timer = null, controller = null, version = 0, fallback = false;
        const status = document.createElement("span");
        status.className = "auto-filter-status muted";
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");
        status.hidden = true;
        (form.querySelector(".actions-inline") || form).appendChild(status);

        function notify(phase) {
            form.dispatchEvent(new CustomEvent("auto-filters:updated", {detail: {phase: phase}}));
            document.querySelectorAll("[data-filter-export]").forEach(function (link) {
                link.setAttribute("aria-disabled", phase === "success" ? "false" : "true");
            });
            document.querySelectorAll("[data-filter-dependent]").forEach(function (action) {
                action.querySelectorAll('button[type="submit"]').forEach(function (button) {
                    if (phase === "loading" && !button.dataset.filterWasDisabled) {
                        button.dataset.filterWasDisabled = button.disabled ? "yes" : "no";
                    }
                    if (phase === "loading" || phase === "error") button.disabled = true;
                    else if (button.dataset.filterWasDisabled) {
                        button.disabled = button.dataset.filterWasDisabled === "yes";
                        delete button.dataset.filterWasDisabled;
                    }
                });
            });
        }
        function invalidate() {
            clearTimeout(timer); timer = null; version++;
            if (controller) controller.abort();
        }
        function buildURL(page) {
            const url = new URL(form.action || window.location.pathname, window.location.href);
            url.search = new URLSearchParams(new FormData(form)).toString();
            if (page === null) url.searchParams.delete("page");
            else url.searchParams.set("page", page);
            return url;
        }
        function restoreControls(url) {
            for (const control of form.elements) {
                if (!control.name || control.type === "submit") continue;
                if (control.type === "checkbox" || control.type === "radio") {
                    control.checked = url.searchParams.getAll(control.name).includes(control.value);
                } else if (control.tagName === "SELECT" || control.tagName === "INPUT") {
                    control.value = url.searchParams.get(control.name) || "";
                }
            }
        }
        function validationErrors(updatedForm) {
            if (!updatedForm) return;
            // Keep existing controls/focus; replace only server validation output.
            form.querySelectorAll(".errorlist").forEach(function (node) { node.remove(); });
            updatedForm.querySelectorAll(".errorlist").forEach(function (node) {
                const field = node.classList.contains("nonfield") ? null : node.parentElement.querySelector("[name]");
                const current = field && Array.from(form.elements).find(function (c) { return c.name === field.name; });
                (current ? current.parentElement : form).appendChild(node.cloneNode(true));
            });
            for (const control of form.elements) {
                const updatedControl = Array.from(updatedForm.elements).find(function (c) { return c.name === control.name; });
                if (!updatedControl) continue;
                for (const attribute of ["aria-invalid", "aria-describedby"]) {
                    const value = updatedControl.getAttribute(attribute);
                    if (value) control.setAttribute(attribute, value);
                    else control.removeAttribute(attribute);
                }
            }
        }
        async function loadResults(url, historyMode) {
            invalidate();
            if (url.origin !== window.location.origin || url.pathname !== window.location.pathname) return;
            const current = version;
            controller = new AbortController();
            const signal = controller.signal;
            fallback = false;
            status.hidden = false;
            status.textContent = form.dataset.searchingLabel;
            results.setAttribute("aria-busy", "true");
            results.querySelectorAll('input[type="checkbox"]').forEach(function (box) { box.checked = false; });
            notify("loading");
            try {
                const response = await fetch(url.toString(), {
                    method: "GET", signal: signal, credentials: "same-origin",
                    headers: {"X-Requested-With": "XMLHttpRequest"}
                });
                if (current !== version || signal.aborted) return;
                const finalURL = new URL(response.url || url.toString(), window.location.href);
                if (response.redirected && finalURL.pathname !== url.pathname) {
                    if (finalURL.origin !== window.location.origin) throw new Error("Unexpected redirect");
                    window.location.assign(finalURL.toString()); return;
                }
                if (!response.ok || !(response.headers.get("Content-Type") || "").includes("text/html")) {
                    throw new Error("Invalid filtering response");
                }
                const html = await response.text();
                if (current !== version || signal.aborted) return;
                const parsed = new DOMParser().parseFromString(html, "text/html");
                const updated = parsed.getElementById("live-filter-results");
                if (!updated) throw new Error("Missing results");
                const focusInResults = results.contains(document.activeElement);
                results.innerHTML = updated.innerHTML;
                results.hidden = false;
                if (focusInResults) {
                    const focusTarget = results.querySelector('[tabindex="0"]');
                    if (focusTarget) focusTarget.focus({preventScroll: true});
                }
                validationErrors(parsed.querySelector('form[data-auto-filters="true"]'));
                const target = url.pathname + url.search;
                if (historyMode === "replace") window.history.replaceState({liveFilters: true}, "", target);
                else if (historyMode === "push" && target !== window.location.pathname + window.location.search) {
                    window.history.pushState({liveFilters: true}, "", target);
                }
                const invalid = updated.querySelector(".errorlist");
                status.textContent = invalid ? form.dataset.validationLabel : form.dataset.updatedLabel;
                notify(invalid ? "error" : "success");
            } catch (error) {
                if (current !== version || signal.aborted || error.name === "AbortError") return;
                fallback = true;
                results.hidden = true; // Do not show old data as current results.
                status.textContent = form.dataset.errorLabel;
                notify("error");
            } finally {
                if (current === version) results.removeAttribute("aria-busy");
            }
        }
        function scheduleSearch(event) {
            if (event && event.isComposing) return;
            invalidate();
            notify("loading");
            timer = setTimeout(function () { loadResults(buildURL(null), "replace"); }, DEBOUNCE_MS);
        }
        form.querySelectorAll('input:not([type="hidden"]), select').forEach(function (control) {
            if (control.disabled) return;
            if (control.type === "text" || control.type === "search") {
                control.addEventListener("input", scheduleSearch);
                control.addEventListener("compositionend", scheduleSearch);
            } else if (control.type === "date" || control.tagName === "SELECT") {
                control.addEventListener("change", function () { loadResults(buildURL(null), "push"); });
            }
        });
        form.addEventListener("submit", function (event) {
            if (fallback) return; // Explicit Filter action falls back to normal GET.
            event.preventDefault(); loadResults(buildURL(null), "push");
        });
        form.addEventListener("click", function (event) {
            const exportLink = event.target.closest("[data-filter-export]");
            if (exportLink && exportLink.getAttribute("aria-disabled") === "true") {
                event.preventDefault(); return;
            }
            const link = event.target.closest("[data-filter-reset]");
            if (!link || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            const url = new URL(link.href, window.location.href);
            restoreControls(url); loadResults(url, "push");
        });
        results.addEventListener("click", function (event) {
            const link = event.target.closest(".request-list-pagination a");
            if (!link || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault(); loadResults(new URL(link.href, window.location.href), "push");
        });
        window.addEventListener("popstate", function () {
            invalidate();
            const url = new URL(window.location.href);
            restoreControls(url); loadResults(url, null);
        });
    }
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll('form[data-auto-filters="true"]').forEach(initializeAutoFilters);
    });
})();
