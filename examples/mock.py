# -*- coding: utf-8 -*-
"""Render the status line for a few made-up sessions, without Claude Code.

    python examples/mock.py                 all scenarios
    python examples/mock.py danger          one scenario
    python examples/mock.py --svg docs/images   also write SVG previews
Uses a throwaway config/state folder, so your real ~/.claude is never touched.
"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='slw-mock-')
atexit.register(shutil.rmtree, TMP, True)
os.environ['CLAUDE_CONFIG_DIR'] = os.path.join(TMP, 'claude')
os.environ['CLAUDE_STATUSLINE_STATE_DIR'] = os.path.join(TMP, 'state')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import statusline as sl  # noqa: E402

NOW = time.time()
H = 3600


def fake_repo(name, branch, dirty):
    """A folder with just .git/HEAD, plus a pre-seeded dirty flag so no git process is needed."""
    path = os.path.join(TMP, name)
    os.makedirs(os.path.join(path, '.git'), exist_ok=True)
    with open(os.path.join(path, '.git', 'HEAD'), 'w') as f:
        f.write(f'ref: refs/heads/{branch}\n')
    cache = sl._load_json(sl.GIT_CACHE)
    cache[path] = {'t': NOW + 600, 'dirty': dirty}
    sl._save_json(sl.GIT_CACHE, cache)
    return path


def session(ctx, five, seven, *, repo, model='claude-opus-5-5', effort='high', lines=(0, 0),
            minutes=0, cache_min=None, rate=True):
    d = {
        'model': {'id': model, 'display_name': sl.display_name_from_id(model)},
        'workspace': {'current_dir': repo, 'project_dir': repo},
        'thinking': {'enabled': True}, 'effort': {'level': effort},
        'context_window': {'used_percentage': ctx, 'context_window_size': 1_000_000,
                           'total_input_tokens': ctx * 10_000, 'total_output_tokens': 0},
        'cost': {'total_lines_added': lines[0], 'total_lines_removed': lines[1],
                 'total_duration_ms': minutes * 60_000},
    }
    if rate:
        d['rate_limits'] = {'five_hour': {'used_percentage': five, 'resets_at': NOW + 4.4 * H},
                            'seven_day': {'used_percentage': seven, 'resets_at': NOW + 133 * H}}
    if cache_min is not None:
        d['prompt_cache'] = {'warm': True, 'expires_at': NOW + cache_min * 60}
    return d


def scenarios():
    return {
        'normal': session(42, 34, 12, repo=fake_repo('my-project', 'main', False),
                          lines=(128, 37), minutes=46, cache_min=52),
        'warning': session(75, 72, 58, repo=fake_repo('api-server', 'feature/login', True),
                           model='claude-sonnet-5-5', effort='medium', lines=(412, 96), minutes=138, cache_min=17),
        'danger': session(92, 91, 88, repo=fake_repo('legacy-app', 'hotfix', True),
                          lines=(1240, 815), minutes=287, cache_min=3),
        'startup': session(3, None, None, repo=fake_repo('new-idea', 'main', False), rate=False),
    }


def main():
    args = sys.argv[1:]
    svg_dir = None
    if '--svg' in args:
        i = args.index('--svg')
        svg_dir = args[i + 1]
        del args[i:i + 2]
    all_s = scenarios()
    names = args or list(all_s)
    stream = sys.stdout.buffer
    for name in names:
        sl._save_json(sl.QUOTA_CACHE, {})          # each scenario starts with an empty quota cache
        out = sl.render(all_s[name])
        stream.write(f'── {name}\n{out}\n\n'.encode('utf-8'))
        if svg_dir:
            from ansi2svg import to_svg
            os.makedirs(svg_dir, exist_ok=True)
            with open(os.path.join(svg_dir, f'{name}.svg'), 'w', encoding='utf-8') as f:
                f.write(to_svg(out.splitlines()))
    stream.flush()


if __name__ == '__main__':
    main()
