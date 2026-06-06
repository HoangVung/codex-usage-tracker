# Install Guide

## Recommended Install

```bash
brew install pipx
pipx ensurepath
pipx install "git+https://github.com/douglasmonsky/codex-usage-tracker.git"
codex-usage-tracker setup
codex-usage-tracker serve-dashboard --open
```

`setup` installs or refreshes the package-owned plugin wrapper, initializes local config templates when needed, refreshes the aggregate index, runs `doctor`, prints a success/failure summary, and tells you whether Codex needs a restart for plugin discovery.

Restart Codex after plugin registration if you want Codex to discover the MCP tools in a fresh session. The localhost dashboard can run immediately.

## Upgrade

```bash
pipx upgrade codex-usage-tracker
codex-usage-tracker setup
```

When installed from GitHub through `pipx`, rerun the GitHub install with `--force`:

```bash
pipx install --force "git+https://github.com/douglasmonsky/codex-usage-tracker.git"
codex-usage-tracker setup
```

## Codex-Assisted Install

Open a Codex session on your machine and paste:

```text
Install and configure Codex Usage Tracker from https://github.com/douglasmonsky/codex-usage-tracker.
Use pipx if it is available. If pipx is missing, install it with Homebrew or use a local virtual environment.
After installation, run codex-usage-tracker setup and serve-dashboard --open.
Verify the dashboard opens locally and tell me the dashboard URL plus whether I need to restart Codex for plugin discovery.
```

Codex should run roughly the same shell commands as the recommended install. This path is useful if you want Codex to verify the dashboard URL and plugin discovery state for you.

## Source Checkout

```bash
git clone https://github.com/douglasmonsky/codex-usage-tracker.git
cd codex-usage-tracker
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
codex-usage-tracker install-plugin --python .venv/bin/python
```

Use the source checkout when developing the project or testing a branch locally.

## Plugin Registration

After installing the Python package, register the local Codex plugin:

```bash
codex-usage-tracker install-plugin
```

For a source checkout that should use the repo-local virtual environment:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python
```

If you previously installed the older source-checkout symlink, replace it once:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python --force
```

`install-plugin` creates `~/plugins/codex-usage-tracker`, writes a package-owned `.mcp.json` that points at the installed Python executable, and updates `~/.agents/plugins/marketplace.json`.

## Local Dashboard

Generate a static dashboard:

```bash
codex-usage-tracker dashboard --open
codex-usage-tracker open-dashboard
```

Serve the dashboard with live aggregate refresh and lazy context loading:

```bash
codex-usage-tracker serve-dashboard --open
codex-usage-tracker serve-dashboard --no-context-api --open
```

The server binds to localhost, requires a per-server token for refresh/context endpoints, and rejects non-loopback `Host` or cross-origin `Origin` headers.

## Setup Checks

```bash
codex-usage-tracker doctor
codex-usage-tracker doctor --suggest-repair
codex-usage-tracker --version
python -m codex_usage_tracker --version
```

`doctor` is read-only. `doctor --suggest-repair` explains likely follow-up commands without making changes.

## Lifecycle Commands

```bash
codex-usage-tracker setup
codex-usage-tracker upgrade-plugin
codex-usage-tracker uninstall-plugin
codex-usage-tracker reset-db --yes
codex-usage-tracker support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

`support-bundle` writes package, Python, OS, doctor, database schema, parser diagnostics, pricing status, and allowance status. It does not include raw logs, prompts, assistant messages, tool output, or context text.
