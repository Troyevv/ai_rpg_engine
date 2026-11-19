import { Children, Fragment, isValidElement, type ReactNode } from "react";
import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

type ChoiceProps = {
  value: string | number;
  onValueChange: (value: string) => void;
  children: ReactNode;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
  "aria-required"?: boolean | "true" | "false";
};

// Prefixing also gives the meaningful empty-value option an identity in Radix.
const optionId = (value: string | number) => "v:" + value;
function items(children: ReactNode): ReactNode {
  return Children.map(children, child => {
    if (!isValidElement<{children?: ReactNode; value?: string | number; disabled?: boolean; label?: string}>(child)) return null;
    const p = child.props;
    if (child.type === Fragment) return items(p.children);
    if (child.type === "optgroup") return <Select.Group><Select.Label>{p.label}</Select.Label>{items(p.children)}</Select.Group>;
    const label = Children.toArray(p.children).join("");
    return <Select.Item className="choice-item" value={optionId(p.value ?? label)} disabled={p.disabled} textValue={label}>
      <Select.ItemText>{p.children}</Select.ItemText><Select.ItemIndicator><Check size={16}/></Select.ItemIndicator>
    </Select.Item>;
  });
}

// Radix dialogs listen on document capture. Let the browser first dismiss its
// top-layer picker and restore the select's focus on the first Escape.
export function dismissOpenChoice(event: KeyboardEvent) {
  if (event.key === "Escape" && CSS.supports("selector(select:open)") && document.querySelector("select[data-choice]:open")) {
    event.stopImmediatePropagation();
  }
}

export function Choice({value, children, onValueChange, disabled, required, ...props}: ChoiceProps) {
  // Customizable select is rendered in the DOM top layer, including on Android.
  // Keep OS pickers out of single-choice fields on browsers with older engines.
  if (typeof CSS !== "undefined" && CSS.supports("appearance", "base-select")) {
    return <select {...props} data-choice="" disabled={disabled} required={required} value={value}
      onChange={event => onValueChange(event.target.value)}>{children}</select>;
  }
  const emptyRequired = required && value === "";
  const placeholder = emptyRequired && Children.toArray(children).find(child =>
    isValidElement<{value?: string}>(child) && child.props.value === "");
  return <Select.Root value={emptyRequired ? "" : optionId(value)} onValueChange={v => onValueChange(v.slice(2))} disabled={disabled} required={required}>
    <Select.Trigger {...props} data-choice="" className={`choice-trigger ${props.className || ""}`}>
      <Select.Value placeholder={isValidElement<{children?: ReactNode}>(placeholder) ? placeholder.props.children : undefined}/><Select.Icon><ChevronDown size={16}/></Select.Icon>
    </Select.Trigger>
    <Select.Portal><Select.Content position="popper" sideOffset={4} collisionPadding={8} className="choice-popup">
      <Select.Viewport>{items(children)}</Select.Viewport>
    </Select.Content></Select.Portal>
  </Select.Root>;
}
