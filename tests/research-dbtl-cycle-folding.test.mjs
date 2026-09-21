import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const html=readFileSync(new URL('../sketches/research-dbtl-cycle-folding/index.html',import.meta.url),'utf8');
const model=html.match(/<script id="model">([\s\S]*?)<\/script>/)[1];
const {groupCycles,tasks}=runInNewContext(`${model};({groupCycles,tasks})`);
test('completed cycles fold while active cycle remains visible',()=>{
 const groups=groupCycles(tasks);
 assert.equal(groups.filter(g=>g.completed).length,7);
 assert.equal(groups.filter(g=>!g.completed).length,1);
 assert.equal(groups.find(g=>!g.completed).cycle,8);
});
test('any unfinished or stale task keeps its entire cycle visible',()=>{
 for(const state of ['ready','todo','running','review','blocked','failed']){
  const g=groupCycles([{cycle:1,status:'done'},{cycle:1,status:state}]);
  assert.equal(g[0].completed,false);
 }
 assert.equal(groupCycles([{cycle:1,status:'done',stale:true}])[0].completed,false);
});
test('grouping preserves task state and evidence references',()=>{
 const source=[{id:'b',cycle:1,status:'done',submission:{id:'pin'}},{id:'l',cycle:1,status:'done',source:'b'}];
 const before=JSON.stringify(source);groupCycles(source);
 assert.equal(JSON.stringify(source),before);
 assert.equal(groupCycles(source)[0].tasks[0],source[0]);
 assert.equal(groupCycles([]).length,0);
});
const {resolveSettings}=runInNewContext(`${model};({resolveSettings})`);
test('task overrides replace only selected defaults, including explicit blanks',()=>{
 const defaults={folder:'/example/project',repo:'/example/project',skills:'research-dbtl',instructions:'Read notes'};
 const override={folder:'/example/task',skills:''};
 const actual=resolveSettings(defaults,override);
 assert.equal(actual.folder,'/example/task');assert.equal(actual.skills,'');
 assert.equal(actual.repo,defaults.repo);assert.equal(actual.instructions,defaults.instructions);
 defaults.instructions='Updated notes';assert.equal(resolveSettings(defaults,override).instructions,'Updated notes');
 assert.equal(override.instructions,undefined);
});
