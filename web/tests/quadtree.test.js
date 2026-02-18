import test from 'node:test';
import assert from 'node:assert/strict';

import { buildQuadtreeIndex, forEachQuadtreeCandidate } from '../data.js';

function bruteCandidates(points, cx, cy, r){
  const r2 = r*r;
  const out = [];
  for(const p of points){
    const dx = p.x - cx;
    const dy = p.y - cy;
    if(dx*dx + dy*dy <= r2) out.push(p.id);
  }
  out.sort((a,b)=>a-b);
  return out;
}

test('quadtree candidate iteration matches brute force for random queries', ()=>{
  // Deterministic pseudo-random set
  const points = [];
  let seed = 123456789;
  const rand = ()=>{
    seed = (1103515245 * seed + 12345) >>> 0;
    return (seed & 0x7fffffff) / 0x7fffffff;
  };

  for(let i=0;i<2000;i++){
    // clustered distribution
    const a = rand() * Math.PI * 2;
    const rr = Math.pow(rand(), 0.7);
    const x = rr * Math.cos(a);
    const y = rr * Math.sin(a);
    points.push({id: i+1, x, y});
  }

  // Adapt to expected cell array shape (id at index+1)
  const cells = points.map(p=>({id:p.id, x:p.x, y:p.y}));
  const qt = buildQuadtreeIndex(cells, {maxItems: 24, maxDepth: 10, pad: 0});

  for(let q=0;q<50;q++){
    const cx = (rand()*2 - 1) * 1.1;
    const cy = (rand()*2 - 1) * 1.1;
    const r = 0.02 + rand() * 0.25;

    const brute = bruteCandidates(points, cx, cy, r);

    const got = [];
    forEachQuadtreeCandidate(qt, cx, cy, r, (id)=>{
      const p = points[id-1];
      const dx = p.x - cx;
      const dy = p.y - cy;
      if(dx*dx + dy*dy <= r*r) got.push(id);
    });
    got.sort((a,b)=>a-b);

    assert.deepEqual(got, brute);
  }
});
