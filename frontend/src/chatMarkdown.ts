import MarkdownIt from 'markdown-it';

export function createChatParser() {
  const parser=new MarkdownIt('commonmark',{html:false,breaks:true}).enable('table');
  const fence=parser.renderer.rules.fence!;
  parser.renderer.rules.fence=(tokens,index,options,env,renderer)=>{
    const token=tokens[index];
    if(token.level===0&&token.info.trim()==='letter')return '<blockquote class="narrative-letter" style="white-space:pre-wrap">'+parser.utils.escapeHtml(token.content)+'</blockquote>\n';
    return fence(tokens,index,options,env,renderer);
  };
  return parser;
}

const parser=createChatParser();
const inlineText=(token:ReturnType<typeof parser.parse>[number])=>(token.children||[]).map(t=>t.type==='softbreak'||t.type==='hardbreak'?'\n':t.type==='image'?'':t.content).join('').trim();

/** Only a complete, top-level action section is interactive. Nested lists,
 * quotations, links and unknown formats retain their ordinary Markdown. */
export function renderChatActions(text:string,complete:boolean,disabled=false) {
  const tokens=parser.parse(text,{});const actions:Record<string,string>={};
  if(complete)for(let i=0;i<tokens.length-3;i++){
    const heading=tokens[i];
    if(heading.type!=='heading_open'||heading.level!==0||inlineText(tokens[i+1]).toLocaleLowerCase()!=='варианты действий')continue;
    const start=i+3;if(tokens[start]?.type!=='ordered_list_open'||tokens[start].level!==0)continue;
    let end=start+1;while(end<tokens.length&&!(tokens[end].type==='ordered_list_close'&&tokens[end].level===0))end++;
    if(end===tokens.length)continue;
    const items:{open:number;inline:number;close:number}[]=[];let cursor=start+1;let valid=true;
    while(cursor<end){
      const span=tokens.slice(cursor,cursor+5);
      if(span.length!==5||span.map(t=>t.type).join(',')!=='list_item_open,paragraph_open,inline,paragraph_close,list_item_close'
        ||(span[2].children||[]).some(t=>['link_open','image','html_inline'].includes(t.type))){valid=false;break}
      if(!inlineText(span[2])){valid=false;break}
      items.push({open:cursor+1,inline:cursor+2,close:cursor+3});cursor+=5;
    }
    if(!valid||items.length<4||items.length>6)continue;
    for(const item of items){
      const id=String(Object.keys(actions).length);actions[id]=inlineText(tokens[item.inline]);
      const open=tokens[item.open];open.type='chat_action_open';open.tag='button';open.hidden=false;
      open.attrs=[['type','button'],['class','chat-action'],['data-chat-action',id],['aria-label','Выбрать вариант: '+actions[id]]];
      if(disabled)open.attrSet('disabled','');
      const close=tokens[item.close];close.type='chat_action_close';close.tag='button';close.hidden=false;
    }
    i=end;
  }
  return {html:parser.renderer.render(tokens,parser.options,{}),actions};
}
