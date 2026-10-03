"""Bounded expression parser and server-owned RNG shared by all mechanical systems."""

import random
import re
from dataclasses import asdict, dataclass, field


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
    components: list[dict] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


class DiceEngine:
    def __init__(self, rng=None):
        self.rng = rng or random.SystemRandom()

    @staticmethod
    def parse(expression):
        if not isinstance(expression, str) or len(expression) > 120:
            raise ValueError("Некорректное выражение кубиков")
        expression = expression.replace(" ", "")
        tokens = re.findall(r"[+-]?[^+-]+", expression)
        if not tokens or "".join(tokens) != expression:
            raise ValueError("Некорректное выражение кубиков")
        terms = []
        dice = 0
        for token in tokens:
            sign = -1 if token.startswith("-") else 1
            atom = token.lstrip("+-")
            m = re.fullmatch(r"(\d{0,2})d(4|6|8|10|12|20|100)", atom)
            if m:
                count = int(m[1] or 1)
                sides = int(m[2])
                if not 1 <= count <= 20:
                    raise ValueError("Слишком много кубиков")
                dice += count
                terms.append((sign, count, sides))
            elif re.fullmatch(r"\d{1,3}", atom):
                terms.append((sign, int(atom), 0))
            else:
                raise ValueError("Неподдерживаемый бросок")
        if next((t for t in terms if t[2]), (0, 0, 0))[0] < 0:
            raise ValueError("Основной кубик не может быть отрицательным")
        if not 1 <= dice <= 100:
            raise ValueError("Нужны от 1 до 100 кубиков")
        return terms

    def roll(
        self,
        expression,
        *,
        modifier=0,
        advantage=0,
        purpose="",
        actor="",
        critical=False,
        critical_rule="double_dice"
    ):
        terms = self.parse(expression)
        dice_terms = [t for t in terms if t[2]]
        if advantage not in (-1, 0, 1) or advantage and dice_terms[0] != (1, 1, 20):
            raise ValueError("Преимущество применимо к основному d20")
        if critical_rule not in ("double_dice", "max_dice"):
            raise ValueError("Неизвестное правило критического урона")
        raw = []
        components = []
        dice_total = 0
        primary = None
        for sign, count, sides in terms:
            if not sides:
                modifier += sign * count
                continue
            primary_d20 = primary is None and count == 1 and sides == 20 and sign == 1
            n = (
                2
                if primary_d20 and advantage
                else count * (2 if critical and critical_rule == "double_dice" else 1)
            )
            values = [self.rng.randint(1, sides) for _ in range(n)]
            value = (
                (max(values) if advantage > 0 else min(values))
                if primary_d20 and advantage
                else sum(values)
            )
            if critical and critical_rule == "max_dice":
                value += count * sides
            if primary_d20:
                primary = value
            dice_total += sign * value
            raw.extend(values)
            components.append(dict(die=sides, raw=values, selected=value, sign=sign))
        return Roll(
            expression,
            raw,
            primary if primary is not None else dice_total,
            modifier,
            dice_total + modifier,
            purpose,
            actor,
            advantage,
            components,
        )
