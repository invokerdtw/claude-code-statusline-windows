# -*- coding: utf-8 -*-
"""Tests for statusline.py.  Run:  python -m unittest discover tests"""
import atexit
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'statusline.py')

# Isolate every test run from the real ~/.claude before the module reads its settings.
TMP = tempfile.mkdtemp(prefix='slw-test-')
atexit.register(shutil.rmtree, TMP, True)
os.environ['CLAUDE_CONFIG_DIR'] = os.path.join(TMP, 'claude')
os.environ['CLAUDE_STATUSLINE_STATE_DIR'] = os.path.join(TMP, 'state')
os.makedirs(os.environ['CLAUDE_CONFIG_DIR'], exist_ok=True)
sys.path.insert(0, ROOT)
import statusline as sl  # noqa: E402


def run_script(payload_bytes, extra_env=None):
    env = dict(os.environ, **(extra_env or {}))
    # Claude Code does not set these; with them present the encoding tests would pass for the wrong reason.
    for k in ('PYTHONIOENCODING', 'PYTHONUTF8'):
        env.pop(k, None)
    return subprocess.run([sys.executable, SCRIPT], input=payload_bytes, capture_output=True, env=env)


def strip_ansi(s):
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


class ModelName(unittest.TestCase):
    def test_known_patterns(self):
        cases = {
            'claude-opus-5-5': 'Opus 5.5',
            'claude-sonnet-4-6': 'Sonnet 4.6',
            'claude-haiku-4-5-20251001': 'Haiku 4.5',
            'claude-opus-5': 'Opus 5',
            'claude-opus-5-20260101': 'Opus 5',
        }
        for mid, want in cases.items():
            self.assertEqual(sl.display_name_from_id(mid), want, mid)

    def test_unknown_id_is_shown_as_is(self):
        self.assertEqual(sl.display_name_from_id('some-other-model'), 'some-other-model')

    def _transcript(self, name, *models):
        t = os.path.join(TMP, name)
        with open(t, 'w', encoding='utf-8') as f:
            for m in models:
                f.write(json.dumps({'message': {'model': m}}) + '\n')
        return t

    def test_stdin_lags_transcript_moves_on(self):
        # /model to Opus; the next reply is Opus, but stdin still reports Sonnet
        t = self._transcript('lag.jsonl', 'claude-sonnet-4-6')
        data = {'session_id': 'lag', 'model': {'id': 'claude-sonnet-4-6', 'display_name': 'Sonnet 4.6'},
                'transcript_path': t}
        self.assertEqual(sl.resolve_model_name(data), 'Sonnet 4.6')
        self._transcript('lag.jsonl', 'claude-sonnet-4-6', 'claude-opus-5-5')
        self.assertEqual(sl.resolve_model_name(data), 'Opus 5.5')

    def test_stdin_updates_first_transcript_still_old(self):
        # stdin already says Opus, but no Opus reply has been written yet: must not fall back to Sonnet
        t = self._transcript('first.jsonl', 'claude-sonnet-4-6')
        old = {'session_id': 'first', 'model': {'id': 'claude-sonnet-4-6', 'display_name': 'Sonnet 4.6'},
               'transcript_path': t}
        new = dict(old, model={'id': 'claude-opus-5-5', 'display_name': 'Opus 5.5'})
        sl.resolve_model_name(old)
        self.assertEqual(sl.resolve_model_name(new), 'Opus 5.5')
        self.assertEqual(sl.resolve_model_name(new), 'Opus 5.5')   # still Opus on the next redraw


class Formatting(unittest.TestCase):
    def test_float_noise_is_rounded(self):
        self.assertIn('7%', sl.fmt_pct(7.000000000000001))
        self.assertNotIn('0000', sl.fmt_pct(7.000000000000001))

    def test_bar_colours_by_cell(self):
        full = sl.make_bar(100, 10)
        self.assertIn(sl.GREEN, full)
        self.assertIn(sl.YELLOW, full)
        self.assertIn(sl.RED, full)
        half = sl.make_bar(50, 10)
        self.assertNotIn(sl.YELLOW, half)
        self.assertNotIn(sl.RED, half)
        self.assertEqual(strip_ansi(sl.make_bar(None, 8)), sl.EMPTY * 8)

    def test_durations(self):
        self.assertEqual(sl.fmt_duration(90), '1m')
        self.assertEqual(sl.fmt_duration(3700), '1h01m')
        self.assertEqual(sl.fmt_duration(5 * 86400 + 3 * 3600), '5d3h')
        self.assertEqual(sl.fmt_duration(-5), '')


class QuotaCache(unittest.TestCase):
    def _write_credentials(self, plan):
        with open(os.path.join(os.environ['CLAUDE_CONFIG_DIR'], '.credentials.json'), 'w', encoding='utf-8') as f:
            json.dump({'claudeAiOauth': {'subscriptionType': plan, 'accessToken': 'secret'}}, f)

    def _write_account(self, uuid):
        with open(os.path.join(os.environ['CLAUDE_CONFIG_DIR'], '.claude.json'), 'w', encoding='utf-8') as f:
            json.dump({'oauthAccount': {'accountUuid': uuid}}, f)

    def test_last_values_shown_until_stdin_has_them(self):
        self._write_credentials('max')
        rl = {'five_hour': {'used_percentage': 40, 'resets_at': time.time() + 3600}}
        sl.resolve_rate_limits({'rate_limits': rl})
        self.assertEqual(sl.resolve_rate_limits({}), rl)

    def test_window_that_already_reset_is_dropped(self):
        self._write_credentials('max')
        sl.resolve_rate_limits({'rate_limits': {
            'five_hour': {'used_percentage': 91, 'resets_at': time.time() - 7200},
            'seven_day': {'used_percentage': 40, 'resets_at': time.time() + 86400}}})
        got = sl.resolve_rate_limits({})
        self.assertNotIn('five_hour', got)
        self.assertEqual(got['seven_day']['used_percentage'], 40)

    def test_same_plan_other_account_is_dropped(self):
        self._write_credentials('max')
        self._write_account('uuid-A')
        sl.resolve_rate_limits({'rate_limits': {'five_hour': {'used_percentage': 97, 'resets_at': time.time() + 3600}}})
        self._write_account('uuid-B')
        try:
            self.assertEqual(sl.resolve_rate_limits({}), {})
        finally:
            os.remove(os.path.join(os.environ['CLAUDE_CONFIG_DIR'], '.claude.json'))

    def test_cache_from_other_account_is_dropped(self):
        self._write_credentials('max')
        sl.resolve_rate_limits({'rate_limits': {'five_hour': {'used_percentage': 97}}})
        self._write_credentials('pro')      # /login to another plan
        self.assertEqual(sl.resolve_rate_limits({}), {})

    def test_token_is_never_stored(self):
        self._write_credentials('max')
        sl.resolve_rate_limits({'rate_limits': {'five_hour': {'used_percentage': 1}}})
        with open(sl.QUOTA_CACHE, encoding='utf-8') as f:
            self.assertNotIn('secret', f.read())


class Git(unittest.TestCase):
    def test_branch_from_head_and_worktree_file(self):
        repo = os.path.join(TMP, 'repo')
        os.makedirs(os.path.join(repo, '.git'), exist_ok=True)
        with open(os.path.join(repo, '.git', 'HEAD'), 'w') as f:
            f.write('ref: refs/heads/feature/x\n')
        root, gitdir = sl.find_git_dir(os.path.join(repo))
        self.assertEqual(sl.branch_from_head(gitdir), 'feature/x')
        wt = os.path.join(TMP, 'wt')
        os.makedirs(wt, exist_ok=True)
        with open(os.path.join(wt, '.git'), 'w') as f:
            f.write('gitdir: ' + os.path.join(repo, '.git'))
        self.assertEqual(os.path.normcase(sl.find_git_dir(wt)[1]), os.path.normcase(os.path.join(repo, '.git')))

    def test_no_git_prefix_is_respected(self):
        sl.NO_GIT_PATHS[:] = [TMP]
        try:
            self.assertTrue(sl.is_cloud_path(os.path.join(TMP, 'anything')))
        finally:
            sl.NO_GIT_PATHS[:] = []

    def test_no_git_matches_whole_folders_only(self):
        work = os.path.join(TMP, 'Work')
        sl.NO_GIT_PATHS[:] = [work]
        try:
            self.assertTrue(sl.is_cloud_path(work))
            self.assertTrue(sl.is_cloud_path(os.path.join(work, 'repo')))
            self.assertFalse(sl.is_cloud_path(os.path.join(TMP, 'Workspace')))
        finally:
            sl.NO_GIT_PATHS[:] = []

    def test_git_in_cloud_does_not_override_no_git(self):
        sl.NO_GIT_PATHS[:] = [TMP]
        sl.GIT_IN_CLOUD = True
        try:
            self.assertTrue(sl.is_cloud_path(os.path.join(TMP, 'x')))
        finally:
            sl.NO_GIT_PATHS[:] = []
            sl.GIT_IN_CLOUD = False


class EndToEnd(unittest.TestCase):
    def test_non_ascii_path_survives_stdin(self):
        proj = os.path.join(TMP, '中文專案')
        payload = json.dumps({'workspace': {'project_dir': proj, 'current_dir': proj}}, ensure_ascii=False)
        r = run_script(payload.encode('utf-8'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('中文專案', r.stdout.decode('utf-8'))

    def test_empty_stdin_still_renders_two_lines(self):
        r = run_script(b'')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(r.stdout.decode('utf-8').strip().splitlines()), 2)

    def test_ascii_mode_has_no_block_characters(self):
        payload = json.dumps({'context_window': {'used_percentage': 50}}).encode()
        payload = json.dumps({'context_window': {'used_percentage': 50},
                              'prompt_cache': {'warm': True, 'expires_at': int(time.time()) + 900}}).encode()
        out = strip_ansi(run_script(payload, {'CLAUDE_STATUSLINE_ASCII': '1'}).stdout.decode('utf-8'))
        self.assertTrue(out.isascii(), [c for c in out if not c.isascii()])

    def test_prompt_cache_shows_clock_time(self):
        exp = int(time.time()) + 1800
        payload = json.dumps({'prompt_cache': {'warm': True, 'expires_at': exp}}).encode()
        out = strip_ansi(run_script(payload).stdout.decode('utf-8'))
        self.assertIn('cache→' + time.strftime('%H:%M', time.localtime(exp)), out)


class Robustness(unittest.TestCase):
    """Malformed input must never blank the status line."""

    def _two_lines(self, payload_bytes):
        r = run_script(payload_bytes)
        out = r.stdout.decode('utf-8', 'replace')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(out.strip().splitlines()), 2, out)
        return strip_ansi(out)

    def test_non_object_json(self):
        for raw in (b'[]', b'"text"', b'null', b'42', b'not json'):
            self._two_lines(raw)

    def test_wrong_types(self):
        self._two_lines(json.dumps({
            'context_window': {'used_percentage': '50', 'context_window_size': None},
            'rate_limits': {'five_hour': {'used_percentage': 'high', 'resets_at': '2026-10-08T00:00:00Z'}},
            'prompt_cache': {'warm': True, 'expires_at': 'soon'},
            'model': 'opus', 'workspace': [], 'cost': {'total_cost_usd': 'free'},
        }).encode())

    def test_infinity_and_nan_are_ignored(self):
        out = self._two_lines(b'{"context_window": {"used_percentage": Infinity, "total_input_tokens": NaN},'
                              b' "rate_limits": {"five_hour": {"used_percentage": NaN, "resets_at": Infinity}}}')
        self.assertNotIn('statusline:', out)     # handled normally, not by the last-resort fallback

    def test_milliseconds_timestamp(self):
        exp_ms = int((time.time() + 1800) * 1000)
        out = self._two_lines(json.dumps({'prompt_cache': {'warm': True, 'expires_at': exp_ms}}).encode())
        self.assertIn('cache→', out)

    def test_lone_surrogate_in_path(self):
        self._two_lines(b'{"workspace": {"project_dir": "C:/x/\\ud800bad"}}')

    def test_cold_cache_with_null_expiry(self):
        out = self._two_lines(json.dumps({'prompt_cache': {'warm': False, 'expires_at': None}}).encode())
        self.assertIn('cache cold', out)

    def test_last_resort_fallback(self):
        # anything render() did not foresee must still produce two lines, not a blank status line
        real = sl.render
        sl.render = lambda data, now=None: 1 / 0
        try:
            out = sl.safe_render({})
        finally:
            sl.render = real
        self.assertEqual(len(out.splitlines()), 2)
        self.assertIn('ZeroDivisionError', out)

    def test_under_one_minute(self):
        self.assertEqual(sl.fmt_duration(30), '<1m')


class BurnRate(unittest.TestCase):
    def test_failed_refresh_is_not_retried_on_every_redraw(self):
        real_run = sl.subprocess.run
        sl.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError('npx'))
        try:
            sl.update_usage_cache()
        finally:
            sl.subprocess.run = real_run
        cache = sl._load_json(sl.USAGE_CACHE)
        self.assertGreater(cache.get('updated_at', 0), time.time() - 60)
        self.assertEqual(cache.get('error'), 'FileNotFoundError')
        spawned = []
        real_spawn, sl._spawn_usage_update = sl._spawn_usage_update, lambda: spawned.append(1)
        sl.BURN_RATE = True
        try:
            for _ in range(5):
                sl.burn_rate_tpm()
        finally:
            sl._spawn_usage_update, sl.BURN_RATE = real_spawn, False
        self.assertEqual(spawned, [])

    def test_version_is_pinned(self):
        self.assertNotIn('latest', sl.CCUSAGE)


class Installer(unittest.TestCase):
    INSTALL = os.path.join(ROOT, 'install.py')

    def setUp(self):
        self.cfg = tempfile.mkdtemp(prefix='slw-inst-', dir=TMP)
        self.settings = os.path.join(self.cfg, 'settings.json')

    def run_install(self, *args):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg)
        return subprocess.run([sys.executable, self.INSTALL, *args], capture_output=True, env=env)

    def write(self, raw_bytes):
        with open(self.settings, 'wb') as f:
            f.write(raw_bytes)

    def read(self):
        with open(self.settings, 'rb') as f:
            return f.read()

    def test_help_and_typos_write_nothing(self):
        original = b'{\n  "model": "opus"\n}\n'
        self.write(original)
        for args in (['--help'], ['--uninstal'], ['install']):
            r = self.run_install(*args)
            self.assertEqual(self.read(), original, args)
            self.assertFalse(os.path.exists(os.path.join(self.cfg, 'statusline-windows')), args)
        self.assertEqual(self.run_install('--help').returncode, 0)
        self.assertNotEqual(self.run_install('--uninstal').returncode, 0)

    def test_bom_and_indent_are_kept(self):
        self.write(b'\xef\xbb\xbf{\n    "model": "opus"\n}\n')
        self.assertEqual(self.run_install().returncode, 0)
        raw = self.read()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\n    "model"', raw)

    def test_uninstall_keeps_a_statusline_you_changed_later(self):
        self.write(json.dumps({'statusLine': {'type': 'command', 'command': 'old'}}).encode())
        self.run_install()
        data = json.loads(self.read().decode('utf-8-sig'))
        data['statusLine'] = {'type': 'command', 'command': 'my-new-choice'}
        self.write(json.dumps(data).encode())
        self.run_install('--uninstall')
        self.assertEqual(json.loads(self.read())['statusLine']['command'], 'my-new-choice')

    def test_uninstall_ignores_extra_keys_like_refresh_interval(self):
        self.write(json.dumps({'statusLine': {'type': 'command', 'command': 'old'}}).encode())
        self.run_install()
        data = json.loads(self.read().decode('utf-8-sig'))
        data['statusLine']['refreshInterval'] = 5          # recommended by the official docs
        self.write(json.dumps(data).encode())
        self.run_install('--uninstall')
        self.assertEqual(json.loads(self.read())['statusLine']['command'], 'old')

    def test_uninstall_keeps_folder_still_in_use(self):
        self.write(b'{}')
        self.run_install()
        data = json.loads(self.read().decode('utf-8-sig'))
        data['statusLine']['command'] += ' --my-flag'      # hand-edited, but still runs our script
        self.write(json.dumps(data).encode())
        self.run_install('--uninstall')
        self.assertTrue(os.path.exists(os.path.join(self.cfg, 'statusline-windows', 'statusline.py')))

    def test_uninstall_keeps_folder_in_use_via_short_path(self):
        # config folder with a space ⇒ the command is written with 8.3 names (STATUS~1), no 'statusline-windows'
        self.cfg = tempfile.mkdtemp(prefix='slw inst ', dir=TMP)
        self.settings = os.path.join(self.cfg, 'settings.json')
        self.write(b'{}')
        self.run_install()
        data = json.loads(self.read().decode('utf-8-sig'))
        data['statusLine']['command'] = 'CLAUDE_STATUSLINE_ASCII=1 ' + data['statusLine']['command']
        self.write(json.dumps(data).encode())
        self.run_install('--uninstall')
        self.assertTrue(os.path.exists(os.path.join(self.cfg, 'statusline-windows', 'statusline.py')),
                        data['statusLine']['command'])

    def test_uninstall_restores_when_untouched(self):
        self.write(json.dumps({'statusLine': {'type': 'command', 'command': 'old'}}).encode())
        self.run_install()
        self.run_install()                       # a second install must not forget "old"
        self.run_install('--uninstall')
        self.assertEqual(json.loads(self.read())['statusLine']['command'], 'old')

    def test_non_object_settings_is_refused(self):
        self.write(b'[]')
        r = self.run_install()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.read(), b'[]')


class CommandQuoting(unittest.TestCase):
    """The command must parse in Git Bash and in PowerShell (Claude Code uses PowerShell
    when Git Bash is missing)."""

    def setUp(self):
        sys.path.insert(0, ROOT)
        import install
        self.inst = install
        self.saved = (install.find_pythonw, install.short_path, install.git_bash_available)
        install.short_path = lambda p: p          # simulate 8.3 names being disabled

    def tearDown(self):
        self.inst.find_pythonw, self.inst.short_path, self.inst.git_bash_available = self.saved

    def test_spaces_with_git_bash(self):
        self.inst.find_pythonw = lambda: 'C:\\Program Files\\Python\\pythonw.exe'
        self.inst.git_bash_available = lambda: True
        self.assertTrue(self.inst.build_command().startswith('"C:/Program Files/Python/pythonw.exe" '))

    def test_spaces_without_git_bash_uses_powershell_call_operator(self):
        self.inst.find_pythonw = lambda: 'C:\\Program Files\\Python\\pythonw.exe'
        self.inst.git_bash_available = lambda: False
        with contextlib.redirect_stdout(io.StringIO()):     # keep the expected notice out of test output
            cmd = self.inst.build_command()
        self.assertTrue(cmd.startswith('& "C:/Program Files/Python/pythonw.exe" '))

    def test_git_bash_found_from_inside_git_bash(self):
        # Inside Git Bash, git resolves to Git\mingw64\bin\git.exe (two levels below Git\bin\bash.exe)
        self.inst.git_bash_available = self.saved[2]
        root = tempfile.mkdtemp(prefix='fakegit-', dir=TMP)
        for rel in (('mingw64', 'bin', 'git.exe'), ('bin', 'bash.exe')):
            os.makedirs(os.path.join(root, *rel[:-1]), exist_ok=True)
            open(os.path.join(root, *rel), 'w').close()
        saved_env = {k: os.environ.pop(k, None) for k in ('MSYSTEM', 'CLAUDE_CODE_GIT_BASH_PATH',
                                                          'ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA')}
        real_which = self.inst.shutil.which
        self.inst.shutil.which = lambda name: os.path.join(root, 'mingw64', 'bin', 'git.exe')
        try:
            self.assertTrue(self.inst.git_bash_available())
            self.inst.shutil.which = lambda name: None
            self.assertFalse(self.inst.git_bash_available())
            os.environ['MSYSTEM'] = 'MINGW64'
            self.assertTrue(self.inst.git_bash_available())
        finally:
            self.inst.shutil.which = real_which
            os.environ.pop('MSYSTEM', None)
            for k, v in saved_env.items():
                if v is not None:
                    os.environ[k] = v

    def test_no_spaces_is_unquoted(self):
        self.inst.find_pythonw = lambda: 'C:\\Python312\\pythonw.exe'
        self.assertTrue(self.inst.build_command().startswith('C:/Python312/pythonw.exe "'))


if __name__ == '__main__':
    unittest.main()
