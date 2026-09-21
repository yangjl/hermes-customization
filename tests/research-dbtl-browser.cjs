// Optional real-browser proof: uses an existing Playwright/Chromium installation.
// All tasks and evidence below are synthetic and live in a disposable native board.
const {execFileSync,spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const hermesSource = process.env.HERMES_SOURCE_DIR || path.join(os.homedir(), '.hermes/hermes-agent');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || path.join(hermesSource, 'node_modules/playwright'));
const base = fs.mkdtempSync(path.join(os.tmpdir(),'dbtl-live-'));
const project = path.join(base,'research'); fs.mkdirSync(project);
const python=process.env.DBTL_PYTHON || path.join(hermesSource,'venv/bin/python');
const tool=path.resolve(__dirname,'../plugins/research-dbtl/scripts/dbtl.py');
const env={...process.env,HERMES_HOME:path.join(base,'hermes'),HERMES_SOURCE_DIR:hermesSource};
const shots=process.env.DBTL_SCREENSHOT_DIR || path.join(os.tmpdir(),'research-dbtl-screenshots');
fs.mkdirSync(shots,{recursive:true});
const cli=(...args)=>JSON.parse(execFileSync(python,[tool,'--project',project,...args],{env,encoding:'utf8'}));
const status=()=>cli('status');
const get=id=>status().tasks.find(t=>t.id===id);
function create(phase,title,parent){return cli('create','--phase',phase,'--title',title,'--brief','Synthetic check: bounded fixture only; no external data.',...(parent?['--parent',parent]:[])).task_id;}
function submit(id,file,text){fs.writeFileSync(path.join(project,file),text);const l=cli('claim','--task',id,'--actor',get(id).actor);return cli('submit','--task',id,`--token=${l.token}`,'--run',String(l.run_id),'--summary',text,'--artifact',file);}
cli('init','--name','Synthetic integration demo','--board','dbtl-verification');
(async()=>{
 let browser,server;
 try{
 server=spawn(python,[tool,'--project',project,'serve'],{env,stdio:['ignore','pipe','pipe']});
 let url=await new Promise((resolve,reject)=>{let output='';server.stdout.on('data',data=>{output+=data; if(output.includes('\n'))resolve(output.trim());});server.on('error',reject);server.on('exit',code=>reject(new Error(`Server exited ${code}`)));});
 const origin=new URL(url).origin, token=new URLSearchParams(new URL(url).hash.slice(1)).get('token');
 browser=await chromium.launch({headless:true,executablePath:process.env.DBTL_CHROMIUM_EXECUTABLE || undefined});
 const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const shot=name=>page.screenshot({path:path.join(shots,`research-dbtl-live-${name}.png`),fullPage:true});
 const refresh=async()=>{await page.getByRole('button',{name:'Refresh tasks'}).click();await page.getByText('Up to date.',{exact:true}).waitFor();};
 async function keyActivate(selector){for(let i=0;i<65;i++){if(await page.locator(selector).evaluate(e=>e===document.activeElement)){await page.keyboard.press('Enter');return;}await page.keyboard.press('Tab');}throw new Error('Keyboard cannot reach '+selector);}
 await page.goto(url);await page.getByText('Start with a research question').waitFor(); await shot('empty');
 assert.equal(new URL(page.url()).hash,'');
 const design=create('design','Define the comparison');submit(design,'design-r1.md','Compare the measured groups; keep interpretation within this sample.');await refresh();await shot('review');
 await page.locator('#decision-note').fill('State the cohort limitation.');
 await keyActivate('#detail > button.secondary');await page.getByText('Correction requested.',{exact:true}).waitFor();assert.equal(get(design).status,'ready');
 submit(design,'design-r2.md','Revised protocol: measured cohort only; transfer is untested.');await refresh();
 await keyActivate('#detail button.primary');await page.getByText('Submission approved.',{exact:true}).waitFor();assert.equal(get(design).status,'done');
 const build=create('build','Estimate the signal',design);submit(build,'build-r1.txt','Internal analysis complete. Routine checks passed; transfer remains untested.');await refresh();await page.locator(`[data-task-id="${build}"]`).click();
 await page.getByRole('button',{name:'Approve submission'}).click();await page.getByText('Submission approved.',{exact:true}).waitFor();
 const learn=create('learn','Prepare the internal report',build);submit(learn,'report-r1.md','Internal figure and interpretation submitted; manuscript admission is separate.');await refresh();await page.locator(`[data-task-id="${learn}"]`).click();await shot('populated');
 await page.getByRole('button',{name:'Project roles',exact:true}).click();await page.selectOption('#role-coordinator','hermes');await page.selectOption('#role-learn','codex');await page.getByRole('button',{name:'Save roles'}).click();await page.getByText('Role defaults saved. Existing task owners are unchanged.').waitFor();
 assert.equal(status().project.roles.coordinator,'hermes');assert.equal(get(learn).actor,'claude');
 await page.getByRole('button',{name:'Project roles',exact:true}).click();await page.selectOption('#role-coordinator','codex');await page.getByRole('button',{name:'Save roles'}).click();await page.getByText('Role defaults saved. Existing task owners are unchanged.').waitFor();

 // Exercise the real image API only against this disposable project.
 const avatarBefore = status();
 const png = await page.evaluate(() => {
   const canvas = document.createElement('canvas'); canvas.width = 80; canvas.height = 40;
   const ctx = canvas.getContext('2d'); ctx.fillStyle = '#27664f'; ctx.fillRect(0,0,80,40);
   ctx.fillStyle = 'white'; ctx.font = '24px sans-serif'; ctx.fillText('A',30,28);
   return canvas.toDataURL('image/png');
 });
 const imageFile = {name:'avatar.png',mimeType:'image/png',buffer:Buffer.from(png.split(',')[1],'base64')};
 const upload = async () => {
   await page.locator('#avatar-file').setInputFiles(imageFile);
   await page.waitForFunction(() => !document.getElementById('save-avatars').disabled);
   await page.waitForFunction(() => document.querySelector('#large-avatar img')?.naturalWidth === 256);
 };
 await keyActivate('#avatars-button'); await page.locator('#avatars-dialog').waitFor({state:'visible'});
 await upload(); assert.equal(await page.locator('.card .avatar img').count(),0);
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 assert.deepEqual(status().project.avatars,{});
 await page.locator('#avatars-button').click();
 await page.locator('#avatar-file').setInputFiles({name:'bad.txt',mimeType:'text/plain',buffer:Buffer.from('invalid')});
 assert.match(await page.locator('#avatars-error').innerText(),/PNG, JPG or WebP/);
 await page.locator('#avatar-file').setInputFiles({name:'bad.png',mimeType:'image/png',buffer:Buffer.from('broken')});
 await page.getByText('This image could not be opened. Try another picture.').waitFor(); await shot('avatars-failure');
 for (const who of ['codex','claude','hermes']) {
   await page.locator(`[data-agent="${who}"]`).click(); await upload();
 }
 await shot('avatars-editor');
 let saveRelease;
 const saveGate = new Promise(resolve => {saveRelease=resolve;});
 await page.route('**/api/action',async route => {await saveGate;await route.continue();});
 await page.getByRole('button',{name:'Save avatars',exact:true}).click();
 await page.getByText('Saving avatars…').waitFor();
 assert.equal(await page.locator('#cancel-avatars').isDisabled(),true);
 assert.equal(await page.locator('#upload-avatar').isDisabled(),true);
 assert.equal(await page.locator('.agent-tab:enabled').count(),0);
 await page.keyboard.press('Escape');assert.equal(await page.locator('#avatars-dialog').isVisible(),true);
 await shot('avatars-saving'); saveRelease();
 await page.getByText('Agent avatars saved.',{exact:true}).waitFor(); await page.unroute('**/api/action');
 const savedAvatars = status().project.avatars;
 assert.deepEqual(Object.keys(savedAvatars).sort(),['claude','codex','hermes']);
 for (const img of await page.locator('.card .avatar img').all()) assert.match(await img.getAttribute('src'),/^data:image\/png;base64,/);
 assert.equal(await page.locator('.card .avatar img').count(),3);
 assert.equal(await page.locator('#agents .avatar img').count(),5);
 assert.equal(await page.locator('#detail .avatar img').count(),1);
 assert.equal(await page.locator('#avatars-button').evaluate(el=>el===document.activeElement),true);
 await page.reload(); await page.getByText('Up to date.',{exact:true}).waitFor();
 assert.equal(await page.locator('.card .avatar img').count(),3);await shot('avatars-cards');
 // Partial patch: an unedited actor can change while this editor remains open.
 await page.locator('#avatars-button').click();await page.locator('#remove-avatar').click();
 const otherEdit=await page.request.post(origin+'/api/action',{headers:{Authorization:'Bearer '+token,Origin:origin},data:{action:'avatars',avatars:{hermes:null}}});
 assert.equal(otherEdit.status(),200);
 await page.route('**/api/action',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'Synthetic save failure'})}));
 await page.getByRole('button',{name:'Save avatars',exact:true}).click();await page.getByText('Synthetic save failure',{exact:true}).waitFor();
 assert.equal(await page.locator('#avatars-dialog').isVisible(),true);
 assert.equal(await page.locator('#large-avatar').innerText(),'Cx');
 assert.equal(status().project.avatars.codex,savedAvatars.codex);
 await shot('avatars-save-failure');await page.unroute('**/api/action');
 await page.getByRole('button',{name:'Save avatars',exact:true}).click();await page.locator('#avatars-dialog').waitFor({state:'hidden'});
 assert.deepEqual(Object.keys(status().project.avatars),['claude']);
 assert.equal(await page.locator('.card .avatar.codex img').count(),0);
 assert.equal(await page.locator('.card .avatar.codex').first().innerText(),'Cx');
 assert.deepEqual(status().project.roles,avatarBefore.project.roles);
 assert.deepEqual(status().tasks,avatarBefore.tasks);
 await page.locator('#avatars-button').click();await upload();await page.getByRole('button',{name:'Save avatars',exact:true}).click();await page.locator('#avatars-dialog').waitFor({state:'hidden'});
 await page.setViewportSize({width:375,height:850});await shot('avatars-narrow-cards');
 await page.locator('#avatars-button').click();await shot('avatars-narrow-editor');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.keyboard.press('Escape');assert.equal(await page.locator('#avatars-dialog').isVisible(),false);
 assert.equal(await page.locator('#avatars-button').evaluate(el=>el===document.activeElement),true);
 await page.setViewportSize({width:1440,height:900});
 fs.writeFileSync(path.join(project,'build-r1.txt'),'Upstream changed after review');await refresh();assert.equal(await page.getByRole('button',{name:'Approve submission'}).isDisabled(),true);await shot('stale');
 const forged=await page.request.post(origin+'/api/action',{headers:{Authorization:'Bearer '+token,Origin:origin},data:{action:'approve',task_id:learn,submission_id:get(learn).submission.id}});assert.equal(forged.status(),400);
 assert.equal((await page.request.get(origin+'/api/snapshot')).status(),401);
 assert.equal((await page.request.get(origin+'/api/snapshot',{headers:{Authorization:'Bearer '+token,Host:'evil.example'}})).status(),403);
 assert.equal((await page.request.post(origin+'/api/action',{headers:{Authorization:'Bearer '+token,Origin:'https://evil.example'},data:{action:'roles',roles:{coordinator:'claude'}}})).status(),403);
 assert.equal(status().project.roles.coordinator,'codex');
 await page.setViewportSize({width:375,height:850});await shot('narrow');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await keyActivate('#detail .back');assert.equal(await page.locator(`[data-task-id="${learn}"]`).evaluate(el=>el===document.activeElement),true);
 await page.setViewportSize({width:1440,height:900});
 await page.route('**/api/snapshot',route=>route.abort());await page.getByRole('button',{name:'Refresh tasks'}).click();await page.getByRole('heading',{name:'Records unavailable'}).waitFor();await shot('failure');await page.unroute('**/api/snapshot');await page.getByRole('button',{name:'Retry',exact:true}).click();await page.getByText('Up to date.',{exact:true}).waitFor();
 let release;const gate=new Promise(r=>release=r);await page.route('**/api/snapshot',async route=>{await gate;await route.continue();});await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('heading',{name:'Loading evidence…'}).waitFor();await shot('loading');release();await page.getByText('Up to date.',{exact:true}).waitFor();await page.unroute('**/api/snapshot');
 assert.deepEqual(errors,[]);
 console.log('PASS: real native board, keyboard correction/revision/approval, Design→Build→Learn, role change without ownership theft, stale evidence rejection, local HTTP authorization/Origin/Host, empty/loading/failure/retry, 375px layout.');
 console.log('PASS: avatars for all agents, card/chip/detail images, PNG normalization, cancel/draft isolation, partial updates, save failure/retry, saving lock/Escape, remove/initials, reload persistence, unchanged tasks/roles, keyboard and narrow layout.');
 console.log('Screenshots: '+shots+'/research-dbtl-live-*.png');
 }finally{if(browser)await browser.close();if(server)server.kill('SIGTERM');fs.rmSync(base,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
