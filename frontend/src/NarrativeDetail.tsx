import { Choice } from "./components/ui/choice";
import { gameLocale } from "./gameDate";

const modes = [
  ["brief", "Кратко", "Brief"],
  ["balanced", "Сбалансированно", "Balanced"],
  ["detailed", "Подробно", "Detailed"],
  ["extended", "Развёрнуто", "Extended"],
];

export function NarrativeDetail({value, onChange, disabled}: {
  value?: string; onChange: (mode: string) => void; disabled?: boolean;
}) {
  const en = gameLocale().startsWith("en");
  const title = en ? "Narrative detail" : "Подробность повествования";
  return <label>{title}
    <Choice aria-label={title} value={value ?? "balanced"} onValueChange={onChange} disabled={disabled}>
      {modes.map(([id, ru, english]) => <option key={id} value={id}>{en ? english : ru}</option>)}
    </Choice>
    <small>{en ? "Sets how richly the current moment is described. You still choose your next action."
      : "Определяет, насколько подробно ведущий опишет текущий момент. Следующее решение остаётся за вами."}</small>
  </label>;
}
