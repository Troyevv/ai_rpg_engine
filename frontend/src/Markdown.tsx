import { memo, useEffect, useState } from "react";
import { api } from "./api";
export const Markdown = memo(function Markdown({
  text,
  saveId,
  worldId,
  onCharacter,
  links = true,
  streaming = false,
}: {
  text: string;
  streaming?: boolean;
  saveId?: number;
  worldId?: number;
  onCharacter?: (id: string) => void;
  links?: boolean;
}) {
  const [html, setHtml] = useState<{text:string;html:string}|null>(null);
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
        .catch(() => {});
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
      {!streaming && html?.text===text ? (
        <div dangerouslySetInnerHTML={{ __html: html.html }} />
      ) : (
        <div>{text.split(/\n\n+/).map((paragraph,i)=><p className="plain-markdown" key={i}>{paragraph}</p>)}</div>
      )}
    </div>
  );
});
