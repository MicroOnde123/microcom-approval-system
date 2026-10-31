/* Presentation only. Services validate quantities, permissions and every write. */
(function () {
    "use strict";
    function cents(value) {
        const text = String(value).trim().replace(",", ".");
        if (!/^(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$/.test(text)) return null;
        const parts = text.split(".");
        const amount = Number(parts[0] || "0") * 100 + Number((parts[1] || "").padEnd(2, "0"));
        return Number.isSafeInteger(amount) ? amount : null;
    }
    function amount(value) { return (value / 100).toFixed(2); }
    function remaining(issued, returned, client, microcom) {
        const values = [issued, returned, client, microcom].map(cents);
        if (values.some(value => value === null)) return null;
        const result = values[0] - values[1] - values[2] - values[3];
        return result >= 0 ? amount(result) : null;
    }
    if (typeof module !== "undefined" && module.exports) module.exports = { cents, remaining };
    if (typeof document === "undefined") return;
    const root = document.querySelector("[data-material-operations]");
    if (!root) return;
    const tabs = Array.from(root.querySelectorAll('[role="tab"]'));
    function activateTab(name, { focus = false, historyMode = null } = {}) {
        const selected = tabs.find(tab => tab.dataset.tab === name) || tabs[0];
        tabs.forEach(tab => {
            const active = tab === selected;
            tab.setAttribute("aria-selected", String(active));
            tab.tabIndex = active ? 0 : -1;
            document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
        });
        if (focus) selected.focus();
        if (historyMode) {
            const url = new URL(window.location.href);
            url.searchParams.set("tab", selected.dataset.tab);
            if (url.href !== window.location.href) window.history[historyMode + "State"]({}, "", url);
        }
    }
    tabs.forEach((tab, index) => {
        tab.addEventListener("click", event => {
            if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            activateTab(tab.dataset.tab, { historyMode: "push" });
        });
        tab.addEventListener("keydown", event => {
            const offsets = { ArrowRight: 1, ArrowLeft: -1 };
            let target;
            if (event.key in offsets) target = (index + offsets[event.key] + tabs.length) % tabs.length;
            else if (event.key === "Home") target = 0;
            else if (event.key === "End") target = tabs.length - 1;
            else if (event.key === " ") target = index;
            else return;
            event.preventDefault();
            activateTab(tabs[target].dataset.tab, { focus: true, historyMode: "push" });
        });
    });
    if (tabs.length) {
        activateTab((tabs.find(tab => tab.getAttribute("aria-selected") === "true") || tabs[0]).dataset.tab);
        window.addEventListener("popstate", () => activateTab(new URL(window.location.href).searchParams.get("tab")));
        root.addEventListener("invalid", event => {
            const panel = event.target.closest('[role="tabpanel"]');
            if (panel) activateTab(panel.id.replace("panel-", ""));
            let details = event.target.closest("details");
            while (details) { details.open = true; details = details.parentElement.closest("details"); }
        }, true);
    }
    const dialog = root.querySelector("[data-review-dialog]");
    let pending = null;
    let trigger = null;
    function cancel() {
        if (dialog.open) dialog.close();
        pending = null;
        if (trigger) trigger.focus();
    }
    dialog.querySelector("[data-review-cancel]").addEventListener("click", cancel);
    dialog.addEventListener("cancel", () => { pending = null; if (trigger) trigger.focus(); });
    dialog.querySelector("[data-review-confirm]").addEventListener("click", () => {
        const form = pending;
        pending = null;
        dialog.close();
        if (form) { form.dataset.reviewed = "yes"; form.requestSubmit(); }
    });
    function review(form, lines) {
        const list = document.createElement("ul");
        lines.forEach(text => { const item = document.createElement("li"); item.textContent = text; list.append(item); });
        dialog.querySelector("#ops-review-title").textContent = form.dataset.reviewTitle;
        dialog.querySelector("[data-review-content]").replaceChildren(list);
        pending = form;
        trigger = document.activeElement;
        if (typeof dialog.showModal === "function") dialog.showModal();
        else if (window.confirm(form.dataset.reviewTitle + "\n" + lines.join("\n"))) {
            form.dataset.reviewed = "yes"; form.requestSubmit();
        }
    }
    const reconciliation = root.querySelector("[data-reconciliation-form]");
    if (reconciliation) {
        const rows = Array.from(reconciliation.querySelectorAll("[data-material-row]"));
        rows.forEach(row => {
            const input = key => row.querySelector('[data-outcome="' + key + '"]');
            const choice = row.querySelector("[data-outcome-choice]");
            const quick = row.querySelector("[data-quick-outcome]");
            const issued = cents(row.dataset.issued), returned = cents(row.dataset.returned);
            if (issued === null || returned === null || returned > issued) return;
            quick.hidden = issued === returned;
            const active = ["CLIENT", "MICROCOM", "RETAINED"].filter(key => cents(input(key).value) > 0);
            choice.value = active.length === 1 ? active[0] : "SPLIT";
            function validate() {
                const keys = ["CLIENT", "MICROCOM", "RETAINED", "RETURNED"];
                const values = keys.map(key => cents(input(key).value));
                const valid = values.every(value => value !== null) && values.reduce((a,b) => a+b, 0) === issued && values[3] === returned;
                input("CLIENT").setCustomValidity(valid ? "" : reconciliation.dataset.invalid);
                row.querySelector("[data-row-feedback]").textContent = valid ? "" : reconciliation.dataset.invalid;
                if (!valid) row.open = true;
                return valid;
            }
            function visibility() {
                // Split mode exposes quantities; single-outcome mode records all nonreturned units.
                row.querySelector(".ops-quantities").hidden = choice.value !== "SPLIT";
            }
            choice.addEventListener("change", () => {
                if (choice.value !== "SPLIT") {
                    ["CLIENT", "MICROCOM", "RETAINED"].forEach(key => { input(key).value = key === choice.value ? amount(issued-returned) : "0.00"; });
                    input("RETURNED").value = amount(returned);
                }
                visibility(); validate();
            });
            ["CLIENT", "MICROCOM"].forEach(key => input(key).addEventListener("input", () => {
                const result = remaining(row.dataset.issued, row.dataset.returned, input("CLIENT").value, input("MICROCOM").value);
                if (result !== null) input("RETAINED").value = result;
                validate();
            }));
            ["RETAINED", "RETURNED"].forEach(key => input(key).addEventListener("input", validate));
            // Never repair stale or invalid posted values on load.
            if (!validate()) choice.value = "SPLIT";
            visibility();
        });
        reconciliation.addEventListener("submit", event => {
            if (reconciliation.dataset.reviewed === "yes") { delete reconciliation.dataset.reviewed; return; }
            event.preventDefault();
            const lines = rows.map(row => row.dataset.name + ": " + Array.from(row.querySelectorAll("[data-outcome]")).map(input => {
                const label = row.querySelector('label[for="' + input.id + '"]');
                return label.textContent.trim() + " " + input.value;
            }).join(" · "));
            review(reconciliation, lines);
        });
    }
    const receipt = root.querySelector("[data-receipt-form]");
    if (receipt) receipt.addEventListener("submit", event => {
        if (receipt.dataset.reviewed === "yes") { delete receipt.dataset.reviewed; return; }
        event.preventDefault();
        const checked = Array.from(receipt.querySelectorAll('input[name="movements"]:checked'));
        const selectionError = receipt.querySelector('[data-selection-error]');
        if (!checked.length) {
            selectionError.hidden = false;
            const first = receipt.querySelector('input[name="movements"]');
            if (first) first.focus();
            return;
        }
        selectionError.hidden = true;
        review(receipt, checked.map(input => input.closest("label").textContent.trim()));
    });
    root.querySelectorAll("[data-return-form]").forEach(form => form.addEventListener("submit", event => {
        if (form.dataset.reviewed === "yes") { delete form.dataset.reviewed; return; }
        event.preventDefault();
        const quantity = form.querySelector('[name="quantity"]');
        const reason = form.querySelector('[name="reason"]');
        const quantityLabel = form.querySelector('label[for="' + quantity.id + '"]').textContent;
        review(form, [form.dataset.name, quantityLabel + ": " + quantity.value, reason.value]);
    }));
}());
