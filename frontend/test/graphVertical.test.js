import assert from 'node:assert/strict';
import test from 'node:test';
import { layoutGraph, NODE_HEIGHT } from '../src/graphLayout.js';
test('vertical layout preserves source-to-target direction', () => {
  const nodes = [{id:'source'}, {id:'target'}];
  const edges = [{id:'link', from_id:'source', to_id:'target'}];
  const result = layoutGraph(nodes, edges, 'TB');
  assert.ok(result.nodes[0].position.y + NODE_HEIGHT < result.nodes[1].position.y);
});
