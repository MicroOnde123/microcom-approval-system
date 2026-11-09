/* No profile values are inserted as HTML. The server validates every selection. */
(() => {
    "use strict";
    document.querySelectorAll("[data-agent-picker]").forEach(root => {
        if (root.dataset.ready) return;
        root.dataset.ready = "1";
        const find = s => root.querySelector(s), hidden = find('[name="agent_selections"]');
        const search = find('[role="combobox"]'), results = find('[role="listbox"]');
        const dropdown = find('[data-dropdown]'), status = find('[data-status]');
        const first = find('#agent-first'), surname = find('#agent-surname');
        const infoToggle = find('[data-agent-info-toggle]'), infoContent = find('[data-agent-info-content]');
        function setInfo(open, restoreFocus = false) {
            infoContent.hidden = !open;
            infoToggle.setAttribute('aria-expanded', String(open));
            if (open) infoToggle.setAttribute('aria-describedby', infoContent.id);
            else infoToggle.removeAttribute('aria-describedby');
            if (restoreFocus) infoToggle.focus();
        }
        infoToggle.addEventListener('click', () => setInfo(infoContent.hidden));
        document.addEventListener('pointerdown', event => {
            if (!infoContent.hidden && !infoToggle.contains(event.target) && !infoContent.contains(event.target)) setInfo(false);
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !infoContent.hidden) {
                event.preventDefault();
                setInfo(false, true);
            }
        });
        let people = [], editing = null, page = 1, generation = 0, timer, controller;
        let options = [], active = -1;
        try {
            const parsed = JSON.parse(hidden.value || '[]');
            if (!Array.isArray(parsed) || parsed.some(person => !person || typeof person !== 'object' || Array.isArray(person))) throw Error();
            people = parsed;
        } catch (_) { status.textContent = root.dataset.invalid; }
        let legacy = !!root.dataset.legacy;
        if (legacy) hidden.value = '';
        function say(message) { status.textContent = message; }
        function close() { dropdown.hidden = true; search.setAttribute('aria-expanded', 'false'); search.removeAttribute('aria-activedescendant'); active = -1; }
        function button(label, action) {
            const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
            b.addEventListener('click', action); return b;
        }
        function render() {
            if (!legacy) hidden.value = JSON.stringify(people);
            find('[data-tags]').replaceChildren();
            people.forEach((person, index) => {
                const tag = document.createElement('span'); tag.className = 'agent-tag';
                const label = document.createElement('span'); label.textContent = person.full_name;
                tag.append(label);
                if (person.kind === 'manual') {
                    const edit = button('✎', () => openManual(index));
                    edit.setAttribute('aria-label', root.dataset.edit + ': ' + person.full_name);
                    edit.title = root.dataset.edit;
                    tag.append(edit);
                }
                const remove = button('×', () => { people.splice(index, 1); editing = null; find('[data-manual-form]').hidden = true; render(); search.focus(); });
                remove.setAttribute('aria-label', root.dataset.remove + ': ' + person.full_name);
                tag.append(remove); find('[data-tags]').append(tag);
            });
            find('[data-counter]').textContent = people.length + ' / 10';
            find('[data-counter]').setAttribute('aria-label', people.length + ' / 10 ' + root.dataset.selected);
            find('[data-manual]').disabled = people.length >= 10;
        }
        async function load(append = false) {
            if (legacy) return;
            const current = ++generation;
            if (controller) controller.abort();
            controller = new AbortController();
            dropdown.hidden = false; search.setAttribute('aria-expanded', 'true');
            if (!append) { page = 1; results.replaceChildren(); options = []; active = -1; search.removeAttribute('aria-activedescendant'); }
            results.setAttribute('aria-busy', 'true'); say(root.dataset.loading);
            find('[data-more]').hidden = true;
            try {
                const url = new URL(root.dataset.url, window.location.origin);
                url.searchParams.set('q', search.value); url.searchParams.set('page', page);
                const response = await fetch(url, {credentials:'same-origin', signal:controller.signal, headers:{'Accept':'application/json'}});
                if (!response.ok) throw Error();
                const data = await response.json();
                if (current !== generation) return;
                data.results.forEach(user => {
                    const option = button(user.name, () => {
                        if (people.some(p => p.kind === 'user' && p.user_id === user.id)) return say(root.dataset.duplicate);
                        if (people.length >= 10) return say(root.dataset.max);
                        people.push({kind:'user', user_id:user.id, full_name:user.name});
                        search.value = ''; say(''); render(); close(); search.focus();
                    });
                    option.tabIndex = -1;
                    option.id = 'agent-option-' + user.id; option.setAttribute('role','option');
                    option.setAttribute('aria-selected', String(people.some(p => p.kind === 'user' && p.user_id === user.id)));
                    results.append(option); options.push(option);
                });
                find('[data-more]').hidden = !data.more;
                say(options.length ? '' : root.dataset.empty);
            } catch (error) { if (error.name !== 'AbortError' && current === generation) say(root.dataset.failed); }
            finally { if (current === generation) results.removeAttribute('aria-busy'); }
        }
        function openManual(index = null) {
            if (index === null && people.length >= 10) return say(root.dataset.max);
            editing = index; close();
            const person = index === null ? {} : people[index];
            first.value = person.first_name || ''; surname.value = person.surname || '';
            find('[data-manual-form]').hidden = false; first.focus();
        }
        search.addEventListener('focus', () => load());
        search.addEventListener('click', () => { if (dropdown.hidden) load(); });
        search.addEventListener('input', () => { clearTimeout(timer); ++generation; if(controller) controller.abort(); timer = setTimeout(() => load(), 200); });
        search.addEventListener('keydown', event => {
            if (event.key === 'Escape') { close(); return; }
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault(); if (dropdown.hidden) { load(); return; }
                if (!options.length) return;
                active = active < 0 ? (event.key === 'ArrowDown' ? 0 : options.length - 1) : (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
                options.forEach((option,index) => option.classList.toggle('agent-active', index === active));
                search.setAttribute('aria-activedescendant', options[active].id);
                options[active].scrollIntoView({block:'nearest'});
            } else if (event.key === 'Enter') {
                event.preventDefault(); if (active >= 0 && options[active] && !dropdown.hidden) options[active].click();
            }
        });
        [first, surname].forEach(input => input.addEventListener('keydown', event => { if(event.key === 'Enter') { event.preventDefault(); find('[data-add]').click(); } }));
        root.addEventListener('keydown', event => { if(event.key === 'Escape') { close(); find('[data-manual-form]').hidden = true; } });
        root.addEventListener('focusout', () => setTimeout(() => { if(!root.contains(document.activeElement)) close(); }, 0));
        find('[data-more]').addEventListener('click', () => { page++; load(true); });
        find('[data-manual]').addEventListener('click', () => openManual());
        find('[data-cancel]').addEventListener('click', () => { editing = null; find('[data-manual-form]').hidden = true; search.focus(); });
        find('[data-add]').addEventListener('click', () => {
            const given = first.value.trim(), family = surname.value.trim();
            if (!given || !family) { say(root.dataset.required); (!given ? first : surname).focus(); return; }
            if (editing === null && people.length >= 10) return say(root.dataset.max);
            const name = given + ' ' + family;
            if (people.some((p,i) => i !== editing && p.full_name.normalize().toLocaleLowerCase() === name.normalize().toLocaleLowerCase()) && !window.confirm(root.dataset.sameName)) return;
            const entry = {kind:'manual', key:editing === null ? (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)) : people[editing].key, first_name:given, surname:family, full_name:name};
            if (editing === null) people.push(entry); else people[editing] = entry;
            editing = null; find('[data-manual-form]').hidden = true; say(''); render(); search.focus();
        });
        if (find('[data-replace]')) find('[data-replace]').addEventListener('click', () => {
            legacy = false; find('[data-legacy-panel]').hidden = true; find('[data-picker-controls]').hidden = false; render(); search.focus();
        });
        render();
    });
})();
