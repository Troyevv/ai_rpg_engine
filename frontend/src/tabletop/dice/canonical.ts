import type { Roll } from "../types";
export type VisualDie = {
  sides: number;
  value: number;
  label: string;
  muted: boolean;
  sign: number;
  percentile?: "tens" | "ones";
};
export function canonicalDice(rolls: Roll[], limit = 12) {
  const all: VisualDie[] = [];
  for (const roll of rolls) {
    const components = roll.components || [
      {
        die: Number(roll.expression.match(/d(\d+)/)?.[1] || 20),
        raw: roll.raw,
        selected: roll.selected,
        sign: 1,
      },
    ];
    for (const [index, c] of components.entries()) {
      const chosen =
        index === 0 && roll.advantage ? c.raw.indexOf(c.selected) : -1;
      for (const [i, value] of c.raw.entries()) {
        const muted = chosen >= 0 && i !== chosen;
        if (c.die === 100) {
          const n = value % 100;
          all.push(
            {
              percentile: "tens",
              sides: 10,
              value: Math.floor(n / 10) + 1,
              label: String(Math.floor(n / 10) * 10).padStart(2, "0"),
              muted,
              sign: c.sign,
            },
            {
              percentile: "ones",
              sides: 10,
              value: (n % 10) + 1,
              label: String(n % 10),
              muted,
              sign: c.sign,
            },
          );
        } else
          all.push({
            sides: c.die,
            value,
            label: String(value),
            muted,
            sign: c.sign,
          });
      }
    }
  }
  return {
    dice: all.slice(0, limit),
    omitted: Math.max(0, all.length - limit),
  };
}
