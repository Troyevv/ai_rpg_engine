import {
  Children,
  Fragment,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import "./choice.css";

export type Choice = {
  value: string;
  label: ReactNode;
  description?: string;
  category?: string;
  disabled?: boolean;
  reason?: string;
};
type Change = { target: { value: string } };
type Props = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "value" | "onChange" | "children"
> & {
  value?: string | number;
  children?: ReactNode;
  options?: Choice[];
  onChange?: (event: Change) => void;
  onValueChange?: (value: string) => void;
  searchable?: boolean;
  allowCustom?: boolean;
  placeholder?: string;
};
/** Declarative option data only. Never mounts an OS choice element. */
export function ChoiceOption(_props: {
  value?: string | number;
  children?: ReactNode;
  disabled?: boolean;
  reason?: string;
  category?: string;
}) {
  return null;
}
function text(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) =>
      isValidElement<{ children?: ReactNode }>(child)
        ? text(child.props.children)
        : String(child ?? ""),
    )
    .join("");
}
function choices(children: ReactNode): Choice[] {
  return Children.toArray(children).flatMap((child) => {
    if (
      !isValidElement<{
        value?: string | number;
        children?: ReactNode;
        disabled?: boolean;
        reason?: string;
        category?: string;
      }>(child)
    )
      return [];
    if (child.type === Fragment) return choices(child.props.children);
    return [
      {
        value: String(child.props.value ?? text(child.props.children)),
        label: child.props.children,
        disabled: child.props.disabled,
        reason: child.props.reason,
        category: child.props.category,
      },
    ];
  });
}
export function ChoiceControl({
  value: controlledValue,
  defaultValue,
  children,
  options,
  onChange,
  onValueChange,
  searchable,
  allowCustom,
  placeholder = "Выбрать",
  className = "",
  ...props
}: Props) {
  const [uncontrolledValue, setUncontrolledValue] = useState(
    String(defaultValue ?? ""),
  );
  const value = controlledValue ?? uncontrolledValue;
  const entries = options ?? choices(children);
  const current = entries.find((e) => e.value === String(value ?? ""));
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState(""),
    [category, setCategory] = useState("");
  const [position, setPosition] = useState({ left: 0, top: 0, width: 320 });
  const trigger = useRef<HTMLButtonElement>(null),
    content = useRef<HTMLDivElement>(null);
  const id = useId();
  const title = props["aria-label"] || "Выберите вариант";
  const categories = [
    ...new Set(entries.flatMap((e) => (e.category ? [e.category] : []))),
  ];
  const visible = entries.filter(
    (e) =>
      (!category || e.category === category) &&
      (text(e.label) + " " + (e.description || ""))
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
  );
  const choose = (v: string) => {
    if (controlledValue === undefined) setUncontrolledValue(v);
    onValueChange?.(v);
    onChange?.({ target: { value: v } });
    setOpen(false);
  };
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCategory("");
    const place = () => {
      const box = trigger.current?.getBoundingClientRect();
      if (box)
        setPosition({
          left: Math.max(12, Math.min(box.left, innerWidth - 372)),
          top: Math.max(12, Math.min(box.bottom + 6, innerHeight - 400)),
          width: Math.min(Math.max(box.width, 320), innerWidth - 24),
        });
    };
    place();
    window.addEventListener("resize", place);
    // A sheet is one Back step, including Android's system Back gesture.
    const mobile = matchMedia("(max-width: 767px)").matches;
    const token = `choice-${id}-${Date.now()}`;
    let popped = false;
    if (mobile) history.pushState({ ...history.state, choiceSheet: token }, "");
    const back = () => {
      if (history.state?.choiceSheet !== token) {
        popped = true;
        setOpen(false);
      }
    };
    if (mobile) window.addEventListener("popstate", back);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("popstate", back);
      if (mobile && !popped && history.state?.choiceSheet === token)
        history.back();
    };
  }, [open, id]);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          {...props}
          ref={trigger}
          type="button"
          role="combobox"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={id}
          data-value={String(value ?? "")}
          className={`choice-trigger ${className}`}
        >
          <span>{current?.label ?? value ?? placeholder}</span>
          <span aria-hidden>⌄</span>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="choice-overlay" />
        <Dialog.Content
          id={id}
          ref={content}
          className="choice-content"
          style={
            {
              "--choice-left": `${position.left}px`,
              "--choice-top": `${position.top}px`,
              "--choice-width": `${position.width}px`,
            } as React.CSSProperties
          }
          onKeyDown={(e) => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key))
              return;
            if (
              (e.key === "Home" || e.key === "End") &&
              (e.target as HTMLElement).tagName === "INPUT"
            )
              return;
            const buttons = Array.from(
              content.current?.querySelectorAll<HTMLButtonElement>(
                "[role=option]:not(:disabled)",
              ) || [],
            );
            if (!buttons.length) return;
            e.preventDefault();
            const active = buttons.indexOf(
              document.activeElement as HTMLButtonElement,
            );
            const next =
              e.key === "Home"
                ? 0
                : e.key === "End"
                  ? buttons.length - 1
                  : (active +
                      (e.key === "ArrowDown" ? 1 : -1) +
                      buttons.length) %
                    buttons.length;
            buttons[next].focus();
          }}
        >
          <div className="choice-heading">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close aria-label="Закрыть выбор">×</Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Выберите значение. Escape закрывает список; стрелки перемещают
            фокус.
          </Dialog.Description>
          {(searchable || allowCustom || entries.length > 7) && (
            <input
              className="choice-search"
              aria-label="Поиск вариантов"
              placeholder="Поиск…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
          {!!categories.length && (
            <SegmentedControl
              aria-label="Категория"
              value={category}
              onValueChange={setCategory}
              options={[
                { value: "", label: "Все" },
                ...categories.map((c) => ({ value: c, label: c })),
              ]}
            />
          )}
          <div
            className="choice-options"
            role="listbox"
            aria-label={String(title)}
          >
            {visible.map((e) => (
              <button
                key={e.value}
                role="option"
                aria-selected={e.value === String(value ?? "")}
                data-value={e.value}
                type="button"
                disabled={e.disabled}
                title={e.reason}
                onClick={() => choose(e.value)}
              >
                <span>
                  {e.label}
                  {e.description && <small>{e.description}</small>}
                  {e.disabled && e.reason && <small>{e.reason}</small>}
                </span>
                {e.value === String(value ?? "") && <span aria-hidden>✓</span>}
              </button>
            ))}
            {!visible.length && <p>Нет подходящих вариантов.</p>}
            {allowCustom &&
              query.trim() &&
              !entries.some((e) => e.value === query.trim()) && (
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => choose(query.trim())}
                >
                  Использовать «{query.trim()}»
                </button>
              )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export const SearchableChoice = (props: Props) => (
  <ChoiceControl {...props} searchable />
);
export function SegmentedControl({
  value,
  options,
  children,
  onValueChange,
  onChange,
  ...props
}: Props) {
  return (
    <div
      role="group"
      aria-label={props["aria-label"]}
      className="choice-segments"
    >
      {(options ?? choices(children)).map((e) => (
        <button
          key={e.value}
          type="button"
          disabled={props.disabled || e.disabled}
          title={e.reason}
          data-value={e.value}
          aria-pressed={e.value === String(value)}
          onClick={() => {
            onValueChange?.(e.value);
            onChange?.({ target: { value: e.value } });
          }}
        >
          {e.label}
        </button>
      ))}
    </div>
  );
}
export function ChoiceCards(props: Props) {
  return (
    <div className="choice-cards" role="group" aria-label={props["aria-label"]}>
      {(props.options ?? choices(props.children)).map((e) => (
        <button
          key={e.value}
          type="button"
          disabled={props.disabled || e.disabled}
          aria-pressed={e.value === String(props.value)}
          onClick={() => {
            props.onValueChange?.(e.value);
            props.onChange?.({ target: { value: e.value } });
          }}
        >
          <strong>{e.label}</strong>
          <p>{e.description}</p>
          {e.reason && <small>{e.reason}</small>}
        </button>
      ))}
    </div>
  );
}
export function MultiChoice({
  value,
  options,
  onChange,
  label,
}: {
  value: string[];
  options: Choice[];
  onChange: (values: string[]) => void;
  label: string;
}) {
  return (
    <fieldset className="choice-multi">
      <legend>{label}</legend>
      {options.map((e) => (
        <label key={e.value}>
          <input
            type="checkbox"
            checked={value.includes(e.value)}
            disabled={e.disabled}
            onChange={() =>
              onChange(
                value.includes(e.value)
                  ? value.filter((v) => v !== e.value)
                  : [...value, e.value],
              )
            }
          />
          {e.label}
          {e.reason && <small>{e.reason}</small>}
        </label>
      ))}
    </fieldset>
  );
}
export function Stepper({
  value,
  min = 0,
  max = 100,
  disabled,
  label,
  onChange,
}: {
  value: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  label: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="choice-stepper" role="group" aria-label={label}>
      <button
        type="button"
        disabled={disabled || value <= min}
        aria-label={`Уменьшить: ${label}`}
        onClick={() => onChange(value - 1)}
      >
        −
      </button>
      <output aria-label={label}>{value}</output>
      <button
        type="button"
        disabled={disabled || value >= max}
        aria-label={`Увеличить: ${label}`}
        onClick={() => onChange(value + 1)}
      >
        +
      </button>
    </div>
  );
}
