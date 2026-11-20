import { memo, useEffect, useMemo, useRef, useState } from "react";
import MarkdownIt from "markdown-it";
import { api } from "./api";
import { createChatParser, renderChatActions } from "./chatMarkdown";

const liveParser = createChatParser();
const sourceParser = new MarkdownIt("commonmark", {html:false, breaks:true}).enable("table");
const renderFence = sourceParser.renderer.rules.fence!;
sourceParser.renderer.rules.fence = (tokens, index, options, env, renderer) => {
  const token = tokens[index];
  if (token.level === 0 && token.info.trim() === "letter") {
    return '<blockquote class="narrative-letter" style="white-space:pre-wrap">' +
      sourceParser.utils.escapeHtml(token.content) + '</blockquote>';
  }
  return renderFence(tokens, index, options, env, renderer);
};

// Parse the full source so a late link definition or closing fence can still
// change an earlier block. React retains unchanged blocks and appends ordinary
// prose to the current text node without replacing completed paragraphs.
const FormattedBlock = memo(function FormattedBlock({html}: {html:string}) {
  return <div style={{display:'contents'}} dangerouslySetInnerHTML={{__html:html}} />;
});

function StreamingBlocks({text}: {text:string}) {
  const env = {};
  const tokens = sourceParser.parse(text, env);
  const blocks = [];
  let first = 0;
  for (let end = 0; end < tokens.length; end++) {
    const token = tokens[end];
    if (token.level !== 0 || token.nesting === 1) continue;
    const inline = tokens[first + 1]?.children;
    if (tokens[first].type === 'paragraph_open' && inline?.length === 1 && inline[0].type === 'text') {
      blocks.push(<p key={first}>{inline[0].content}</p>);
    } else {
      const html = sourceParser.renderer.render(tokens.slice(first, end + 1), sourceParser.options, env);
      blocks.push(<FormattedBlock key={first} html={html} />);
    }
    first = end + 1;
  }
  return <div>{blocks}</div>;
}

export const Markdown = memo(function Markdown({
  text,
  saveId,
  worldId,
  onCharacter,
  links = true,
  streaming = false,
  liveMarkdown = false,
  onReady,
  onAction,
  actionsComplete = false,
  actionsDisabled = false,
}: {
  text: string;
  streaming?: boolean;
  liveMarkdown?: boolean;
  onReady?:()=>void;
  onAction?:(text:string)=>void;
  actionsComplete?:boolean;
  actionsDisabled?:boolean;
  saveId?: number;
  worldId?: number;
  onCharacter?: (id: string) => void;
  links?: boolean;
}) {
  const [html, setHtml] = useState<{text:string;html:string|null}|null>(null);
  const liveHtml = useMemo(() => liveMarkdown ? liveParser.render(text) : null, [text, liveMarkdown]);
  const actionHtml=useMemo(()=>onAction?renderChatActions(text,actionsComplete&&!streaming,actionsDisabled):null,[text,!!onAction,actionsComplete,streaming,actionsDisabled]);
  const ready=useRef(onReady);ready.current=onReady;
  useEffect(()=>{if(!streaming&&(actionHtml||html?.text===text))ready.current?.()},[html,text,streaming,actionHtml]);
  useEffect(() => {
    if (streaming||onAction) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api<{ html: string }>(
        "/markdown",
        { text, save_id: saveId, world_id: worldId, link_names: links },
        "POST",
        controller.signal,
      )
        .then((value) => setHtml({text,html:value.html}))
        .catch(() => {if(!controller.signal.aborted)setHtml({text,html:null})});
    }, 80);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, saveId, worldId, links, streaming,!!onAction]);
  return (
    <div
      className="prose"
      onClick={(e) => {
        const action=(e.target as HTMLElement).closest<HTMLButtonElement>('button[data-chat-action]');
        if(action&&e.currentTarget.contains(action)&&!action.disabled&&actionHtml){
          const value=actionHtml.actions[action.dataset.chatAction!];if(value!==undefined)onAction?.(value);return;
        }
        const button = (e.target as HTMLElement).closest<HTMLButtonElement>(
          "[data-character-id]",
        );
        if (button?.dataset.characterId)
          onCharacter?.(button.dataset.characterId);
      }}
    >
      {actionHtml ? <div dangerouslySetInnerHTML={{__html:actionHtml.html}}/> : !streaming && html?.text===text && html.html ? (
        <div dangerouslySetInnerHTML={{ __html: html.html }} />
      ) : liveHtml !== null ? (
        <div dangerouslySetInnerHTML={{ __html: liveHtml }} />
      ) : streaming ? (
        <StreamingBlocks text={text}/>
      ) : (
        <div dangerouslySetInnerHTML={{ __html: sourceParser.render(text) }} />
      )}
    </div>
  );
});
