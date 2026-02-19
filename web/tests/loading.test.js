import test from 'node:test';
import assert from 'node:assert/strict';

import { buildLoadedDataset, inferDelimiter, splitLine } from '../data.js';

test('inferDelimiter prefers tab when header contains tabs', ()=>{
  assert.equal(inferDelimiter('a\tb\tc'), '\t');
  assert.equal(inferDelimiter('a,b,c'), ',');
});

test('splitLine supports double-quoted CSV fields and escaped quotes', ()=>{
  const parts = splitLine('a,"b,c","d""e",f', ',');
  assert.deepEqual(parts, ['a', 'b,c', 'd"e', 'f']);
});

test('buildLoadedDataset accepts common header variants and quoted fields', ()=>{
  const csv = [
    'Cell ID,X coordinate,Y coordinate,Cell Type,EPCAM,CD3E',
    'cell_001,0.10,0.05,Epithelial,3.2,0.0',
    '"cell_002",-0.12,-0.08,"T cell, CD8",0.1,2.8',
  ].join('\n');

  const ds = buildLoadedDataset(csv, 'example.csv');
  assert.equal(ds.cells.length, 2);
  assert.equal(ds.genePanel.length, 2);
  assert.deepEqual(ds.genePanel, ['EPCAM','CD3E']);
  assert.equal(ds.cells[1].cell_id, 'cell_002');
  assert.equal(ds.cells[1].type, 'T cell, CD8');
});

test('buildLoadedDataset parses TSV', ()=>{
  const tsv = [
    'cell_id\tx\ty\tcell_type\tEPCAM',
    'c1\t1\t2\tEpithelial\t3.14',
  ].join('\n');

  const ds = buildLoadedDataset(tsv, 'example.tsv');
  assert.equal(ds.delim, '\t');
  assert.equal(ds.cells.length, 1);
  assert.equal(ds.cells[0].cell_id, 'c1');
  assert.equal(ds.cells[0].x, 1);
  assert.equal(ds.cells[0].y, 2);
});

test('buildLoadedDataset throws a helpful error when required columns are missing', ()=>{
  const csv = [
    'id,x,y',
    'c1,0,0',
  ].join('\n');

  assert.throws(()=>buildLoadedDataset(csv, 'bad.csv'), /Missing required columns/);
});

