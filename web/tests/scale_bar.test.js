import test from 'node:test';
import assert from 'node:assert/strict';

import { niceStep, formatLengthUm, computeScaleBar } from '../scale_bar.js';

test('niceStep uses 1-2-5-10 progression', ()=>{
  assert.equal(niceStep(0.9), 1);
  assert.equal(niceStep(1.1), 2);
  assert.equal(niceStep(2.1), 5);
  assert.equal(niceStep(5.1), 10);

  assert.equal(niceStep(21), 50);
  assert.equal(niceStep(55), 100);
});

test('formatLengthUm formats mm and µm sensibly', ()=>{
  assert.equal(formatLengthUm(5), '5.0 µm');
  assert.equal(formatLengthUm(12), '12 µm');
  assert.equal(formatLengthUm(1500), '1.5 mm');
  assert.equal(formatLengthUm(12000), '12 mm');
});

test('computeScaleBar returns null without calibration', ()=>{
  assert.equal(computeScaleBar({umPerPixel: 0, viewScale: 200}), null);
  assert.equal(computeScaleBar({umPerPixel: 1, viewScale: 0}), null);
});

test('computeScaleBar returns positive px and label', ()=>{
  const bar = computeScaleBar({umPerPixel: 1, viewScale: 240, targetPx: 110});
  assert.ok(bar);
  assert.ok(bar.barUm > 0);
  assert.ok(bar.barPx > 0);
  assert.equal(typeof bar.label, 'string');
  assert.ok(bar.label.length > 0);
});
