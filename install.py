#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install / uninstall claude-code-statusline-windows.

    python install.py              install (or update) and point Claude Code at it
    python install.py --dry-run    show what would change, write nothing
    python install.py --uninstall  put your previous statusLine back and remove the files

What install does:
  1. copies statusline.py to %USERPROFILE%\\.claude\\statusline-windows\\statusline.py
  2. backs up settings.json (settings.json.bak-statusline-<timestamp>)
  3. remembers your previous "statusLine" value so --uninstall can put it back
  4. sets "statusLine" to run the script with pythonw.exe (absolute path, forward slashes)
Respects CLAUDE_CONFIG_DIR if you use a non-default Claude Code config folder.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(os.path.expanduser('~'), '.claude')
INSTALL_DIR = os.path.join(CLAUDE_DIR, 'statusline-windows')
# Same default as statusline.py. Only this default folder is ever deleted on uninstall; a folder you
# chose with CLAUDE_STATUSLINE_STATE_DIR is yours and is left alone.
DEFAULT_STATE_DIR = (os.path.join(os.environ['LOCALAPPDATA'], 'claude-code-statusline-windows')
                     if os.name == 'nt' and os.environ.get('LOCALAPPDATA') else None)
TARGET = os.path.join(INSTALL_DIR, 'statusline.py')
SETTINGS = os.path.join(CLAUDE_DIR, 'settings.json')
PREVIOUS = os.path.join(INSTALL_DIR, 'previous_statusline.json')


def fwd(path):
    """Forward slashes work in every shell Claude Code may use; bash eats backslashes as escapes."""
    return path.replace('\\', '/')


def find_pythonw():
    """pythonw.exe has no console, so the status line never opens a window of its own."""
    if os.name != 'nt':
        return sys.executable
    pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if os.path.exists(pyw):
        return pyw
    print('Warning: pythonw.exe not found next to this Python; falling back to "pythonw" on PATH.')
    return 'pythonw'


def short_path(path):
    """8.3 short form (C:/PROGRA~1/...) has no spaces, so it needs no quoting in any shell.
    Returns the path unchanged when 8.3 names are disabled or the path does not exist."""
    if os.name != 'nt' or ' ' not in path or not os.path.exists(path):
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
        return buf.value if 0 < n < len(buf) else path
    except Exception:
        return path


def git_bash_available():
    """Claude Code on Windows runs the status line through Git Bash when it is installed and
    through PowerShell otherwise; the two need different quoting for a program path with spaces."""
    p = os.environ.get('CLAUDE_CODE_GIT_BASH_PATH')
    if p and os.path.isfile(p):
        return True
    if os.environ.get('MSYSTEM'):          # we are running inside Git Bash right now
        return True
    # git.exe sits in Git\cmd (PowerShell PATH) or Git\mingw64\bin (Git Bash PATH):
    # walk up a few levels from it and look for Git\bin\bash.exe.
    git = shutil.which('git')
    if git:
        d = os.path.dirname(os.path.realpath(git))
        for _ in range(3):
            d = os.path.dirname(d)
            if os.path.isfile(os.path.join(d, 'bin', 'bash.exe')):
                return True
    for env in ('ProgramFiles', 'ProgramW6432', 'LOCALAPPDATA'):
        base = os.environ.get(env)
        for sub in (('Git',), ('Programs', 'Git')):
            if base and os.path.isfile(os.path.join(base, *sub, 'bin', 'bash.exe')):
                return True
    return False


def build_command():
    exe = fwd(short_path(find_pythonw()))
    script = fwd(short_path(TARGET) if os.path.exists(TARGET) else TARGET)
    if ' ' not in exe:
        return f'{exe} "{script}"'                      # works in Git Bash, PowerShell and cmd
    if git_bash_available():
        return f'"{exe}" "{script}"'
    print('Note: Python lives in a path with spaces and Git Bash was not found, so the command is\n'
          '      written for PowerShell. If you install Git for Windows later, run install again.')
    return f'& "{exe}" "{script}"'


def load_settings():
    """Returns (dict, existed, had_bom, indent). Refuses to touch a file it cannot parse."""
    if not os.path.exists(SETTINGS):
        return {}, False, False, 2
    with open(SETTINGS, 'rb') as f:
        raw = f.read()
    had_bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    if not text.strip():
        return {}, True, had_bom, 2
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f'settings.json is not valid JSON ({e}). Nothing was changed; fix it and run again.')
    if not isinstance(data, dict):
        sys.exit('settings.json does not contain a JSON object. Nothing was changed.')
    m = re.search(r'\n([ \t]+)"', text)     # indentation of the first key
    if not m:
        indent = 2
    else:
        indent = m.group(1) if '\t' in m.group(1) else len(m.group(1))
    return data, True, had_bom, indent


def save_settings(data, had_bom, indent):
    """Keep the original BOM and indentation so the file only changes where it has to."""
    tmp = SETTINGS + '.tmp'
    with open(tmp, 'w', encoding='utf-8-sig' if had_bom else 'utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
        f.write('\n')
    os.replace(tmp, SETTINGS)


def backup_settings():
    if os.path.exists(SETTINGS):
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        dst = f'{SETTINGS}.bak-statusline-{stamp}'
        shutil.copy2(SETTINGS, dst)
        return dst
    return None


def load_previous():
    try:
        with open(PREVIOUS, encoding='utf-8') as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def install(dry):
    settings, existed, had_bom, indent = load_settings()
    current = settings.get('statusLine')
    print(f'Claude config : {CLAUDE_DIR}')
    print(f'Copy          : statusline.py -> {TARGET}')
    if dry:
        new_value = {'type': 'command', 'command': build_command()}
        print(f'statusLine    : {json.dumps(current, ensure_ascii=False) if current else "(not set)"}')
        print(f'           -> : {json.dumps(new_value, ensure_ascii=False)}')
        print('Dry run: nothing written. (A real install may write paths in 8.3 short form, e.g.\n'
              '         PROGRA~1, once the script exists; that is the same location.)')
        return
    os.makedirs(INSTALL_DIR, exist_ok=True)
    shutil.copy2(os.path.join(HERE, 'statusline.py'), TARGET)
    new_value = {'type': 'command', 'command': build_command()}   # after copying: short path needs the file
    print(f'statusLine    : {json.dumps(current, ensure_ascii=False) if current else "(not set)"}')
    print(f'           -> : {json.dumps(new_value, ensure_ascii=False)}')
    prev = load_previous()
    if 'value' not in prev:   # keep the very first previous value; re-installs must not overwrite it
        prev = {'had_key': 'statusLine' in settings, 'value': current}
    prev['installed'] = new_value   # what we wrote, so uninstall can tell if you changed it since
    with open(PREVIOUS, 'w', encoding='utf-8') as f:
        json.dump(prev, f, ensure_ascii=False, indent=2)
    bak = backup_settings()
    settings['statusLine'] = new_value
    save_settings(settings, had_bom, indent)
    if bak:
        print(f'Backup        : {bak}')
    print('Done. Restart Claude Code to load the new status line.')


def uninstall(dry):
    settings, existed, had_bom, indent = load_settings()
    prev = load_previous()
    current = settings.get('statusLine')
    # Compare only the command: extra keys such as refreshInterval do not make it someone else's.
    installed_cmd = (prev.get('installed') or {}).get('command')
    current_cmd = current.get('command') if isinstance(current, dict) else None
    ours = bool(installed_cmd) and current_cmd == installed_cmd
    # Not ours, but still pointing into our folder: deleting the folder would leave a broken setting.
    # The folder may appear in its long form or as an 8.3 short path (STATUS~1) — check both.
    markers = {'statusline-windows', fwd(short_path(INSTALL_DIR)).lower(), fwd(INSTALL_DIR).lower()}
    still_uses_us = (not ours and isinstance(current_cmd, str)
                     and any(m and m in fwd(current_cmd).lower() for m in markers))
    restore = prev.get('value') if prev.get('had_key') else None
    print(f'statusLine    : {json.dumps(current, ensure_ascii=False)}')
    if ours:
        print(f'           -> : {json.dumps(restore, ensure_ascii=False) if restore else "(removed)"}')
    else:
        print('           -> : (left as is: it is no longer the value this installer wrote)')
    print(f'Remove folder : {INSTALL_DIR}')
    if dry:
        print('Dry run: nothing written.')
        return
    if existed and ours:
        bak = backup_settings()
        if restore is not None:
            settings['statusLine'] = restore
        else:
            settings.pop('statusLine', None)
        save_settings(settings, had_bom, indent)
        print(f'Backup        : {bak}')
    if still_uses_us:
        print('Kept the folder: your statusLine still runs a script inside it. Change statusLine first,\n'
              'then run --uninstall again to remove the files.')
        return
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    if DEFAULT_STATE_DIR and not os.environ.get('CLAUDE_STATUSLINE_STATE_DIR'):
        shutil.rmtree(DEFAULT_STATE_DIR, ignore_errors=True)
        print(f'Removed cache : {DEFAULT_STATE_DIR}')
    print('Uninstalled. Restart Claude Code.')


def main():
    # allow_abbrev=False: a misspelled option is an error, never silently matched to another one
    ap = argparse.ArgumentParser(description='Install or remove claude-code-statusline-windows.',
                                 allow_abbrev=False)
    ap.add_argument('--dry-run', action='store_true', help='show what would change, write nothing')
    ap.add_argument('--uninstall', action='store_true', help='restore the previous statusLine and remove the files')
    args = ap.parse_args()          # unknown or misspelled options exit here, before anything is written
    (uninstall if args.uninstall else install)(args.dry_run)


if __name__ == '__main__':
    main()
