import { memo, useEffect, useRef, useState } from "react";
import { api } from "./api";
export const Markdown = memo(function Markdown({
  text,
  saveId,
  worldId,
  onCharacter,
  links = true,
  streaming = false,
  deferFormatting = false,
  onReady,
}: {
  text: string;
  streaming?: boolean;
  deferFormatting?: boolean;
  onReady?:()=>void;
  saveId?: number;
  worldId?: number;
  onCharacter?: (id: string) => void;
  links?: boolean;
}) {
  const container=useRef<HTMLDivElement>(null);
  const [format,setFormat]=useState(!deferFormatting);
  useEffect(()=>{
    if(format)return;
    const el=container.current;if(!el)return;
    // Exact plain text is always present. Only expensive server formatting
    // waits for the reading viewport; the #72 scroll owner is unchanged.
    if(typeof IntersectionObserver==='undefined'){setFormat(true);return}
    const observer=new IntersectionObserver(entries=>{
      if(entries.some(e=>e.isIntersecting)){setFormat(true);observer.disconnect()}
    },{root:el.closest('.story-scroll,.call-scene-scroll'),rootMargin:'600px'});
    observer.observe(el);return()=>observer.disconnect();
  },[format]);
  const [html, setHtml] = useState<{text:string;html:string|null}|null>(null);
  const ready=useRef(onReady);ready.current=onReady;
  useEffect(()=>{if(!streaming&&html?.text===text)ready.current?.()},[html,text,streaming]);
  useEffect(() => {
    if (streaming || !format) return;
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
  }, [text, saveId, worldId, links, streaming, format]);
  return (
    <div
      ref={container}
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
        <div>{text.split(/\n\n+/).map((paragraph,i)=><p className="plain-markdown" key={i}>{paragraph}</p>)}</div>
      )}
    </div>
  );
});
