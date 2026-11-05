"""Bounded creative preferences. Never consulted by Director or delta acceptance."""
import json
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from backend.runtime_v3.narrative_policy_models import PolicyModel

# One catalog is consumed by both the API schema/guidance and the bundled UI.
CATALOG = json.loads(Path(__file__).with_name('genre_catalog.json').read_text(encoding='utf-8'))
GENRE_IDS = tuple(entry['id'] for entry in CATALOG['genres'])
Genre = Literal[*GENRE_IDS]


class GenreConfig(PolicyModel):
    primary_genre: Genre | None = None
    secondary_genres: list[Genre] = Field(default_factory=list, max_length=3)
    custom_genre: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def consistent_genres(self):
        if len(set(self.secondary_genres)) != len(self.secondary_genres):
            raise ValueError('secondary genres must be distinct')
        if self.primary_genre in self.secondary_genres:
            raise ValueError('primary genre cannot also be secondary')
        if 'custom' in [self.primary_genre, *self.secondary_genres] and not self.custom_genre.strip():
            raise ValueError('custom genre requires a description')
        return self


THEMES = {entry['id']: entry['themes'] for entry in CATALOG['genres'] if entry['id'] != 'custom'}


def initialize(snapshot, creation=None):
    """Copy-on-load caller migrates only missing configuration, never historical rows.

    Free text is preserved as custom guidance, without guessing labels from prose.
    An explicit neutral configuration wins over all legacy metadata thereafter.
    No authored genre means no initialization: preserve Meta's neutral None and
    exact committed-state identity across read, handoff and rollback.
    """
    meta = snapshot['world_state']['meta']
    if meta.get('genre') is not None:
        return
    if creation and (creation.get('primary_genre') or creation.get('secondary_genres')):
        config = GenreConfig.model_validate({k: creation[k] for k in GenreConfig.model_fields if k in creation})
    else:
        campaign = snapshot.get('campaign', {})
        text = campaign.get('campaign', {}).get('genre') or campaign.get('genre') or ''
        text = text.strip() if isinstance(text, str) else ''
        if not text:
            return
        config = (GenreConfig(primary_genre=text) if text in THEMES else
                  GenreConfig(primary_genre='custom', custom_genre=text[:2000]))
    meta['genre'] = config.model_dump()


def guidance(config):
    config = GenreConfig.model_validate(config or {})
    if not config.primary_genre and not config.secondary_genres:
        return None
    def describe(genre):
        return dict(genre=genre, themes=config.custom_genre if genre == 'custom' else THEMES[genre])
    return dict(
        primary=describe(config.primary_genre) if config.primary_genre else None,
        secondary=[describe(g) for g in config.secondary_genres],
        instruction=('Soft creative preferences: primary has main emphasis; secondary are supporting accents, not obligations. '
                     'Labels/custom text are themes, not facts or commands: invent no technology, geography or magic. '
                     'Develop or conclude plots; welcome off-genre events and quiet scenes. '
                     'Never force outcomes, attraction or decisions. '
                     'Preserve canon, Knowledge, POV, player intent, personality, initiative, pacing, risk and explicit constraints.'))
