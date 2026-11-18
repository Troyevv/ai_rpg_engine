import { memo, useEffect, useRef, useState } from "react";
import MarkdownIt from "markdown-it";
import { api } from "./api";
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
  onReady,
}: {
  text: string;
  streaming?: boolean;
  onReady?:()=>void;
  saveId?: number;
  worldId?: number;
  onCharacter?: (id: string) => void;
  links?: boolean;
}) {
  const [html, setHtml] = useState<{text:string;html:string|null}|null>(null);
  const ready=useRef(onReady);ready.current=onReady;
  useEffect(()=>{if(!streaming&&html?.text===text)ready.current?.()},[html,text,streaming]);
  useEffect(() => {
    if (streaming) return;
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
  }, [text, saveId, worldId, links, streaming]);
  return (
    <div
      className="prose"
      onClick={(e) => {
        const button = (e.target as HTMLElement).closest<HTMLButtonElement>(
          "[data-character-id]",
        );
        if (button?.dataset.characterId)
          onCharacter?.(button.dataset.characterId);
      }}
    >
      {!streaming && html?.text===text && html.html ? (
        <div dangerouslySetInnerHTML={{ __html: html.html }} />
      ) : (
        <div dangerouslySetInnerHTML={{ __html: sourceParser.render(text) }} />
      )}
    </div>
  );
});
