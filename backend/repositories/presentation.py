"""World-scoped presentation metadata. Never part of runtime snapshots or LLM context."""
import json
import re
from typing import Literal

ThemeId = Literal['graphite', 'gothic', 'parchment', 'noir', 'neon']


def suggested_theme(text):
    # A fixed presentation heuristic, not a model call. Only used on explicit Auto selection.
    for theme, pattern in (
        ('neon', r'киберпанк|cyberpunk|sci-fi|космическ|научн.{0,8}фантаст'),
        ('gothic', r'готик|gothic|horror|хоррор|вампир|vampire|dark fantasy|т[её]мн.{0,4}фэнтези'),
        ('noir', r'нуар|noir|детектив'),
        ('parchment', r'фэнтези|fantasy|средневек|historical|историческ'),
    ):
        if re.search(pattern, text, re.I):
            return theme
    return 'graphite'


class PresentationStorage:
    def init_presentation(self):
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS world_presentation (
                world_id INTEGER PRIMARY KEY REFERENCES worlds(id), payload TEXT NOT NULL)''')

    def get_presentation(self, world_id):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM worlds WHERE id=?', (world_id,)).fetchone():
                raise ValueError('Мир не найден.')
            row = db.execute('SELECT payload FROM world_presentation WHERE world_id=?', (world_id,)).fetchone()
        value = json.loads(row['payload']) if row else {'theme_id': 'graphite', 'mode': 'manual'}
        return {key: value[key] for key in ('theme_id', 'mode')}

    def set_presentation(self, world_id, theme_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            world = db.execute('SELECT name,source_md FROM worlds WHERE id=?', (world_id,)).fetchone()
            if not world:
                raise ValueError('Мир не найден.')
            row = db.execute('SELECT payload FROM world_presentation WHERE world_id=?', (world_id,)).fetchone()
            value = json.loads(row['payload']) if row else {}
            if theme_id == 'auto':
                value.setdefault('auto_theme_id', suggested_theme(world['name'] + '\n' + world['source_md']))
                value.update(theme_id=value['auto_theme_id'], mode='auto')
            else:
                value.update(theme_id=theme_id, mode='manual')
            db.execute('INSERT INTO world_presentation VALUES(?,?) ON CONFLICT(world_id) DO UPDATE SET payload=excluded.payload',
                       (world_id, json.dumps(value)))
        return {key: value[key] for key in ('theme_id', 'mode')}
