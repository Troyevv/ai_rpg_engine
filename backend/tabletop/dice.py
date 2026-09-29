"""Server-side dice; injected RNG supports deterministic domain tests."""
import random
import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Roll:
    expression: str
    raw: list[int]
    selected: int
    modifier: int
    total: int
    purpose: str
    actor: str
    advantage: int

    def as_dict(self):
        return asdict(self)


class DiceEngine:
    def __init__(self, rng=None):
        self.rng = rng or random.SystemRandom()

    def roll(self, expression, *, modifier=0, advantage=0, purpose='', actor='', critical=False, critical_rule='double_dice'):
        match = re.fullmatch(r'(\d{0,2})d(4|6|8|10|12|20|100)([+-]\d{1,3})?', expression)
        if not match:
            raise ValueError('Неподдерживаемый бросок')
        count, sides = int(match[1] or 1), int(match[2])
        modifier += int(match[3] or 0)
        if not 1 <= count <= 20 or advantage not in (-1, 0, 1) or advantage and (count != 1 or sides != 20):
            raise ValueError('Некорректный бросок')
        if critical and critical_rule not in ('double_dice', 'max_dice'):
            raise ValueError('Неизвестное правило критического урона')
        n = count * 2 if critical and critical_rule == 'double_dice' else count
        raw = [self.rng.randint(1, sides) for _ in range(2 if advantage else n)]
        selected = (max(raw) if advantage > 0 else min(raw)) if advantage else sum(raw)
        if critical and critical_rule == 'max_dice':
            selected += count * sides
        return Roll(expression, raw, selected, modifier, selected + modifier, purpose, actor, advantage)
