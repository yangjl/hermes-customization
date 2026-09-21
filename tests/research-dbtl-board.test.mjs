import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const {groupCycles} = runInNewContext(readFileSync(new URL('../plugins/research-dbtl/assets/board-model.js', import.meta.url),'utf8')+';({groupCycles})');
test('folds complete cycles without mutating task state; stale/mixed cycles stay active',()=>{
 const tasks=[{cycle:1,status:'done'},{cycle:2,status:'done'},{cycle:2,status:'review'},{cycle:3,status:'done',stale:true}];
 const before=JSON.stringify(tasks),groups=groupCycles(tasks);
 assert.deepEqual(Array.from(groups,g=>g.completed),[true,false,false]);
 assert.equal(JSON.stringify(tasks),before);assert.equal(groupCycles([]).length,0);
 assert.equal(groupCycles([{cycle:1,status:'done'}])[0].completed,true);
});
