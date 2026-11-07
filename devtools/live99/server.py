"""Private subprocess. Install the guard before the engine imports the provider."""
from pathlib import Path
import json
import sys

import llm
import uvicorn
from .budget import Budget, MODEL


def main():
    directory, fd, mode = sys.argv[1:]
    ledger = Path(directory) / 'budget.sqlite'
    if not ledger.is_file():
        raise SystemExit('Missing budget ledger; refusing to reset spending history')
    manifest = json.loads((Path(directory) / 'manifest.json').read_text())
    budget = Budget(ledger, Path(directory) if manifest.get('stage') == 'B' else None,
                    stage_c=Path(directory) if manifest.get('stage') == 'C' else None)
    if mode == 'live' and MODEL not in llm.get_deepseek_models():
        raise SystemExit('Configured model unavailable')

    original = budget.wrap(llm.chat_stream)

    def disabled(*args, **kwargs):
        raise RuntimeError('Preflight forbids model requests')

    llm.chat_stream = original if mode == 'live' else disabled
    from backend.api.app import create_app
    app = create_app(Path(directory) / 'game.sqlite')
    uvicorn.run(app, fd=int(fd), access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
