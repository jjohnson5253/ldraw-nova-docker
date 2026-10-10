"""Try the unrestricted example through the real restricted publication tool.

Run inside the web container with its backend on PYTHONPATH. The input is copied
into the existing restricted chat's output directory, and removed afterwards.
No LLM request is made and the existing models and palette selection are kept.
"""
import argparse
import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

import parts_policy
import settings
import tools
from store import get_store


def hashes():
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in settings.GENERATED_DIR.glob('*.mpd')}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('chat_id', help='An idle chat with the restriction enabled')
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    store = get_store()
    if not store.get_chat(args.chat_id) or parts_policy.policy.load(args.chat_id) is None:
        raise ValueError('Choose an existing restricted chat')
    source_bytes = args.source.read_bytes()
    before = hashes()
    with tempfile.NamedTemporaryFile(dir=store.work_dir(args.chat_id), suffix='.mpd') as candidate:
        candidate.write(source_bytes); candidate.flush()
        ctx = tools.ToolContext(args.chat_id, store, lambda *args: None)
        try:
            await tools.t_publish_model(ctx, candidate.name, 'Palette rejection audit')
        except tools.ToolError as exc:
            if 'Palette validation blocked publication' not in str(exc):
                raise
            error = str(exc)
        else:
            raise AssertionError('An out-of-palette model was published')
    assert before == hashes(), 'Generated models changed during rejection'
    print(json.dumps({'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
                      'blocked': True, 'generated_models_unchanged': True, 'error': error}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
