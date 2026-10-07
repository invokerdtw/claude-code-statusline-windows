#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claude-code-statusline-windows — a Windows-first status line for Claude Code.

Line 1  CTX ██████░░░░ 185k/1.0M 19%  │  5h ███░░░░░ 34% 4h25m  │  7d █░░░░░░░ 9% 5d14h
Line 2  Opus 5.5  high  main*  +67/-17  my-project  cache→00:43  28m

Python 3.8+, standard library only (no jq, no bash, no Node unless you opt in to burn rate).
Every value comes from the JSON Claude Code pipes to stdin; nothing is estimated locally.

Run it with pythonw.exe so Windows never flashes a console window.
"""
import json
import math
import os
import re
import subprocess
import sys
import time

__version__ = '1.0.0'

IS_WIN = os.name == 'nt'
# CREATE_NO_WINDOW: child processes (git.exe, npx.cmd) would otherwise pop a black console
# window every time the status line refreshes. pythonw alone does not prevent this, because
# console programs spawned from it allocate their own console.
NO_WINDOW = {'creationflags': 0x08000000} if IS_WIN else {}


# ── Settings (environment variables) ────────────────────────────────────────────────────────
def _env_flag(name):
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


WARN = _env_int('CLAUDE_STATUSLINE_WARN', 65)        # yellow from this percentage
CRIT = _env_int('CLAUDE_STATUSLINE_CRIT', 85)        # red from this percentage
ASCII = _env_flag('CLAUDE_STATUSLINE_ASCII')         # no block characters / no emoji
BURN_RATE = _env_flag('CLAUDE_STATUSLINE_BURN_RATE')  # tokens/min via ccusage (needs Node)
SHOW_COST = _env_flag('CLAUDE_STATUSLINE_SHOW_COST')  # API users; subscribers usually hide it
GIT_IN_CLOUD = _env_flag('CLAUDE_STATUSLINE_GIT_IN_CLOUD')  # force git even on cloud drives
NO_GIT_PATHS = [p.strip() for p in os.environ.get('CLAUDE_STATUSLINE_NO_GIT', '').split(';') if p.strip()]

CLAUDE_DIR = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(os.path.expanduser('~'), '.claude')
# Cache files live in %LOCALAPPDATA% (the Windows place for caches), not in ~/.claude: many people keep
# ~/.claude in git, and machine-local caches must never end up in commits.
DEFAULT_STATE_DIR = (os.path.join(os.environ['LOCALAPPDATA'], 'claude-code-statusline-windows')
                     if IS_WIN and os.environ.get('LOCALAPPDATA')
                     else os.path.join(CLAUDE_DIR, 'statusline-windows', 'state'))
STATE_DIR = os.environ.get('CLAUDE_STATUSLINE_STATE_DIR') or DEFAULT_STATE_DIR
QUOTA_CACHE = os.path.join(STATE_DIR, 'quota_cache.json')
GIT_CACHE = os.path.join(STATE_DIR, 'git_cache.json')
USAGE_CACHE = os.path.join(STATE_DIR, 'usage_cache.json')
USAGE_LOCK = os.path.join(STATE_DIR, 'usage_update.lock')
MODEL_STATE = os.path.join(STATE_DIR, 'model_state.json')
ACCOUNT_MEMO = os.path.join(STATE_DIR, 'account_memo.json')
CCUSAGE = 'ccusage@20.0.26'   # pinned: never auto-run whatever npm publishes next

GIT_TTL = 5          # seconds a cached dirty flag stays valid
USAGE_TTL = 300      # seconds between ccusage refreshes
USAGE_LOCK_TTL = 120  # do not start another refresh while one started this recently


# ── Small file helpers ─────────────────────────────────────────────────────────────────────
def _load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _d(obj):
    """Treat anything that is not a JSON object as an empty one (defensive: never crash on input)."""
    return obj if isinstance(obj, dict) else {}


def _num(value):
    """A number from stdin, or None. Rejects strings/booleans instead of crashing on them."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None   # json accepts Infinity / NaN


def _epoch(value):
    """Epoch seconds per the Claude Code spec; tolerate milliseconds just in case."""
    v = _num(value)
    if v is None or v <= 0:
        return None
    return v / 1000 if v > 1e11 else v


def _save_json(path, obj):
    """Write via a temp file + os.replace so a half-written file is never read.
    ensure_ascii=True: Windows paths can carry lone surrogates that make a UTF-8 dump fail midway."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f'{path}.{os.getpid()}.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ── stdin ─────────────────────────────────────────────────────────────────────────────────
def read_stdin():
    """Decode stdin as UTF-8 bytes ourselves. Python on Windows decodes text stdin with the ANSI
    code page (cp1252, cp950, …), which corrupts any non-ASCII path inside the JSON."""
    if sys.stdin is None:
        return {}
    try:
        raw = sys.stdin.buffer.read()
        return _d(json.loads(raw.decode('utf-8', 'replace'))) if raw.strip() else {}
    except Exception:
        return {}


# ── Quota cache, scoped to the signed-in account ───────────────────────────────────────────
def account_fingerprint():
    """Who is signed in, without touching secrets:
    - plan fields from .credentials.json (on Windows the OAuth token is a plain file there, not the
      macOS Keychain — we read only subscriptionType / rateLimitTier, never the token);
    - a hash of oauthAccount.accountUuid from .claude.json, which /login rewrites, so two accounts
      on the same plan are told apart too."""
    import hashlib
    c = _d(_load_json(os.path.join(CLAUDE_DIR, '.credentials.json')).get('claudeAiOauth'))
    parts = [c.get('subscriptionType'), c.get('rateLimitTier')]
    # With CLAUDE_CONFIG_DIR set, Claude Code keeps .claude.json inside that folder; otherwise in home.
    cfg = (os.path.join(CLAUDE_DIR, '.claude.json') if os.environ.get('CLAUDE_CONFIG_DIR')
           else os.path.join(os.path.expanduser('~'), '.claude.json'))
    h = _account_hash(cfg, hashlib)
    if h:
        parts.append(h)
    return '/'.join(str(p) for p in parts if p) or None


def _account_hash(cfg, hashlib):
    """.claude.json grows to megabytes over time; parse it only when its mtime/size changed."""
    try:
        st = os.stat(cfg)
    except OSError:
        return None
    stamp = [cfg, st.st_mtime_ns, st.st_size]
    memo = _load_json(ACCOUNT_MEMO)
    if memo.get('stamp') == stamp:
        return memo.get('hash')
    uuid = _d(_load_json(cfg).get('oauthAccount')).get('accountUuid')
    h = hashlib.sha256(str(uuid).encode()).hexdigest()[:12] if uuid else None
    _save_json(ACCOUNT_MEMO, {'stamp': stamp, 'hash': h})
    return h


def resolve_rate_limits(stdin_data):
    """Claude Code only sends rate_limits after the first API reply of a session. Until then we
    show the last known values, with two guards, because an old number looks exactly like a
    correct one:
    - values saved under a different account (after /login) are dropped;
    - a window whose resets_at has already passed is dropped (it has reset; its old % is wrong)."""
    acct = account_fingerprint()
    live = _d(stdin_data.get('rate_limits'))
    if live:
        _save_json(QUOTA_CACHE, {'account': acct, 'rate_limits': live})
        return live
    cached = _load_json(QUOTA_CACHE)
    if acct and cached.get('account') and cached['account'] != acct:
        return {}
    now = time.time()
    return {k: w for k, w in _d(cached.get('rate_limits')).items()
            if isinstance(w, dict) and (_epoch(w.get('resets_at')) or 0) > now}


# ── Model name ────────────────────────────────────────────────────────────────────────────
_MODEL_ID_RE = re.compile(r'^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$')


def display_name_from_id(mid):
    """claude-opus-5-5 → Opus 5.5, claude-haiku-4-5-20251001 → Haiku 4.5.
    Derived from the id pattern so new models need no lookup-table update."""
    m = _MODEL_ID_RE.match(mid or '')
    if not m:
        return mid
    family, major, minor = m.groups()
    return f'{family.title()} {major}.{minor}' if minor else f'{family.title()} {major}'


def latest_model_from_transcript(path, tail_bytes=131072):
    """After /model, Claude Code keeps sending the old model until the next refresh.
    The transcript already has the new one, so read its last assistant model id."""
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            f.seek(max(0, size - tail_bytes))
            chunk = f.read().decode('utf-8', errors='ignore')
        for line in reversed(chunk.splitlines()):
            if '"model"' not in line:
                continue
            try:
                msg = json.loads(line).get('message') or {}
                mid = msg.get('model') if isinstance(msg, dict) else None
                if mid and mid != '<synthetic>':
                    return mid
            except Exception:
                continue
    except Exception:
        pass
    return None


def resolve_model_name(data):
    """stdin can lag behind /model, and the transcript lags too (it changes only after the next
    reply). So remember, per session, what the transcript said when stdin's model last changed:
    the transcript wins only once it has moved past that point to a different model."""
    model = _d(data.get('model'))
    sid, name = model.get('id'), model.get('display_name') or 'Claude'
    transcript = data.get('transcript_path')
    if not (isinstance(transcript, str) and os.path.isfile(transcript)):
        return name
    tid = latest_model_from_transcript(transcript)
    key = str(data.get('session_id') or transcript)
    state = _load_json(MODEL_STATE)
    st = _d(state.get(key))
    if st.get('stdin_id') != sid:                        # stdin just changed (or first sight)
        state[key] = {'stdin_id': sid, 'transcript_base': tid, 't': time.time()}
        if len(state) > 50:                              # keep the file small
            for old in sorted(state, key=lambda k: _d(state[k]).get('t', 0))[:-50]:
                state.pop(old, None)
        _save_json(MODEL_STATE, state)
        return name
    if tid and tid != st.get('transcript_base') and tid != sid:
        return display_name_from_id(tid)
    return name


# ── Git, without hanging on cloud drives ───────────────────────────────────────────────────
def _drive_label(path):
    """Volume label of the drive holding `path` ('Google Drive' for Google Drive for desktop)."""
    if not IS_WIN:
        return ''
    try:
        import ctypes
        root = os.path.splitdrive(os.path.abspath(path))[0] + '\\'
        buf = ctypes.create_unicode_buffer(261)
        if ctypes.windll.kernel32.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0):
            return buf.value
    except Exception:
        pass
    return ''


def is_cloud_path(path):
    """Git on a streaming cloud drive can block forever inside a file-system call. Such a git.exe
    ignores kill, keeps piling up, and may leave .git/index.lock behind. We never start git there.
    Google Drive is recognised by its volume label; OneDrive folders are skipped as a precaution
    (status would hydrate every on-demand file).
    CLAUDE_STATUSLINE_NO_GIT always applies; CLAUDE_STATUSLINE_GIT_IN_CLOUD only turns off the
    automatic Google Drive / OneDrive detection."""
    if any(_under(path, r) for r in NO_GIT_PATHS):
        return True
    if GIT_IN_CLOUD:
        return False
    if any(_under(path, os.environ.get(k, '')) for k in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial')):
        return True
    return 'google drive' in _drive_label(path).lower()


def _under(path, root):
    """True if `path` is `root` or inside it. Compares whole path components, so C:\\Work does
    not match C:\\Workspace."""
    if not root:
        return False
    p = os.path.normcase(os.path.abspath(path))
    r = os.path.normcase(os.path.abspath(root)).rstrip('\\/')
    return p == r or p.startswith(r + os.sep)


def find_git_dir(start):
    """Walk up to the repository; `.git` may be a directory or a 'gitdir:' file (worktrees)."""
    d = os.path.abspath(start)
    for _ in range(40):
        g = os.path.join(d, '.git')
        if os.path.isdir(g):
            return d, g
        if os.path.isfile(g):
            try:
                with open(g, encoding='utf-8', errors='replace') as f:
                    line = f.read().strip()
                if line.startswith('gitdir:'):
                    return d, os.path.abspath(os.path.join(d, line[7:].strip()))
            except Exception:
                pass
            return None, None
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None, None


def branch_from_head(gitdir):
    """Branch name straight from .git/HEAD — one tiny file read, no git process."""
    try:
        with open(os.path.join(gitdir, 'HEAD'), encoding='utf-8', errors='replace') as f:
            head = f.read().strip()
        if head.startswith('ref: refs/heads/'):
            return head[len('ref: refs/heads/'):]
        return head[:7] or None   # detached HEAD → short SHA
    except Exception:
        return None


def is_dirty(root):
    """Uncommitted changes to tracked files, cached for GIT_TTL seconds per repository.
    --no-optional-locks: a read-only status must not create .git/index.lock (frequent polling
    otherwise races with your own commits). Returns None when unknown."""
    cache = _load_json(GIT_CACHE)
    hit = cache.get(root)
    if hit and time.time() - hit.get('t', 0) < GIT_TTL:
        return hit.get('dirty')
    try:
        out = subprocess.run(
            ['git', '--no-optional-locks', '-C', root, 'status', '--porcelain', '--untracked-files=no'],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=3, **NO_WINDOW)
        dirty = bool(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        dirty = None
    cache[root] = {'t': time.time(), 'dirty': dirty}
    _save_json(GIT_CACHE, cache)
    return dirty


def git_segment(cwd):
    root, gitdir = find_git_dir(cwd)
    if not root:
        return ''
    branch = branch_from_head(gitdir)
    if not branch:
        return ''
    dirty = None if is_cloud_path(root) else is_dirty(root)
    return branch + ('*' if dirty else '')


# ── Optional burn rate (ccusage) ────────────────────────────────────────────────────────────
def burn_rate_tpm():
    """Rate-limit percentages move in coarse steps; a live tokens/min figure shows the session is
    still consuming. The refresh runs in a detached background process so rendering never waits."""
    if not BURN_RATE:
        return None
    cache = _load_json(USAGE_CACHE)
    if time.time() - (_num(cache.get('updated_at')) or 0) > USAGE_TTL:
        _spawn_usage_update()
    return _num(cache.get('burn_rate_tpm'))


def _spawn_usage_update():
    try:
        if os.path.exists(USAGE_LOCK) and time.time() - os.path.getmtime(USAGE_LOCK) < USAGE_LOCK_TTL:
            return   # a refresh is already running; do not start another npx
        os.makedirs(STATE_DIR, exist_ok=True)
        open(USAGE_LOCK, 'w').close()
        exe = sys.executable
        if IS_WIN:
            pyw = os.path.join(os.path.dirname(exe), 'pythonw.exe')
            exe = pyw if os.path.exists(pyw) else exe
        subprocess.Popen([exe, os.path.abspath(__file__), '--update-usage'],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, **NO_WINDOW)
    except Exception:
        pass


def update_usage_cache():
    """Background mode. On Windows npx is a batch file, so it must be called as npx.cmd."""
    npx = 'npx.cmd' if IS_WIN else 'npx'
    # Always stamp updated_at — also on failure (no Node, offline, …). Otherwise every redraw
    # would start another background npx.
    result = {'updated_at': time.time(), 'burn_rate_tpm': None}
    try:
        out = subprocess.run([npx, '-y', CCUSAGE, 'blocks', '--active', '--json'],
                             stdin=subprocess.DEVNULL, capture_output=True, timeout=90,
                             encoding='utf-8', errors='ignore', **NO_WINDOW)
        blocks = _d(json.loads(out.stdout)).get('blocks') or []
        result['burn_rate_tpm'] = _num(_d(_d(blocks[0]).get('burnRate')).get('tokensPerMinute')) if blocks else None
    except Exception as e:
        result['error'] = type(e).__name__
    finally:
        _save_json(USAGE_CACHE, result)
        try:
            os.remove(USAGE_LOCK)
        except Exception:
            pass


# ── Rendering ─────────────────────────────────────────────────────────────────────────────
RESET, GRAY, GREEN, YELLOW, RED = '\033[0m', '\033[90m', '\033[32m', '\033[33m', '\033[31m'
MAGENTA, CYAN, WHITE, BOLD = '\033[95m', '\033[96m', '\033[97m', '\033[1m'
FULL, EMPTY = ('#', '-') if ASCII else ('█', '░')
ARROW = '->' if ASCII else '→'
SEP = f'  {GRAY}{"|" if ASCII else "│"}{RESET}  '


def color_for(pct):
    if pct >= CRIT:
        return RED
    if pct >= WARN:
        return YELLOW
    return GREEN


def make_bar(pct, width):
    """Each cell is coloured by the percentage it represents, so a bar reads green → yellow → red
    as it fills, the same way on every terminal (no 24-bit colour needed)."""
    if pct is None:
        return GRAY + EMPTY * width + RESET
    filled = round(min(max(pct, 0), 100) / 100 * width)
    cells = [color_for((i + 1) / width * 100) + FULL if i < filled else GRAY + EMPTY for i in range(width)]
    return ''.join(cells) + RESET


def fmt_pct(pct):
    # round(): stdin percentages are floats; 7.000000000000001% must not leak onto the screen
    return f'{color_for(pct)}{round(pct)}%{RESET}' if pct is not None else f'{GRAY}--{RESET}'


def fmt_tokens(n):
    if not n:
        return '0'
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    if n >= 1000:
        return f'{n // 1000}k'
    return str(n)


def fmt_duration(seconds):
    if seconds <= 0:
        return ''
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f'{d}d{h}h'
    if h:
        return f'{h}h{m:02d}m'
    return f'{m}m' if m else '<1m'


def fmt_reset(resets_at):
    left = fmt_duration((_epoch(resets_at) or 0) - time.time())
    return f' {GRAY}{left}{RESET}' if left else ''


def fmt_burn(tpm):
    if not tpm or tpm < 1:
        return ''
    return f' {MAGENTA}{fmt_tokens(int(tpm))}/min{RESET}'


def _text(value):
    return value if isinstance(value, str) and value else None


def render(data, now=None):
    now = now or time.time()
    data = _d(data)
    ctx = _d(data.get('context_window'))
    rl = resolve_rate_limits(data)
    five, seven = _d(rl.get('five_hour')), _d(rl.get('seven_day'))

    # Line 1 — context and both rate-limit windows
    ctx_pct = _num(ctx.get('used_percentage'))
    used = int(_num(ctx.get('total_input_tokens')) or 0)   # same basis as used_percentage (input side)
    size = int(_num(ctx.get('context_window_size')) or 0)
    detail = f' {fmt_tokens(used)}/{fmt_tokens(size)}' if used and size else ''
    p5, p7 = _num(five.get('used_percentage')), _num(seven.get('used_percentage'))
    line1 = SEP.join([
        f'CTX {make_bar(ctx_pct, 10)}{detail} {fmt_pct(ctx_pct)}',
        f'5h {make_bar(p5, 8)} {fmt_pct(p5)}{fmt_burn(burn_rate_tpm())}{fmt_reset(five.get("resets_at"))}',
        f'7d {make_bar(p7, 8)} {fmt_pct(p7)}{fmt_reset(seven.get("resets_at"))}',
    ])

    # Line 2 — who / where / how long
    name = str(resolve_model_name(data))
    ml = name.lower()
    mcol = MAGENTA if 'opus' in ml else CYAN if 'sonnet' in ml else YELLOW if 'haiku' in ml else WHITE
    parts = [f'{"" if ASCII else "🤖 "}{mcol}{BOLD}{name}{RESET}']

    if data.get('fast_mode') is True:
        parts.append(f'{MAGENTA}fast{RESET}')
    elif _d(data.get('thinking')).get('enabled') is True:
        parts.append(f'{CYAN}{_text(_d(data.get("effort")).get("level")) or "thinking"}{RESET}')

    agent = _text(_d(data.get('agent')).get('name'))
    if agent:
        parts.append(f'{YELLOW}agent:{agent}{RESET}')
    wt = _text(_d(data.get('worktree')).get('name'))
    if wt:
        parts.append(f'{YELLOW}worktree:{wt}{RESET}')

    ws = _d(data.get('workspace'))
    cwd = _text(ws.get('current_dir')) or _text(data.get('cwd')) or os.getcwd()
    g = git_segment(cwd)
    if g:
        parts.append(f'{CYAN}{g}{RESET}')

    cost = _d(data.get('cost'))
    added = int(_num(cost.get('total_lines_added')) or 0)
    removed = int(_num(cost.get('total_lines_removed')) or 0)
    if added or removed:
        parts.append(f'{GRAY}+{added}/-{removed}{RESET}')

    proj = _text(ws.get('project_dir')) or cwd
    parts.append(f'{WHITE}{os.path.basename(os.path.normpath(proj)) or proj}{RESET}')

    # Prompt cache: show the clock time it expires, not a countdown — the status line only
    # redraws on events (replies, /compact, …), not every second, so a countdown would freeze
    # between redraws; a clock time stays correct.
    pc = _d(data.get('prompt_cache'))
    if 'warm' in pc:
        exp = _epoch(pc.get('expires_at'))
        if pc.get('warm') is True and exp and exp > now:
            ccol = YELLOW if exp - now < 300 else GREEN   # under 5 minutes at the last redraw
            parts.append(f'{ccol}cache{ARROW}{time.strftime("%H:%M", time.localtime(exp))}{RESET}')
        else:
            parts.append(f'{GRAY}cache cold{RESET}')

    elapsed = fmt_duration((_num(cost.get('total_duration_ms')) or 0) / 1000)
    if elapsed:
        parts.append(f'{GRAY}{elapsed}{RESET}')
    c = _num(cost.get('total_cost_usd'))
    if SHOW_COST and c is not None:
        parts.append(f'{RED if c >= 10 else YELLOW if c >= 5 else GRAY}${c:.2f}{RESET}')

    return line1 + '\n' + '  '.join(parts)


def safe_render(data):
    """A status line must never go blank: on any unexpected input, fall back to a minimal one."""
    try:
        return render(data)
    except Exception as e:
        return f'CTX {make_bar(None, 10)} --\n{GRAY}statusline: {type(e).__name__}{RESET}'


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--update-usage':
        update_usage_cache()
        return
    if len(sys.argv) > 1 and sys.argv[1] == '--version':
        print(__version__)
        return
    out = safe_render(read_stdin())
    # Emit UTF-8 bytes directly: the console code page cannot encode block characters or emoji.
    # 'replace': a Windows path can contain a lone surrogate, which strict UTF-8 refuses to encode.
    stream = getattr(sys.stdout, 'buffer', None)
    if stream is not None:
        stream.write((out + '\n').encode('utf-8', 'replace'))
        stream.flush()


if __name__ == '__main__':
    main()
