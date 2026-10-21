import { Check } from "@phosphor-icons/react/dist/ssr";

interface ChoiceGroupProps {
  name: string;
  choices: [value: string, label: string][];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/**
 * Radio buttons drawn as square ink tiles. The chosen one fills with ink and gains a check, so the state reads
 * without its words. The native radios stay in the page for keyboard and screen reader use.
 */
export function ChoiceGroup({ name, choices, value, onChange, disabled = false }: ChoiceGroupProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {choices.map(([choice, label]) => (
        <label
          key={choice}
          className="pressable inline-flex cursor-pointer items-center gap-2 border border-ink px-4 py-2 font-medium hover:bg-ink/5 has-checked:bg-ink has-checked:text-paper has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent has-disabled:cursor-not-allowed has-disabled:opacity-40"
        >
          <input type="radio" name={name} value={choice} checked={value === choice} onChange={() => onChange(choice)} disabled={disabled} className="peer sr-only" />
          <Check size={16} weight="bold" aria-hidden className="hidden peer-checked:block" />
          {label}
        </label>
      ))}
    </div>
  );
}
