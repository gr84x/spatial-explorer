import test from 'node:test';
import assert from 'node:assert/strict';

import { sanitizeForFilename, timestampForFilename } from '../data.js';

test('sanitizeForFilename strips unsafe characters and normalizes whitespace', ()=>{
  assert.equal(sanitizeForFilename('  hello world  '), 'hello-world');
  assert.equal(sanitizeForFilename('A/B\\C:D*E?F"G<H>I|J'), 'A-B-C-D-E-F-G-H-I-J');
  assert.equal(sanitizeForFilename('multi   space\n\tname'), 'multi-space-name');
  assert.equal(sanitizeForFilename('---already---clean---'), 'already-clean');
  assert.equal(sanitizeForFilename(''), '');
});

test('timestampForFilename is ISO-like, stable, and colon-free', ()=>{
  const d = new Date('2026-02-08T16:52:13.456Z');
  const ts = timestampForFilename(d);
  assert.equal(ts, '2026-02-08_165213Z');
  assert.ok(!ts.includes(':'), 'timestamp should not contain colons');
});
