"""Interval arithmetic for #43, using the canonical #37 calendar adapter.

No day/year expansion: annual recurrences are represented by first/last/count.
"""

import calendar as gregorian
from backend.runtime_v3.calendar import (
    current_time,
    profile_of,
    date_parts,
    ordinal,
    _dates,
)


def target_minute(state, amount, unit):
    if type(amount) is not int or not 1 <= amount <= 200:
        raise ValueError("Выбери интервал от 1 до 200 единиц.")
    now = state["meta"]["world_time"]
    if unit == "weeks":
        target = now + amount * 7 * 1440
    elif unit in ("months", "years"):
        today = current_time(state)["date"]
        if not today:
            raise ValueError("Для месяцев и лет нужна установленная дата календаря.")
        profile = profile_of(state)
        year, month, day = date_parts(today, profile)
        months = (
            len(profile["month_lengths"]) if profile.get("system") == "custom" else 12
        )
        index = (
            (year - 1) * months
            + month
            - 1
            + amount * (months if unit == "years" else 1)
        )
        y, m = divmod(index, months)
        y += 1
        m += 1
        length = (
            profile["month_lengths"][m - 1]
            if profile.get("system") == "custom"
            else gregorian.monthrange(y, m)[1]
        )
        destination = f"{y:04d}-{m:02d}-{min(day, length):02d}"
        target = now + (ordinal(destination, profile) - ordinal(today, profile)) * 1440
    else:
        raise ValueError("Неизвестная единица длительного перехода.")
    if target - now <= 10080:
        raise ValueError("До 7 суток используй обычный пропуск времени.")
    if current_time(state)["date"] and not current_time(state, target)["date"]:
        raise ValueError("Интервал выходит за диапазон календаря.")
    return target


def annual_occurrences(state, start, target, relevant_ids):
    """One row per configured date, including Gregorian Feb 29 without year loops."""
    profile = profile_of(state)
    first_date, last_date = (
        current_time(state, start)["date"],
        current_time(state, target)["date"],
    )
    if not first_date or not last_date:
        return []
    sy, sm, sd = date_parts(first_date, profile)
    ey, em, ed = date_parts(last_date, profile)
    anchor = ordinal(first_date, profile)

    def leap_count(y):
        return y // 4 - y // 100 + y // 400

    rows = []
    for rule in _dates(state, relevant_ids):
        month, day = rule["month"], rule["day"]
        lo = max(sy + int((month, day) <= (sm, sd)), rule.get("since_year", 1))
        hi = ey - int((month, day) > (em, ed))
        if lo > hi:
            continue
        leap = profile.get("system") != "custom" and (month, day) == (2, 29)
        if leap:
            count = leap_count(hi) - leap_count(lo - 1)
            if not count:
                continue
            # A Gregorian century can skip at most one four-year recurrence.
            lo += (-lo) % 4
            if not gregorian.isleap(lo):
                lo += 4
            hi -= hi % 4
            if not gregorian.isleap(hi):
                hi -= 4
        else:
            count = hi - lo + 1
        first = f"{lo:04d}-{month:02d}-{day:02d}"
        last = f"{hi:04d}-{month:02d}-{day:02d}"
        rows.append(
            dict(
                rule,
                first_date=first,
                last_date=last,
                count=count,
                minute=start + (ordinal(first, profile) - anchor) * 1440,
            )
        )
    return sorted(rows, key=lambda r: (r["minute"], r["id"]))
