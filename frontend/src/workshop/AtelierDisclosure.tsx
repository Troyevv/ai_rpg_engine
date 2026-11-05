import {useId,useState,type ReactNode} from 'react';
import '../styles/atelier-disclosure.css';
import {ChevronDown} from 'lucide-react';

/** A disclosure with an interruptible, intrinsic-height transition and no hidden tab stops. */
export function AtelierDisclosure({title,children,className='',initialOpen=false}:{title:ReactNode;children:ReactNode;className?:string;initialOpen?:boolean}) {
 const [open,setOpen]=useState(initialOpen);const id=useId();
 return <div className={'atelier-disclosure '+className} data-open={open}>
  <button type="button" className="atelier-disclosure-trigger" aria-expanded={open} aria-controls={id} onClick={()=>setOpen(v=>!v)}>{title}<ChevronDown size={15}/></button>
  <div className="atelier-disclosure-body" id={id} aria-hidden={!open} inert={!open}><div>{children}</div></div>
 </div>;
}
