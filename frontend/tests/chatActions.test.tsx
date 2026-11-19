import {describe,it,expect,vi,afterEach} from 'vitest';
import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {renderChatActions} from '../src/chatMarkdown';
import {Markdown} from '../src/Markdown';

const choices='### Варианты действий\n\n1. **Спросить Лену:** «Кто там?»\n2. **Осмотреть дверь:** проверить замок.\n3. **Позвать гостя:** «Кто там?»\n4. **Подождать:** остаться у стола.\n\n**Свободный ввод:** свой вариант.\n\n---\n\n### Текущая сцена\n\n**Место:** маяк.';
afterEach(()=>{vi.restoreAllMocks();document.body.innerHTML=''});
describe('Chat actions: bounded Markdown nodes only',()=>{
  it('keeps numbering, bold, separators and original text while exposing plain draft values',()=>{
    const value=renderChatActions(choices,true);const host=document.createElement('div');host.innerHTML=value.html;
    expect(host.querySelectorAll('ol > li > button')).toHaveLength(4);expect(host.querySelectorAll('button strong')).toHaveLength(4);
    expect(host.querySelectorAll('hr')).toHaveLength(1);expect(value.actions['0']).toBe('Спросить Лену: «Кто там?»');
    expect(choices).toContain('1. **Спросить Лену:**');
  });
  it.each([
    choices.replace('### Варианты действий','### Список покупок'),
    choices.split('\n').map(line=>'> '+line).join('\n'),
    '```md\n'+choices+'\n```',
    choices.replace('2. **Осмотреть','   - вложенный пункт\n2. **Осмотреть'),
    choices.replace('«Кто там?»','[ссылка](https://example.com)'),
    choices.replace('4. **Подождать:** остаться у стола.\n',''),
  ])('leaves unrelated, quoted, nested and unknown lists as ordinary Markdown',text=>{
    expect(Object.keys(renderChatActions(text,true).actions)).toHaveLength(0);
  });
  it('does not enable partial streaming choices or render raw HTML',()=>{
    expect(Object.keys(renderChatActions(choices,false).actions)).toHaveLength(0);
    const html=renderChatActions('<script>alert(1)</script>\n\n'+choices,true,true).html;
    expect(html).not.toContain('<script>');expect(html.match(/disabled/g)).toHaveLength(4);
  });
  it('selects through a real button without HTTP or submission',async()=>{
    const fetch=vi.spyOn(globalThis,'fetch').mockRejectedValue(new Error('unexpected HTTP'));
    const click=vi.fn(),submit=vi.fn();const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
    await act(async()=>root.render(<form onSubmit={submit}><Markdown text={choices} onAction={click} actionsComplete liveMarkdown/></form>));
    await act(async()=>host.querySelector('button')!.click());
    expect(click).toHaveBeenCalledWith('Спросить Лену: «Кто там?»');expect(submit).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled();
    await act(async()=>root.unmount());
  });
});
