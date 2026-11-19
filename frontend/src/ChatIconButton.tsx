import {useId} from 'react';
import {Button, type ButtonProps} from './components/ui/button';

/** Small artwork, full touch target. Tooltip also appears on keyboard focus. */
export function ChatIconButton({label,children,className='',...props}:ButtonProps&{label:string}) {
  const id=useId();
  return <span className="chat-icon-control"><Button {...props} size="icon" variant="ghost" className={`chat-icon-button ${className}`} aria-label={label} aria-describedby={id}>{children}</Button><span id={id} role="tooltip" className="chat-tooltip">{label}</span></span>;
}
