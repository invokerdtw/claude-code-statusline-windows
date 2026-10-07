# Installing with an AI assistant

If you are an AI coding assistant (Claude Code, Codex, …) asked to install this status line,
follow these steps exactly. Do not edit `settings.json` by hand; `install.py` backs it up first.

1. Confirm the platform is Windows and Python 3.8+ is available: `python --version`.
2. Clone the repository to a temporary folder:
   `git clone https://github.com/invokerdtw/claude-code-statusline-windows.git`
3. Preview the change and show it to the user: `python install.py --dry-run`
4. Install: `python install.py`
5. Verify the installed command really runs. Copy the `command` value that install printed and run it
   with sample input, for example in Git Bash:
   `echo '{"context_window":{"used_percentage":12}}' | <command>`
   Two lines starting with `CTX` and the model name must appear.
6. Tell the user to restart Claude Code. The status line appears after the first reply.

To remove it: `python install.py --uninstall` (restores the previous `statusLine` value).
