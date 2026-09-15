import { useEffect, useState } from "react";
import { api } from "./api";
export function Markdown({
  text,
  saveId,
  worldId,
  onCharacter,
  links = true,
}: {
  text: string;
  saveId?: number;
  worldId?: number;
  onCharacter?: (id: string) => void;
  links?: boolean;
}) {
  const [html, setHtml] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api<{ html: string }>(
        "/markdown",
        { text, save_id: saveId, world_id: worldId, link_names: links },
        "POST",
        controller.signal,
      )
        .then((value) => setHtml(value.html))
        .catch(() => {});
    }, 80);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, saveId, worldId, links]);
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
      {html ? (
        <div dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <div className="plain-markdown">{text}</div>
      )}
    </div>
  );
}
