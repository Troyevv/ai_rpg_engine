// Adapted from deepseek-ai/chat-demo MessageList.tsx (MIT), commit
// 5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c. See docs/chat/upstream.md.
import {useLayoutEffect, useRef, useState} from 'react';

export function useChatScroll(identity:string) {
  const viewport=useRef<HTMLDivElement>(null);
  const content=useRef<HTMLDivElement>(null);
  const sticky=useRef(true);
  const previous=useRef(0);
  const [following,setFollowing]=useState(true);
  const toLatest=()=>{sticky.current=true;setFollowing(true);const el=viewport.current;if(el){el.scrollTop=el.scrollHeight;previous.current=el.scrollTop}};
  useLayoutEffect(()=>{
    sticky.current=true;setFollowing(true);
    const el=viewport.current;if(el){el.scrollTop=el.scrollHeight;previous.current=el.scrollTop}
  },[identity]);
  useLayoutEffect(()=>{
    const el=viewport.current, column=content.current;if(!el||!column)return;
    const follow=()=>{if(sticky.current){el.scrollTop=el.scrollHeight;previous.current=el.scrollTop}};
    const scroll=()=>{
      if(el.scrollHeight-el.scrollTop-el.clientHeight<40)sticky.current=true;
      else if(el.scrollTop<previous.current)sticky.current=false;
      setFollowing(sticky.current);
      previous.current=el.scrollTop;
    };
    const observer=new ResizeObserver(follow);observer.observe(el);observer.observe(column);
    el.addEventListener('scroll',scroll,{passive:true});follow();
    return()=>{observer.disconnect();el.removeEventListener('scroll',scroll)};
  },[identity]);
  return {viewport,content,sticky,following,toLatest};
}
