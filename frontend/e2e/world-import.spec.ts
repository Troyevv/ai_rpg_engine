import {test,expect} from '@playwright/test';
import {detectWorldImport} from '../src/worldImport';

for (const [name,text,fileFormat,format,error] of [
 ['json file','{"characters":[],"world":{"version":2}}','json','json',false],
 ['pasted state',' \n{"characters":[],"world":{"version":2}}\n ',undefined,'json',false],
 ['pasted wrapper','{"state":{"characters":[],"world":{"version":2}}}',undefined,'json',false],
 ['broken JSON','{"campaign":',undefined,'json',true],
 ['braces without JSON','{not JSON}',undefined,'json',true],
 ['Markdown','# Мир\nОбычная выжимка.',undefined,'text',false],
 ['plain text','Герой находится на кухне.',undefined,'text',false],
 ['md file is explicit text','{"hello":"world"}','text','text',false],
 ['txt file is explicit text','{"campaign":','text','text',false],
 ['array is not auto JSON','[]',undefined,'text',false],
 ['empty text','   ',undefined,'text',false],
 ['json file with non-object','[]','json','json',true],
] as const) {
 test(`world import regression: ${name}`,()=>{
  const detected=detectWorldImport(text,fileFormat);
  expect(detected.format).toBe(format);
  expect(!!detected.error).toBe(error);
 });
}

test('editing selected text clears the file override and detects JSON',()=>{
 const json='{"state":{"characters":[],"world":{"version":2}}}';
 expect(detectWorldImport(json,'text').format).toBe('text');
 expect(detectWorldImport(json).format).toBe('json');
 expect(detectWorldImport('{broken}').error).toContain('ошибка синтаксиса');
 expect(detectWorldImport(json).error).toBeNull();
 expect(detectWorldImport('# Мир').format).toBe('text');
});
