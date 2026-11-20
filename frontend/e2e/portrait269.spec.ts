import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { nav } from './navigation';
import { authorView, workshopNav } from './workshop-navigation';
import { chooseOption } from './choice-navigation';

test('classic portrait edits keep the revision, local controls and saved features', async ({ page, request }, info) => {
  const mobile = info.project.name === 'mobile';
  await page.setViewportSize({width: mobile ? 360 : 1280, height: mobile ? 720 : 850});
  const state = JSON.parse(readFileSync(new URL('../../tests/fixtures/initial_world/runtime_presentation.json', import.meta.url),'utf8'));
  const first = state.characters[0];
  first.portrait_traits = {form:'human', face:'long', body_build:'slender', eye_shape:'open', hair:'parted'};
  const workspace = await (await request.post('/api/workspaces', {data:{name:'Классические портреты'}})).json();
  const url = '/api/workspaces/'+workspace.id+'/draft';
  const imported = await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}});
  expect(imported.ok(), await imported.text()).toBeTruthy();
  await page.addInitScript(({id,theme})=>{
    localStorage.setItem('draftWorkspace',id);
    localStorage.setItem('workshop-theme',JSON.stringify({theme_id:theme,mode:'manual'}));
  },{id:workspace.id,theme:mobile?'parchment':'graphite'});
  await page.goto('/');
  await nav(page,'Создать');
  await authorView(page);
  await workshopNav(page,'Персонажи');
  const button = (name:string)=>page.getByRole('button',{name,exact:true});
  await button('Досье '+first.name).click();
  const stored = async () => (await (await request.get(url+'/characters/'+first.id+'/portraits?author=true')).json()).descriptor;
  const before=await stored();
  expect(before).toMatchObject({version:3,face_revision:4,eye_revision:2,body_build:'slender',eye_shape:'open'});
  let generations=0;
  page.on('request', r=>{if (/portrait-proposals.*\/generate$/.test(r.url())) generations++});
  await button('Редактировать портрет').click();
  await button('Настроить иллюстрацию').click();
  await page.getByRole('searchbox',{name:'Поиск · Волосы'}).fill('кроп');
  await expect(page.locator('.studio-gallery button')).toHaveCount(1);
  await button('Французский кроп').click();
  await button('Одежда').click();
  await button('Будущее').click();
  await expect(page.locator('.studio-gallery button')).toHaveCount(2);
  await button('Модульный технокостюм').click();
  await button('Цвета').click();
  await button('Цвет отделки').click();
  await button('Бронзовый').click();
  await button('Лицо').click();
  await button('Ромбовидное').click();
  await chooseOption(page.getByRole('combobox',{name:'Форма носа'}),'aquiline');
  await button('Образ').click();
  await chooseOption(page.getByRole('combobox',{name:'Телосложение',exact:true}),'stocky');
  await chooseOption(page.getByRole('combobox',{name:'Очки',exact:true}),'round_wire');
  if(mobile) await page.setViewportSize({width:393,height:500});
  const save=button('Сохранить иллюстрацию');
  const bounds=await save.boundingBox();
  expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  await expect(page.locator('.studio-open')).toBeVisible();
  expect(await page.locator('.studio-open').evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBeTruthy();
  await page.screenshot({path:info.outputPath('classic-editor.jpg'),scale:'css'});
  await save.click();
  await expect(page.locator('.portrait-dialog')).toHaveCount(0);
  expect(await stored()).toEqual({...before,visage:'diamond',hairstyle:'french_crop',garment:'tech_shell',accent_color:19,eyewear:'round_wire',body_build:'stocky',nose_shape:'aquiline'});
  await button('Редактировать портрет').click();
  await button('Настроить иллюстрацию').click();
  await button('Образ').click();
  await expect(page.getByRole('combobox',{name:'Телосложение',exact:true})).toHaveText(/Коренастое/);
  expect(generations).toBe(0);
});

test('previewing the corrected eyes keeps the saved cast until explicit confirmation', async ({page,request}, info) => {
  const mobile = info.project.name === 'mobile';
  await page.setViewportSize({width:mobile?393:1280,height:850});
  const fixture = new URL('../../tests/fixtures/initial_world/runtime_presentation.json', import.meta.url);
  const state = JSON.parse(readFileSync(process.env.PORTRAIT_REVIEW_DRAFT || fixture,'utf8'));
  if (!process.env.PORTRAIT_REVIEW_DRAFT) {
    for (const [i, card] of state.characters.entries()) {
      state.world.characters[card.id].procedural_portrait = {
        version:3, seed:i.toString(16).padStart(32,'0'), stage:'adult', form:'human', face_revision:i%2?3:4,
        face:0,hair:1,skin:1,eyes:3,clothing:0,accessory:0,palette:1,
        visage:'oval',hairstyle:'parted',garment:'shirt',body_frame:'neutral',facial_hair:'clean_shaven',
      };
      state.world.characters[card.id].portrait_mode='procedural';
    }
  }
  const workspace=await(await request.post('/api/workspaces',{data:{name:'Сравнение глаз'}})).json();
  const url='/api/workspaces/'+workspace.id+'/draft';
  const imp=await request.post(url+'/import',{data:{revision:0,format:'json',text:JSON.stringify(state)}});
  expect(imp.ok()).toBe(true);
  const saved=async()=>await(await request.get(url+'?author=true')).json();
  const before=await saved();
  const included=state.characters.filter((c:{id:string})=>before.portraits[c.id]?.can_update_eyes);
  expect(included.length).toBeGreaterThan(0);
  await page.addInitScript(id=>localStorage.setItem('draftWorkspace',id),workspace.id);
  await page.goto('/'); await nav(page,'Создать'); await authorView(page); await workshopNav(page,'Персонажи');
  const button=(name:string)=>page.getByRole('button',{name,exact:true});
  const grid=page.locator('.ww-characters-grid');
  const pictures=async()=>grid.locator('.ww-card-art img').evaluateAll(els=>els.map(img=>(img as HTMLImageElement).src));
  const capture=async(name:string)=>{
    const imgs=grid.locator('.ww-card-art img');
    await imgs.evaluateAll(els=>Promise.all(els.map(el=>{const img=el as HTMLImageElement;img.loading='eager';return img.decode()})));
    for (const width of mobile?[360,393]:[1280]) {
      await page.setViewportSize({width,height:850});
      await grid.screenshot({path:info.outputPath(name+'-'+width+'.jpg'),scale:'css',animations:'disabled'});
      const bounds = await grid.evaluate(container=>{
        const origin=container.getBoundingClientRect();
        return [...container.querySelectorAll('.ww-card-art')].map(node=>{
          const rect=node.getBoundingClientRect();
          return {x:rect.x-origin.x,y:rect.y-origin.y,width:rect.width,height:rect.height,
                  card:node.parentElement!.getAttribute('aria-label')};
        });
      });
      writeFileSync(info.outputPath(name+'-'+width+'.json'),JSON.stringify(bounds));
      if (process.env.PORTRAIT_REVIEW_DRAFT && mobile) {
        for (const [i,plate] of (await grid.locator('.ww-card-art').all()).entries()) {
          await plate.evaluate(el=>el.scrollIntoView({block:'center',behavior:'instant'}));
          await expect(plate).toBeInViewport();
          await plate.screenshot({path:info.outputPath(`${name}-${width}-plate-${i}.png`),scale:'css',animations:'disabled'});
        }
      }
    }
  };
  const initial=await pictures();
  await capture('before');
  await button('Примерить новую посадку глаз').click();
  await capture('preview');
  const pupilsInside = await grid.locator('.ww-card-art img').evaluateAll(images=>images.every(img=>{
    const src = (img as HTMLImageElement).src;
    if (!src.startsWith('data:image/svg+xml')) return true;
    const svg = new DOMParser().parseFromString(decodeURIComponent(src.slice(src.indexOf(',')+1)),'image/svg+xml');
    const node=document.importNode(svg.documentElement,true) as unknown as SVGSVGElement;
    node.style.cssText='position:fixed;left:-10000px;top:0';document.body.append(node);
    const pupils=[...node.querySelectorAll('ellipse[fill="#292725"]')];
    try { return pupils.length===2 && pupils.every(pupil=>{
      const clip=pupil.parentElement!.getAttribute('clip-path')!;
      const aperture=node.querySelector(clip.slice(4,-1)+' path') as SVGPathElement;
      return aperture.isPointInFill(new DOMPoint(Number(pupil.getAttribute('cx')),Number(pupil.getAttribute('cy'))));
    }); } finally {node.remove()}
  }));
  expect(pupilsInside).toBe(true);
  expect(await pictures()).not.toEqual(initial);
  expect((await saved()).revision).toBe(before.revision);
  await button('Отменить примерку').click();
  expect(await pictures()).toEqual(initial);
  await button('Примерить новую посадку глаз').click();
  await button('Сохранить посадку глаз · '+included.length).click();
  await expect(button('Примерить новую посадку глаз')).toHaveCount(0);
  const after=await saved();
  for(const card of included) {
    expect(after.portraits[card.id].procedural_portrait).toEqual({...before.portraits[card.id].procedural_portrait,eye_revision:2});
  }

  const card=included[0], approved=after.portraits[card.id].procedural_portrait;
  await button('Досье '+card.name).click();
  await button('Редактировать портрет').click();
  const previewNose=async()=>{
    await button('Настроить иллюстрацию').click();
    await button('Лицо').click();
    await button('Примерить новую форму носа').click();
  };
  await previewNose();
  await button('Отмена').click();
  expect((await saved()).portraits[card.id].procedural_portrait).toEqual(approved);
  await previewNose();
  await button('Сохранить иллюстрацию').click();
  await expect(page.locator('.portrait-dialog')).toHaveCount(0);
  // Manual save also materializes the three existing v3 model defaults on sparse imports.
  expect((await saved()).portraits[card.id].procedural_portrait).toEqual({
    base_version:2, skin_swatch:false, eye_swatch:false, ...approved, nose_revision:2,
  });
});
