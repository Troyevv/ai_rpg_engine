"""Presentation guard. Rejected prose never causes another LLM call or a mutation."""

import re

# This is a conservative output gate, not a natural-language rules interpreter.
MECHANICAL_PROSE = re.compile(
    r"(?:брос\w*|кин\w*|roll|throw)\s.{0,45}(?:куб|кости|кост[ьи]|d\s*\d|initiative|инициатив|damage|урон)"
    r"|(?:сдела\w*|пройд\w*|выполн\w*|нуж\w*|требу\w*|make|perform)\s.{0,45}(?:проверк|спасброс|saving\s+throw|check)"
    r"|\b(?:dc|кд)\s*[:=]?\s*\d+|\bd\s*20\b"
    r"|(?:потер\w*|получ\w*|нанес\w*|восстанов\w*|добав\w*|отним\w*|take|deal|gain|heal|lose|add)\s.{0,30}(?:\d+\s*(?:hp|хп|урон|здоров|damage)|[+−-]\s*\d+)"
    r"|(?:потра\w*|израсход\w*|spend|use)\s.{0,30}(?:ячейк|spell\s+slot)"
    r"|(?:получ\w*|добав\w*|gain|add)\s.{0,25}(?:предмет|инвентар|состояни|condition|item)"
    r"|(?:нажми|нажмите|click|press)\b"
    r"|(?:выбери|выберите)\s+действие\s*\d",
    re.IGNORECASE,
)


def contains_mechanical_instruction(text):
    return bool(MECHANICAL_PROSE.search(text))


def safe_narration(text):
    if contains_mechanical_instruction(text):
        return "Результат действия сохранён в журнале."
    return text
