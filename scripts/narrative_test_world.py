"""Opt-in load/reset command; no production HTTP route or frontend control."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Загрузить/сбросить Narrative QA мир в новое прохождение.')
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'dev-narrative-v4.sqlite3',
                        help='SQLite dev-сервера; по умолчанию отдельная QA база, не RPG_DB_PATH.')
    parser.add_argument('--checkpoint', default='base')
    args = parser.parse_args(argv)
    if os.environ.get('RPG_DEV_TOOLS') != '1':
        parser.error('Команда доступна только при явном RPG_DEV_TOOLS=1.')
    from devtools.narrative_test_world import build_fixture, load_fixture
    from backend.repositories.preparation import Repository
    # Reject invalid checkpoint selection before even opening/migrating a DB.
    build_fixture(args.checkpoint)
    result = load_fixture(Repository(args.db), args.checkpoint)
    print(json.dumps(dict(result, database=str(args.db.resolve())), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
