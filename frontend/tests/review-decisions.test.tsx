import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it} from 'vitest';
import {ReviewDecisions} from '../src/workshop/ReviewDecisions';
it('distinguishes explicit outcomes and never links old indexed addresses into a changed world',()=>{
 const html=renderToStaticMarkup(<ReviewDecisions items={[{issue_id:'a',signature:'s',message:'Старое замечание',resolution:'disproved',reason:'Проверено основание',paths:['/characters/0'],applies_to_current:false},{issue_id:'b',signature:'s',message:'Другое замечание',resolution:'replaced',reason:'Уточнён адрес',paths:['/campaign/title'],applies_to_current:true}]} links={paths=><a href="#">{paths.join(',')}</a>}/>);
 expect(html).toContain('Опровергнуто проверкой');
 expect(html).toContain('Переформулировано проверкой');
 expect(html).not.toContain('/characters/0');
 expect(html).toContain('/campaign/title');
 expect(html).not.toContain('Исправлено');
});
