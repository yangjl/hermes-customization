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
 try {
 server=spawn(python,[tool,'--project',project,'serve'],{env,stdio:['ignore','pipe','pipe']});
 const url=await new Promise((resolve,reject)=>{let output='';server.stdout.on('data',data=>{output+=data;if(output.includes('\n'))resolve(output.trim());});server.on('error',reject);server.on('exit',code=>reject(new Error('Server exited '+code)));});
 browser=await chromium.launch({headless:true,executablePath:process.env.DBTL_CHROMIUM_EXECUTABLE || undefined});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const origin=new URL(url).origin,token=new URLSearchParams(new URL(url).hash.slice(1)).get('token');
 const action=async data=>{const response=await page.request.post(origin+'/api/action',{headers:{Authorization:'Bearer '+token,Origin:origin},data});assert.equal(response.status(),200,await response.text());return response.json();};
 const refresh=async()=>{await page.getByRole('button',{name:'Refresh tasks'}).click();await page.getByText('Up to date.',{exact:true}).waitFor();};
 const shot=name=>page.screenshot({path:path.join(shots,`research-dbtl-settings-${name}.png`),fullPage:true});
 const approve=async id=>action({action:'approve',task_id:id,submission_id:get(id).submission.id});
 const design=create('design','Completed protocol');submit(design,'d.md','Synthetic protocol');await approve(design);
 const build=create('build','Completed Build',design);submit(build,'b.md','Synthetic Build');await approve(build);
 const learn=create('learn','Completed Learn',build);submit(learn,'l.md','Synthetic Learn');await approve(learn);
 const active=cli('create','--phase','design','--title','Review the next comparison','--brief','Synthetic next cycle','--cycle','2').task_id;
 let releaseSettings;const settingsGate=new Promise(resolve=>releaseSettings=resolve);
 await page.route('**/settings.js',async route=>{await settingsGate;await route.continue();});
 let snapshots=0;page.on('request',request=>{if(request.url().endsWith('/api/snapshot'))snapshots++;});
 await page.goto(url,{waitUntil:'commit'});await page.waitForFunction(()=>typeof refresh==='function');
 assert.equal(snapshots,0);releaseSettings();await page.getByText('Up to date.',{exact:true}).waitFor();await page.unroute('**/settings.js');
 assert.equal(await page.locator('#board .card').count(),1);assert.equal(await page.locator('#completed-cycles').evaluate(e=>e.open),false);await shot('collapsed');
 await page.locator('#completed-summary').focus();await page.keyboard.press('Enter');await page.locator('[data-cycle="1"]>summary').click();await page.locator(`[data-task-id="${learn}"]`).click();await shot('expanded');
 await page.reload();await page.getByText('Up to date.',{exact:true}).waitFor();assert.equal(await page.locator('#completed-cycles').evaluate(e=>e.open),true);
 await page.getByRole('button',{name:'Back to active work'}).click();assert.match(await page.locator('#detail h2').innerText(),/next comparison/);
 await page.getByRole('button',{name:'Agent defaults',exact:true}).click();await page.getByRole('button',{name:'Codex',exact:true}).click();
 await page.getByLabel('Instructions',{exact:true}).fill('Read notes and check results.');await page.locator('#setting-skills').fill('research-dbtl, verification-loop');await shot('agent-editor');
 await page.getByRole('button',{name:'Save settings',exact:true}).click();await page.getByText('Agent defaults saved. Existing runs keep their settings.',{exact:true}).waitFor();
 assert.equal(get(active).settings.effective.instructions,'Read notes and check results.');
 const openTask=async()=>{if(!await page.locator('#task-settings').evaluate(e=>e.open))await page.locator('#task-settings>summary').click();await page.getByRole('button',{name:'Edit task settings',exact:true}).click();};
 await openTask();assert.equal(await page.getByRole('checkbox',{name:'Use Codex default for instructions',exact:true}).count(),1);
 await page.locator('#inherit-instructions').uncheck();await page.locator('#setting-instructions').fill('Only compare the proposed budgets.');await page.locator('#inherit-skills').uncheck();await page.locator('#setting-skills').fill('');await shot('task-editor');
 await page.getByRole('button',{name:'Save settings',exact:true}).click();await page.getByText('Task settings saved for the next run.',{exact:true}).waitFor();assert.equal(await page.locator('#task-settings>summary').evaluate(el=>el===document.activeElement),true);
 assert.equal(get(active).settings.effective.instructions,'Only compare the proposed budgets.');assert.equal(get(active).settings.effective.skills,'');
 await openTask();await page.locator('#setting-instructions').fill('Discard this');await page.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(get(active).settings.effective.instructions,'Only compare the proposed budgets.');
 await openTask();await page.route('**/api/action',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'Synthetic save failure'})}));await page.getByRole('button',{name:'Save settings',exact:true}).click();await page.locator('#settings-error').waitFor({state:'visible'});assert.equal(await page.locator('#settings-dialog').isVisible(),true);await shot('save-failure');await page.unroute('**/api/action');
 let release;const gate=new Promise(resolve=>release=resolve);await page.route('**/api/action',async route=>{await gate;await route.continue();});await page.getByRole('button',{name:'Save settings',exact:true}).click();assert.equal(await page.locator('#settings-cancel').isDisabled(),true);await page.keyboard.press('Escape');assert.equal(await page.locator('#settings-dialog').isVisible(),true);release();await page.locator('#settings-dialog').waitFor({state:'hidden'});await page.unroute('**/api/action');
 await page.reload();await page.getByText('Up to date.',{exact:true}).waitFor();await openTask();assert.equal(await page.locator('#setting-instructions').inputValue(),'Only compare the proposed budgets.');
 await page.locator('#inherit-instructions').check();await page.getByRole('button',{name:'Save settings',exact:true}).click();await page.locator('#settings-dialog').waitFor({state:'hidden'});assert.equal(get(active).settings.effective.instructions,'Read notes and check results.');
 // Settings must not rewrite historical submissions.
 const previous=get(build).submission;await action({action:'task-settings',task_id:build,version:get(build).settings.version,settings:{instructions:'Future only'}});assert.deepEqual(get(build).submission,previous);
 // A changed upstream source brings the whole completed cycle back to active.
 fs.writeFileSync(path.join(project,'b.md'),'Changed fixture');await refresh();assert.equal(await page.locator('#board .card').count(),4);assert.equal(await page.locator('#completed-cycles').isVisible(),false);
 fs.writeFileSync(path.join(project,'b.md'),'Synthetic Build');await refresh();assert.equal(await page.locator('#board .card').count(),1);
 // UI source navigation fixture: restored historical receipts are covered by native Python tests.
 const data=status();data.tasks.find(t=>t.id===learn).completion={completed_on:'2026-09-21',summary:'Synthetic archived Learn',source_build:{task_id:build}};
 await page.route('**/api/snapshot',route=>route.fulfill({json:data}));await refresh();if(!await page.locator('#completed-cycles').evaluate(e=>e.open))await page.locator('#completed-summary').click();await page.locator('[data-cycle="1"]>summary').click();await page.locator(`[data-task-id="${learn}"]`).click();await page.getByRole('button',{name:'Open source Build',exact:true}).click();assert.equal(await page.locator(`[data-task-id="${build}"]`).getAttribute('aria-pressed'),'true');await page.unroute('**/api/snapshot');
 await page.setViewportSize({width:390,height:844});await page.locator('#completed-summary').click();
 await page.getByRole('button',{name:'← Board',exact:true}).click();assert.equal(await page.locator('#completed-cycles').evaluate(el=>el.open),true);assert.equal(await page.locator(`[data-task-id="${build}"]`).evaluate(el=>el===document.activeElement),true);
 await page.getByRole('button',{name:'Back to active work'}).click();await page.setViewportSize({width:390,height:844});await openTask();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:path.join(shots,'research-dbtl-settings-narrow.png')});await page.keyboard.press('Escape');assert.equal(await page.locator('#settings-dialog').isVisible(),false);
 assert.deepEqual(errors,[]);console.log('PASS: live folding, mixed/stale cycles, source navigation, settings persistence/inheritance/blank override, save/cancel/failure/busy, keyboard focus, narrow layout, preserved historical evidence.');
 }finally{if(browser)await browser.close();if(server)server.kill('SIGTERM');fs.rmSync(base,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
