import test from 'node:test';
import assert from 'node:assert/strict';

import { evaluateGate } from '../data.js';

function makeCells(exprRows){
  // exprRows: array of objects {id, expr:{GENE:value}}
  const genes = new Set();
  for(const r of exprRows){
    for(const g of Object.keys(r.expr || {})) genes.add(String(g).toUpperCase());
  }
  const genePanel = [...genes].sort();
  const geneIndex = new Map(genePanel.map((g,i)=>[g,i]));
  const cells = exprRows.map(r=>{
    const expr = new Float32Array(genePanel.length);
    for(const [g,v] of Object.entries(r.expr || {})){
      const idx = geneIndex.get(String(g).toUpperCase());
      expr[idx] = Number(v);
    }
    return {id: r.id, expr};
  });
  return {cells, geneIndex, genePanel};
}

function idsFromMask(mask){
  const out = [];
  if(!mask) return out;
  for(let i=0;i<mask.length;i++) if(mask[i]) out.push(i+1);
  return out;
}

test('evaluateGate supports AND/OR/NOT with parentheses', ()=>{
  const {cells, geneIndex} = makeCells([
    {id:1, expr:{A: 1, B: 1, C: 0}}, // A+, B+, C-
    {id:2, expr:{A: 1, B: 0, C: 0}}, // A+, B-, C-
    {id:3, expr:{A: 0, B: 1, C: 1}}, // A-, B+, C+
    {id:4, expr:{A: 1, B: 1, C: 1}}, // A+, B+, C+
  ]);

  const gateConditions = [
    {gene:'A', sense:'pos', cutoff:0.5, join:'AND'}, // label A
    {gene:'B', sense:'pos', cutoff:0.5, join:'AND'}, // label B
    {gene:'C', sense:'pos', cutoff:0.5, join:'AND'}, // label C
  ];

  {
    const {mask, error} = evaluateGate({
      cells,
      geneIndex,
      gateEnabled: true,
      gateConditions,
      gateExpr: 'A AND B AND NOT C',
    });
    assert.equal(error, null);
    assert.deepEqual(idsFromMask(mask), [1]);
  }

  {
    const {mask, error} = evaluateGate({
      cells,
      geneIndex,
      gateEnabled: true,
      gateConditions,
      gateExpr: 'A AND (B OR C)',
    });
    assert.equal(error, null);
    assert.deepEqual(idsFromMask(mask), [1,4]);
  }

  {
    const {mask, error} = evaluateGate({
      cells,
      geneIndex,
      gateEnabled: true,
      gateConditions,
      gateExpr: '(A AND B) OR (C AND NOT A)',
    });
    assert.equal(error, null);
    assert.deepEqual(idsFromMask(mask), [1,3,4]);
  }
});

test('evaluateGate returns a helpful error for unknown labels', ()=>{
  const {cells, geneIndex} = makeCells([
    {id:1, expr:{A: 1}},
  ]);

  const {mask, error, matchCount} = evaluateGate({
    cells,
    geneIndex,
    gateEnabled: true,
    gateConditions: [{gene:'A', sense:'pos', cutoff:0.5, join:'AND'}],
    gateExpr: 'A AND Z',
  });

  assert.equal(mask, null);
  assert.equal(matchCount, 0);
  assert.ok(String(error).includes('Unknown condition label'));
});

test('evaluateGate preserves mask but reports missing genes', ()=>{
  const {cells, geneIndex} = makeCells([
    {id:1, expr:{A: 1}},
    {id:2, expr:{A: 0}},
  ]);

  const {mask, error, matchCount} = evaluateGate({
    cells,
    geneIndex,
    gateEnabled: true,
    gateConditions: [
      {gene:'A', sense:'pos', cutoff:0.5, join:'AND'}, // label A
      {gene:'MISSING', sense:'pos', cutoff:0.5, join:'AND'}, // label B, gene not in index
    ],
    gateExpr: 'A AND B',
  });

  // Missing gene condition evaluates to all-zero mask; still a valid expression.
  assert.ok(mask instanceof Uint8Array);
  assert.equal(matchCount, 0);
  assert.ok(String(error).includes('Missing genes: MISSING'));
});
