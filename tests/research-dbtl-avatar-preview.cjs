// Optional browser check for the disposable avatar preview; requires existing Playwright.
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');
const source = process.env.HERMES_SOURCE_DIR || path.join(os.homedir(), '.hermes/hermes-agent');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || path.join(source, 'node_modules/playwright'));
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.DBTL_CHROMIUM_EXECUTABLE || undefined});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:960}});
    const errors = [], requests = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => requests.push(r.url()));
    await page.goto(pathToFileURL(path.resolve(__dirname, '../sketches/research-dbtl-avatars/index.html')).href);
    const shots = process.env.DBTL_SCREENSHOT_DIR || path.join(os.tmpdir(), 'research-dbtl-avatar-preview');
    fs.mkdirSync(shots, {recursive:true});
    const screenshot = name => page.screenshot({path:path.join(shots,`avatars-${name}.png`), fullPage:true});
    const card = who => page.locator(`.card .avatar.${who}`);
    const original = await card('codex').locator('img').getAttribute('src');
    const data = await page.evaluate(() => {
      const c=document.createElement('canvas'); c.width=80; c.height=40;
      const ctx=c.getContext('2d');ctx.fillStyle='#27664f';ctx.fillRect(0,0,80,40);
      ctx.fillStyle='white';ctx.font='24px sans-serif';ctx.fillText('A',30,28);
      return c.toDataURL('image/png');
    });
    const payload = {name:'sample.png',mimeType:'image/png',buffer:Buffer.from(data.split(',')[1],'base64')};
    await page.locator('#agents').focus();await page.keyboard.press('Enter');
    await page.locator('#dialog').waitFor({state:'visible'});
    await screenshot('editor');
    await page.locator('#file').setInputFiles(payload);
    await page.waitForFunction(() => !document.getElementById('save').disabled);
    assert.equal(await card('codex').locator('img').getAttribute('src'), original, 'Draft must not change cards');
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    assert.equal(await card('codex').locator('img').getAttribute('src'), original);
    await page.locator('#agents').click();
    await page.locator('#file').setInputFiles({name:'not-an-image.txt',mimeType:'text/plain',buffer:Buffer.from('invalid')});
    assert.match(await page.locator('#error').innerText(), /PNG, JPG or WebP/);
    await page.locator('#file').setInputFiles({name:'bad.png',mimeType:'image/png',buffer:Buffer.from('broken png')});
    await page.getByText('This image could not be opened. Try another picture.').waitFor();
    await screenshot('failure');
    for (const who of ['codex','claude','hermes']) {
      await page.locator(`[data-agent="${who}"]`).click();
      await page.locator('#file').setInputFiles(payload);
      await page.waitForFunction(() => !document.getElementById('save').disabled);
      assert.equal(await page.locator('#large-avatar img').evaluate(img=>img.naturalWidth),256);
    }
    await page.getByRole('button',{name:'Save avatars'}).click();
    for (const who of ['codex','claude','hermes']) {
      assert.match(await card(who).locator('img').getAttribute('src'), /^data:image\/png/);
    }
    assert.equal(await page.locator('#agents').evaluate(el=>el===document.activeElement),true);
    await screenshot('cards');
    await page.locator('#agents').click();
    await page.getByRole('button',{name:'Remove',exact:false}).click();
    await page.getByRole('button',{name:'Save avatars'}).click();
    assert.equal(await card('codex').innerText(),'Cx');
    assert.equal(await card('codex').locator('img').count(),0);
    await page.setViewportSize({width:375,height:850});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await screenshot('narrow-cards');
    await page.locator('#agents').click();await screenshot('narrow-editor');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#dialog').isVisible(),false);
    await page.reload();assert.equal(await card('codex').locator('img').getAttribute('src'),original);
    assert.deepEqual(errors,[]);
    assert.equal(requests.every(url=>/^(file:|data:|blob:)/.test(url)),true);
    console.log('PASS: all three uploads, card display, draft isolation, cancel, remove/fallback, invalid/corrupt files, square crop, keyboard open/Escape, narrow layout, reload reset, no network.');
    console.log('Screenshots: '+shots);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
