const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

test('private PDF preview prints on load, supports retry/download and revokes blob', () => {
    let prints = 0, focused = 0, revoked = null;
    const events = {}, frame = {contentWindow: {focus() {focused++;}, print() {prints++;}},
        addEventListener(name, handler) {events[name] = handler;}};
    const download = {}, button = {addEventListener(name, handler) {events.click = handler;}};
    const context = {document: {getElementById() {return {textContent: JSON.stringify(Buffer.from('%PDF-test').toString('base64'))};},
        querySelector(selector) {return selector === '[data-pdf-frame]' ? frame : selector === '[data-download-pdf]' ? download : button;}},
        window: {setTimeout(fn) {fn();}, addEventListener(name, handler) {events[name] = handler;}},
        atob: text => Buffer.from(text, 'base64').toString('binary'), Uint8Array, Blob,
        URL: {createObjectURL(blob) {assert.equal(blob.type, 'application/pdf'); return 'blob:private';}, revokeObjectURL(url) {revoked = url;}}};
    vm.runInNewContext(fs.readFileSync('static/js/document_print.js', 'utf8'), context);
    assert.equal(frame.src, 'blob:private'); assert.equal(download.href, 'blob:private');
    events.load(); events.click(); assert.equal(prints, 2); assert.equal(focused, 2);
    events.pagehide(); assert.equal(revoked, 'blob:private');
});
