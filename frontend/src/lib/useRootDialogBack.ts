import { dismissTransient } from './transientBack';
import { useEffect } from 'react';

const topDialog = () =>
  Array.from(
    document.querySelectorAll<HTMLElement>('[role="dialog"][data-state="open"]')
  ).at(-1);

/** The Narrative root has no route entry of its own. Give its standalone
 * dialogs one Back entry, exactly like the Inspector. Nested portals share it. */
export function useRootDialogBack() {
  useEffect(() => {
    let owned = false,
      consuming = false;
    const sync = () => {
      if (consuming) return;
      const state = history.state || {};
      // A library-to-workshop transition promotes this same entry to a route.
      if (state.worldWorkshop) { owned = false; return; }
      const layer = topDialog() || document.querySelector<HTMLElement>('.choice-popup');
      const routed =
        state.inspectorOpen ||
        state.saveWorkspace ||
        state.mobileMenu ||
        state.phoneUI ||
        state.phoneCall ||
        state.chatMode ||
        state.choiceDraft ||
        state.worldWorkshop;
      if (
        layer &&
        !routed &&
        !state.rootDialog &&
        !layer.matches('.mobile-game-menu,.chat-dialog') &&
        !document.querySelector('.ww-shell,.chat-mode')
      ) {
        history.pushState({ ...state, rootDialog: true }, '');
        owned = true;
      } else if (!layer && owned && state.rootDialog && !routed) {
        consuming = true;
        history.back();
      }
    };
    const back = (e: PopStateEvent) => {
      if (!owned || history.state?.rootDialog) return;
      e.stopImmediatePropagation();
      owned = false;
      if (consuming) {
        consuming = false;
        sync();
        return;
      }
      const top = topDialog();
      if (!dismissTransient())
        top
          ?.querySelector<HTMLButtonElement>(':scope > .dialog-close')
          ?.click();
      // A refused close (busy or dirty editor) still owns Back.
      requestAnimationFrame(sync);
    };
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true });
    const root = document.getElementById('root');
    if (root) observer.observe(root, {childList:true});
    owned = !!history.state?.rootDialog;
    sync();
    window.addEventListener('control-layer-change', sync);
    window.addEventListener('popstate', back, true);
    return () => {
      observer.disconnect();
      window.removeEventListener('control-layer-change', sync);
      window.removeEventListener('popstate', back, true);
    };
  }, []);
}
