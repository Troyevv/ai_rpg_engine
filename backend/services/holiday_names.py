"""Display-only adapter for the pinned holidays catalogs, never holiday rules.

Dates and IDs always come from calendar_presets.source(). Matching by translated
list position is unsafe: get_list() sorts names differently in each language.
"""
from datetime import datetime
from functools import lru_cache
import re

import holidays


def display_locale(requested, calendar):
    """Resolve only explicit supported locales; never let gettext use the host locale."""
    value = (requested or '').replace('-', '_').casefold()
    supported = calendar.supported_languages
    exact = next((x for x in supported if x.casefold() == value), None)
    if exact:
        return exact
    base = value.split('_')[0]
    matches = [x for x in supported if x.split('_')[0].casefold() == base]
    return matches[0] if len(matches) == 1 else 'en_US'


def _messages(calendar):
    # holidays 0.87 uses GNUTranslations. Read catalogs, including parent domains,
    # to associate msgids, not dates or alphabetic positions. No global patching.
    translation = calendar.tr.__self__
    keys = set()
    while translation is not None:
        keys.update(k for k in getattr(translation, '_catalog', {}) if isinstance(k, str) and k)
        translation = getattr(translation, '_fallback', None)
    return keys


def _translator(source, target):
    pairs = {}
    for key in sorted(_messages(source) | _messages(target)):
        english, localized = source.tr(key), target.tr(key)
        # A missing non-native translation must retain the English source name.
        if localized == key and target.language != target.default_language and key != english:
            continue
        pairs.setdefault(english, set()).add(localized)
    templates = [(key, re.compile(re.escape(key).replace('%s', '(.+)')), value)
                 for key, values in pairs.items() for value in sorted(values)
                 if key.count('%s') == value.count('%s') == 1]

    def candidates(name, depth=0):
        if name in pairs:
            return pairs[name]
        if depth > 2:
            return {name}
        results = set()
        for source_template, pattern, template in templates:
            match = pattern.fullmatch(name)
            if not match:
                continue
            inner = match[1]
            # Substitution labels include a formatted date, supplied by the
            # library's own metadata; no dates or regional rules are recreated.
            date_format = getattr(source, 'substituted_date_format', None)
            if date_format and source_template == source.tr(getattr(source, 'substituted_label', '')):
                try:
                    value = datetime.strptime(inner, source.tr(date_format)).strftime(target.tr(date_format))
                except ValueError:
                    continue
                results.add(template % value)
            else:
                results.update(template % value for value in candidates(inner, depth + 1))
        return results or {name}

    def translate(name, allowed=None):
        values = candidates(name)
        if allowed is not None:
            values = values & allowed
        return next(iter(values)) if len(values) == 1 else name
    return translate


@lru_cache(maxsize=128)
def _names(country, subdivision, years, observed, locale):
    from backend.services.calendar_presets import source
    english = source(country, subdivision, years, observed)
    target = holidays.country_holidays(country, subdiv=subdivision, years=years,
        expand=False, language=locale, observed=observed, categories='public')
    translate = _translator(english, target)
    result = {}
    for day in english:
        translated = set(target.get_list(day))
        for name in english.get_list(day):
            candidate = translate(name, translated)
            # Only names actually produced by the same pinned rule set can be
            # displayed. Ambiguous/missing entries deterministically stay English.
            result[day.isoformat(), name] = candidate if candidate in translated else name
    return result


def localized_names(regional, years, requested):
    from backend.services.calendar_presets import source
    calendar = source(regional['country'], regional.get('subdivision'))
    locale = display_locale(requested, calendar)
    if locale == 'en_US':
        return {}
    try:
        return _names(regional['country'], regional.get('subdivision'), tuple(sorted(years)),
                      bool(regional.get('observed')), locale)
    except OSError:
        # A missing translation catalog must not make a saved calendar unloadable.
        return {}
