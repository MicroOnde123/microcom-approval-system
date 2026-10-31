const {test} = require('node:test');
const assert = require('node:assert/strict');
const {cents, remaining} = require('../../static/js/material_operations.js');
test('partial quantities use integer hundredths without floating point drift', () => {
    assert.equal(remaining('1', '.30', '.20', '.10'), '0.40');
    assert.equal(remaining('1.00', '0.30', '0.20', '0.10'), '0.40');
});
test('zero and fully returned quantities remain legitimate', () => {
    assert.equal(cents('0.00'), 0);
    assert.equal(remaining('1', '1', '0', '0'), '0.00');
});
test('comma decimal input is supported', () => assert.equal(cents('12,25'), 1225));
test('excess usage cannot create negative retained quantities', () => assert.equal(remaining('1', '0', '2', '0'), null));
test('malformed, negative and nonfinite values fail closed', () => {
    for (const value of ['', '-1', 'NaN', 'Infinity', '1.001', '1e3', '<script>']) assert.equal(cents(value), null);
});
test('large supported quantities preserve cents', () => assert.equal(cents('99999999.99'), 9999999999));
