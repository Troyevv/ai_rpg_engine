import { memo, useEffect, useRef, useState } from "react";
import MarkdownIt from "markdown-it";
import { api } from "./api";
const sourceParser = new MarkdownIt("commonmark");

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
        <div>{streamingProse(text)}</div>
      )}
    </div>
  );
});
