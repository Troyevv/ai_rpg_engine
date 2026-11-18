import { memo, useEffect, useMemo, useRef, useState } from "react";
import MarkdownIt from "markdown-it";
import { api } from "./api";
import {createChatParser,renderChatActions} from './chatMarkdown';
const sourceParser = new MarkdownIt("commonmark");
// Chat renders ordinary Markdown during streaming, with the same safe CommonMark
// options as /markdown. No game-format parsing or per-chunk HTTP requests.
const liveParser = createChatParser();

// Presentation only: canonical binding is exclusively performed by Runtime.
// CommonMark knows which fences are letters, including an unfinished stream.
function streamingProse(text: string) {
  const lines = text.split("\n");
  const parts: React.ReactNode[] = [];
  const plain = (value: string, key: string) => value.split(/\n\n+/).map((p, i) =>
    <p className="plain-markdown" key={`${key}-${i}`}>{p}</p>);
  let end = 0;
  for (const token of sourceParser.parse(text, {})) {
    if (token.type !== "fence" || token.level !== 0 || token.info.trim() !== "letter" || !token.map) continue;
    const [start, next] = token.map;
    parts.push(...plain(lines.slice(end, start).join("\n"), `before-${start}`));
    parts.push(<blockquote className="narrative-letter" style={{whiteSpace: "pre-wrap"}} key={`letter-${start}`}>{token.content}</blockquote>);
    end = next;
  }
  parts.push(...plain(lines.slice(end).join("\n"), "after"));
  return parts;
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
      ) : (
        <div>{streamingProse(text)}</div>
      )}
    </div>
  );
});
