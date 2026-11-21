import {useTransientBack} from '../../lib/transientBack';
import { Children, Fragment, isValidElement, useState, useCallback, type ReactNode } from "react";
import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

type ChoiceProps = {
  value: string | number;
  onValueChange: (value: string) => void;
  children: ReactNode;
  disabled?: boolean;
  required?: boolean;
  optionPreview?: (value: string) => ReactNode;
  id?: string;
  className?: string;
  "aria-label"?: string;
  "aria-required"?: boolean | "true" | "false";
};

// Prefixing also gives the meaningful empty-value option an identity in Radix.
const optionId = (value: string | number) => "v:" + value;
function items(children: ReactNode, preview?: ChoiceProps['optionPreview']): ReactNode {
  return Children.map(children, child => {
    if (!isValidElement<{children?: ReactNode; value?: string | number; disabled?: boolean; label?: string}>(child)) return null;
    const p = child.props;
    if (child.type === Fragment) return items(p.children,preview);
    if (child.type === "optgroup") return <Select.Group><Select.Label>{p.label}</Select.Label>{items(p.children,preview)}</Select.Group>;
    const label = Children.toArray(p.children).join("");
    return <Select.Item className="choice-item" data-value={p.value ?? label} value={optionId(p.value ?? label)} disabled={p.disabled} textValue={label}>
      {preview?.(String(p.value ?? label))}<Select.ItemText>{p.children}</Select.ItemText><Select.ItemIndicator><Check size={16}/></Select.ItemIndicator>
    </Select.Item>;
  });
}

export function Choice({value, children, onValueChange, disabled, required, optionPreview, ...props}: ChoiceProps) {
  const [open,setOpen]=useState(false);
  useTransientBack(open,useCallback(()=>setOpen(false),[]));
  const emptyRequired = required && value === "";
  const placeholder = emptyRequired && Children.toArray(children).find(child =>
    isValidElement<{value?: string}>(child) && child.props.value === "");
  return <Select.Root open={open} onOpenChange={setOpen} value={emptyRequired ? "" : optionId(value)} onValueChange={v => onValueChange(v.slice(2))} disabled={disabled} required={required}>
    <Select.Trigger {...props} data-choice="" value={value} className={`choice-trigger ${props.className || ""}`}>
      <Select.Value placeholder={isValidElement<{children?: ReactNode}>(placeholder) ? placeholder.props.children : undefined}/><Select.Icon><ChevronDown size={16}/></Select.Icon>
    </Select.Trigger>
    <Select.Portal container={document.getElementById("root")}><Select.Content position="popper" sideOffset={4} collisionPadding={8} className="choice-popup">
      <Select.Viewport>{items(children,open ? optionPreview : undefined)}</Select.Viewport>
    </Select.Content></Select.Portal>
  </Select.Root>;
}
