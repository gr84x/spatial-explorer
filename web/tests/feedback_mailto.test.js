import test from 'node:test';
import assert from 'node:assert/strict';

import { buildFeedbackMailto, DEFAULT_FEEDBACK_TO } from '../ui.js';

test('buildFeedbackMailto builds a mailto with encoded subject/body', ()=>{
  const href = buildFeedbackMailto({
    name: 'Ada Lovelace',
    email: 'ada@example.com',
    message: 'Hello\nWorld',
    pageHref: 'https://example.com/#v=1',
  });

  const u = new URL(href);
  assert.equal(u.protocol, 'mailto:');
  assert.equal(u.pathname, DEFAULT_FEEDBACK_TO);
  assert.equal(u.searchParams.get('subject'), 'Spatial Explorer feedback');

  const body = u.searchParams.get('body');
  assert.ok(body.includes('Message:\nHello\nWorld'), 'body should include message');
  assert.ok(body.includes('Name: Ada Lovelace'), 'body should include name');
  assert.ok(body.includes('Email: ada@example.com'), 'body should include email');
  assert.ok(body.includes('Page: https://example.com/#v=1'), 'body should include page URL');
});

test('buildFeedbackMailto omits Page line when no pageHref provided', ()=>{
  const href = buildFeedbackMailto({message: ''});
  const u = new URL(href);
  const body = u.searchParams.get('body');
  assert.ok(body.includes('(no message)'), 'empty messages get placeholder');
  assert.ok(!body.includes('Page:'), 'Page line should be omitted');
});

