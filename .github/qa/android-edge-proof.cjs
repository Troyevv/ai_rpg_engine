const {chromium, expect, request} = require(process.cwd() + '/node_modules/@playwright/test');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');
(async () => {
  const destination = '/tmp/android-proof';
  fs.mkdirSync(destination, {recursive: true});
  const browser = await chromium.connectOverCDP('http://localhost:9235');
  const context = browser.contexts()[0];
  const page = context.pages()[0] || await context.newPage();
  page.setDefaultTimeout(30000);
  const cdp = await context.newCDPSession(page);
  async function tap(el) {
    await el.scrollIntoViewIfNeeded();
    const b = await el.boundingBox();
    await cdp.send('Input.dispatchTouchEvent', {type: 'touchStart', touchPoints: [{x: b.x+b.width/2, y: b.y+b.height/2}]});
    await cdp.send('Input.dispatchTouchEvent', {type: 'touchEnd', touchPoints: []});
  }
  for (const [version, port] of [['before', 8216], ['after', 8217]]) {
    const baseURL = 'http://127.0.0.1:' + port;
    const api = await request.newContext({baseURL});
    const selection = await (await api.post('/test/phone-seed?incoming=false')).json();
    await api.put('/api/worlds/'+selection.world+'/presentation', {data:{theme_id:'graphite'}});
    await page.goto(baseURL);
    await page.evaluate(s => localStorage.setItem('selection', JSON.stringify(s)), selection);
    await page.reload();
    await page.locator('.choices button').first().waitFor();
    await tap(page.getByRole('button', {name: 'Меню игры', exact: true}));
    const menu = page.locator('.mobile-game-menu');
    await expect(menu).toBeVisible();
    await page.evaluate(async () => {
      await document.fonts.ready;
      const animations = document.getAnimations().filter(a => Number.isFinite(a.effect?.getComputedTiming().endTime));
      await Promise.allSettled(animations.map(a=>a.finished));
    });
    for (const position of ['top', 'bottom']) {
      if (position === 'bottom') {
        const scroll = menu.locator('.mobile-menu-scroll');
        const b = await scroll.boundingBox();
        for (let n=0;n<6;n++) {
          const pts=y=>[{x:b.x+b.width*.5,y:b.y+b.height*y}];
          await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:pts(.85)});
          for (const y of [.74,.61,.48,.35,.22]) await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:pts(y)});
          await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
          if (await scroll.evaluate(el=>el.scrollTop+el.clientHeight>=el.scrollHeight-1)) break;
        }
        await expect.poll(()=>scroll.evaluate(el=>el.scrollTop+el.clientHeight>=el.scrollHeight-1)).toBe(true);
      }
      const info = await menu.evaluate(el=>{
        const r=el.getBoundingClientRect(), s=getComputedStyle(el);
        return {ua:navigator.userAgent,rect:[r.x,r.y,r.width,r.height],viewport:[innerWidth,innerHeight],border:s.borderWidth,bg:s.backgroundColor,inner:getComputedStyle(el.querySelector('.menu-world')).borderWidth};
      });
      console.log(version,position,info);
      expect(info.ua).toContain('Android');
      expect(info.border).toBe(version==='after'?'0px':'1px');
      expect(info.inner).toBe('1px');
      expect(info.rect).toEqual([0,0,...info.viewport]);
      const path=destination+'/'+version+'-'+position;
      fs.writeFileSync(path+'.json',JSON.stringify(info));
      await page.screenshot({path:path+'-web.png'});
      fs.writeFileSync(path+'-device.png',execFileSync('adb',['exec-out','screencap','-p'],{maxBuffer:12*1024*1024}));
    }
    await tap(menu.getByRole('button',{name:'Настройки',exact:true}));
    await expect(page.locator('.settings-dialog')).toBeVisible();
    await api.dispose();
  }
  process.exit(0);
})().catch(e=>{console.error(e);process.exit(1)});
