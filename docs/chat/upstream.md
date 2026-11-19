# Chat UI provenance

Reviewed upstream: https://github.com/deepseek-ai/chat-demo at
`5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c` (MIT, Copyright 2026 DeepSeek).
README, LICENSE, package.json, MessageList.tsx and BranchSwitcher.tsx were inspected.

`frontend/src/useChatScroll.ts` adapts the sticky-scroll / ResizeObserver interaction
from `src/components/messages/MessageList.tsx`. The required notice is preserved in
[the upstream license](../licenses/deepseek-chat-demo-MIT.txt).
Layout/composer/edit/branch interactions use the engine's React 19, Vite, Radix
Dialog, Buttons, Textarea and safe Markdown component. The engine already has
these dependencies; no demo dependencies were copied or added. Upstream uses
React 18/Rspack/Zustand/IndexedDB; none of that storage/transport architecture is
imported. No branding, browser keys, tools, speech, uploads or direct provider HTTP.
