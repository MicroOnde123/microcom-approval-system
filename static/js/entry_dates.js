'use strict';

function parseEntryDate(value) {
    let match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
    if (!match) {
        const french = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value.trim());
        if (french) match = [french[0], french[3], french[2], french[1]];
    }
    if (!match) return null;
    const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
    const result = new Date(0);
    result.setUTCFullYear(year, month - 1, day);
    result.setUTCHours(12, 0, 0, 0);
    return year >= 1 && result.getUTCFullYear() === year && result.getUTCMonth() === month - 1 && result.getUTCDate() === day ? result : null;
}

function isoEntryDate(date) {
    return `${String(date.getUTCFullYear()).padStart(4, '0')}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
}

function formatEntryDate(date, language) {
    const iso = isoEntryDate(date);
    return language === 'fr' ? `${iso.slice(8)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : iso;
}

function shiftEntryMonth(date, amount) {
    const result = new Date(date);
    const day = result.getUTCDate();
    result.setUTCDate(1);
    result.setUTCMonth(result.getUTCMonth() + amount);
    const last = new Date(result);
    last.setUTCMonth(last.getUTCMonth() + 1, 0);
    result.setUTCDate(Math.min(day, last.getUTCDate()));
    return result;
}

function enhanceEntryDate(root, document) {
    const input = root.querySelector('input'), dialog = root.querySelector('dialog');
    const open = root.querySelector('.entry-calendar-open'), days = root.querySelector('.entry-calendar-days');
    // The text field remains fully usable if JavaScript or modal dialogs are unavailable.
    if (!dialog.showModal) return;
    const language = root.dataset.language;
    let focused;
    const monthFormat = new Intl.DateTimeFormat(language, {month: 'long', year: 'numeric', timeZone: 'UTC'});
    const fullFormat = new Intl.DateTimeFormat(language, {dateStyle: 'full', timeZone: 'UTC'});
    const weekdayFormat = new Intl.DateTimeFormat(language, {weekday: 'short', timeZone: 'UTC'});
    const setInput = date => {
        input.value = formatEntryDate(date, language);
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
    };
    function render(focus = true) {
        root.querySelector('[data-month-label]').textContent = monthFormat.format(focused);
        days.replaceChildren();
        const first = new Date(focused); first.setUTCDate(1);
        const mondayOffset = (first.getUTCDay() + 6) % 7;
        for (let index = 0; index < 7; index++) {
            const label = document.createElement('span');
            label.textContent = weekdayFormat.format(new Date(Date.UTC(2024, 0, 1 + index)));
            label.setAttribute('aria-hidden', 'true'); days.append(label);
        }
        for (let index = 0; index < mondayOffset; index++) {
            const blank = document.createElement('span'); blank.setAttribute('aria-hidden', 'true'); days.append(blank);
        }
        const last = new Date(first); last.setUTCMonth(last.getUTCMonth() + 1, 0);
        const selected = parseEntryDate(input.value);
        for (let day = 1; day <= last.getUTCDate(); day++) {
            const date = new Date(first); date.setUTCDate(day);
            const button = document.createElement('button'); button.type = 'button';
            button.textContent = String(day); button.dataset.day = String(day);
            button.setAttribute('aria-label', fullFormat.format(date));
            button.tabIndex = day === focused.getUTCDate() ? 0 : -1;
            if (selected && isoEntryDate(date) === isoEntryDate(selected)) {
                button.setAttribute('aria-pressed', 'true');
            }
            button.addEventListener('click', () => { setInput(date); dialog.close(); input.focus(); });
            button.addEventListener('keydown', event => {
                const delta = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7}[event.key];
                if (delta !== undefined) {
                    const next = new Date(date); next.setUTCDate(next.getUTCDate() + delta); focused = next;
                } else if (event.key === 'PageUp' || event.key === 'PageDown') {
                    focused = shiftEntryMonth(date, event.key === 'PageUp' ? -1 : 1);
                } else if (event.key === 'Home' || event.key === 'End') {
                    focused = new Date(date);
                    const offset = (date.getUTCDay() + 6) % 7;
                    focused.setUTCDate(date.getUTCDate() + (event.key === 'Home' ? -offset : 6 - offset));
                } else return;
                event.preventDefault();
                if (focused.getUTCFullYear() < 1 || focused.getUTCFullYear() > 9999) focused = date;
                render();
            });
            days.append(button);
        }
        if (focus) days.querySelector('[tabindex="0"]').focus();
    }
    open.hidden = false;
    open.addEventListener('click', () => {
        const today = new Date();
        focused = parseEntryDate(input.value) || parseEntryDate(`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`);
        render(false); dialog.showModal(); days.querySelector('[tabindex="0"]').focus();
    });
    root.querySelectorAll('[data-month]').forEach(button => button.addEventListener('click', () => {
        const next = shiftEntryMonth(focused, Number(button.dataset.month));
        if (next.getUTCFullYear() >= 1 && next.getUTCFullYear() <= 9999) focused = next;
        render(false);
    }));
    root.querySelector('[data-calendar-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => open.focus());
    // Submit canonical ISO values without changing the visible value (including on back navigation).
    input.form.addEventListener('formdata', event => {
        const date = parseEntryDate(input.value);
        if (date) event.formData.set(input.name, isoEntryDate(date));
    });
}

if (typeof module !== 'undefined') module.exports = {parseEntryDate, isoEntryDate, formatEntryDate, shiftEntryMonth, enhanceEntryDate};
if (typeof document !== 'undefined') document.querySelectorAll('[data-entry-date]').forEach(root => enhanceEntryDate(root, document));
