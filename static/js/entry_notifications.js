'use strict';
document.querySelectorAll('[data-entry-notification]').forEach(notice => {
    const dismiss = notice.querySelector('[data-entry-dismiss]');
    if (!dismiss) return;
    dismiss.hidden = false;
    dismiss.addEventListener('click', () => {
        notice.remove();
        // Dismissing must preserve anything already typed into the fresh form.
        const url = new URL(window.location.href);
        url.searchParams.delete('saved_draft');
        window.history.replaceState(null, '', url);
        document.querySelector('.entry-page-header a')?.focus();
    });
});
