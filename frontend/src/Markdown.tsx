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
      ) : (
        <div dangerouslySetInnerHTML={{ __html: sourceParser.render(text) }} />
      )}
    </div>
  );
});
