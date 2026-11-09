/* Reuses picker styling; every control and search state is scoped to the site root. */
(() => {
    'use strict';
    document.querySelectorAll('[data-site-picker]').forEach(root => {
        if (root.dataset.ready) return;
        root.dataset.ready = '1';
        const q = selector => root.querySelector(selector);
        const hidden = q('[name=site_selections]'), input = q('#site-search');
        const results = q('[role=listbox]'), dropdown = q('[data-site-dropdown]');
        const manual = q('[data-site-manual-form]'), name = q('#site-manual-name');
        const info = q('[data-site-info-content]'), infoButton = q('[data-site-info-toggle]');
        let sites = [], legacy = !!root.dataset.legacy, editing = null, page = 1, active = -1;
        let options = [], generation = 0, timer, controller;
        const say = message => { q('[data-site-status]').textContent = message; };
        try {
            const parsed = JSON.parse(hidden.value || '[]');
            if (!Array.isArray(parsed) || parsed.some(row => !row || typeof row !== 'object' || Array.isArray(row))) throw Error();
            sites = parsed;
        } catch (_) { say(root.dataset.invalid); }
        if (legacy) hidden.value = '';
        function infoState(open, restore = false) {
            info.hidden = !open; infoButton.setAttribute('aria-expanded', String(open));
            if (open) infoButton.setAttribute('aria-describedby', info.id);
            else infoButton.removeAttribute('aria-describedby');
            if (restore) infoButton.focus();
        }
        infoButton.addEventListener('click', () => infoState(info.hidden));
        document.addEventListener('pointerdown', event => {
            if (!info.hidden && !info.contains(event.target) && !infoButton.contains(event.target)) infoState(false);
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !info.hidden) { event.preventDefault(); infoState(false, true); }
        });
        function button(text, action, label) {
            const element = document.createElement('button'); element.type = 'button'; element.textContent = text;
            if (label) { element.setAttribute('aria-label', label); element.title = label; }
            element.addEventListener('click', action); return element;
        }
        function close() { dropdown.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); active = -1; }
        function render() {
            if (!legacy) hidden.value = JSON.stringify(sites);
            q('[data-site-counter]').textContent = sites.length + ' / 5';
            q('[data-site-counter]').setAttribute('aria-label', sites.length + ' / 5 ' + root.dataset.selected);
            q('[data-site-manual]').disabled = sites.length >= 5;
            q('[data-site-tags]').replaceChildren();
            sites.forEach((site, index) => {
                const tag = document.createElement('span'); tag.className = 'agent-tag';
                const text = document.createElement('span'); text.textContent = site.name; tag.append(text);
                if (site.kind === 'manual') tag.append(button('✎', () => openManual(index), root.dataset.edit + ': ' + site.name));
                tag.append(button('×', () => { sites.splice(index, 1); editing = null; manual.hidden = true; render(); input.focus(); }, root.dataset.remove + ': ' + site.name));
                q('[data-site-tags]').append(tag);
            });
        }
        async function load(append = false) {
            if (legacy) return;
            const current = ++generation;
            if (controller) controller.abort();
            controller = new AbortController();
            if (!append) { page = 1; options = []; active = -1; results.replaceChildren(); input.removeAttribute('aria-activedescendant'); }
            dropdown.hidden = false; input.setAttribute('aria-expanded', 'true');
            results.setAttribute('aria-busy', 'true'); say(root.dataset.loading); q('[data-site-more]').hidden = true;
            try {
                const url = new URL(root.dataset.url, location.origin); url.searchParams.set('q', input.value); url.searchParams.set('page', page);
                const response = await fetch(url, {credentials: 'same-origin', signal: controller.signal, headers: {Accept: 'application/json'}});
                if (!response.ok) throw Error();
                const data = await response.json(); if (current !== generation) return;
                data.results.forEach(site => {
                    const option = button(site.name, () => {
                        if (sites.some(row => row.kind === 'site' && row.site_id === site.id)) return say(root.dataset.duplicate);
                        if (sites.length >= 5) return say(root.dataset.max);
                        sites.push({kind: 'site', site_id: site.id, name: site.name}); input.value = ''; say(''); render(); close(); input.focus();
                    });
                    option.id = 'site-option-' + site.id; option.tabIndex = -1; option.setAttribute('role', 'option');
                    option.setAttribute('aria-selected', String(sites.some(row => row.kind === 'site' && row.site_id === site.id)));
                    options.push(option); results.append(option);
                });
                q('[data-site-more]').hidden = !data.more; say(options.length ? '' : root.dataset.empty);
            } catch (error) { if (error.name !== 'AbortError' && current === generation) say(root.dataset.failed); }
            finally { if (current === generation) results.removeAttribute('aria-busy'); }
        }
        function openManual(index = null) {
            if (index === null && sites.length >= 5) return say(root.dataset.max);
            editing = index; name.value = index === null ? '' : sites[index].name;
            close(); manual.hidden = false; name.focus();
        }
        input.addEventListener('focus', () => load());
        input.addEventListener('click', () => { if (dropdown.hidden) load(); });
        input.addEventListener('input', () => { clearTimeout(timer); ++generation; if (controller) controller.abort(); timer = setTimeout(() => load(), 200); });
        input.addEventListener('keydown', event => {
            if (event.key === 'Escape') return close();
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault(); if (dropdown.hidden) { load(); return; } if (!options.length) return;
                active = active < 0 ? (event.key === 'ArrowDown' ? 0 : options.length - 1) : (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
                options.forEach((option, index) => option.classList.toggle('agent-active', index === active));
                input.setAttribute('aria-activedescendant', options[active].id); options[active].scrollIntoView({block: 'nearest'});
            } else if (event.key === 'Enter') { event.preventDefault(); if (active >= 0 && !dropdown.hidden) options[active].click(); }
        });
        root.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                if (!manual.hidden) { editing = null; manual.hidden = true; input.focus(); }
                close();
            }
        });
        root.addEventListener('focusout', () => setTimeout(() => { if (!root.contains(document.activeElement)) close(); }, 0));
        q('[data-site-more]').addEventListener('click', () => { page++; load(true); });
        q('[data-site-manual]').addEventListener('click', () => openManual());
        q('[data-site-cancel]').addEventListener('click', () => { editing = null; manual.hidden = true; input.focus(); });
        q('[data-site-add]').addEventListener('click', () => {
            const value = name.value.trim();
            if (!value || value.length > 255 || /[\u0000-\u001f\u007f]/.test(value)) { say(root.dataset.required); name.focus(); return; }
            if (editing === null && sites.length >= 5) return say(root.dataset.max);
            if (sites.some((row, index) => index !== editing && row.name.normalize().toLocaleLowerCase() === value.normalize().toLocaleLowerCase()) && !confirm(root.dataset.sameName)) return;
            const entry = {kind: 'manual', key: editing === null ? (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)) : sites[editing].key, name: value};
            if (editing === null) sites.push(entry); else sites[editing] = entry;
            editing = null; manual.hidden = true; say(''); render(); input.focus();
        });
        name.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); q('[data-site-add]').click(); } });
        q('[data-site-replace]')?.addEventListener('click', () => { legacy = false; q('[data-site-legacy]').hidden = true; q('[data-site-controls]').hidden = false; render(); input.focus(); });
        render();
    });
})();
