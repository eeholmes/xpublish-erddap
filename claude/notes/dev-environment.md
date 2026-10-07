# Development environment on EH's JupyterHub

## Packages change whenever the server restarts

Installs from an earlier session may be gone or at different versions. On
2026-09-16 one restart put erddapy back to 3.1.0, removed `pre-commit`,
upgraded ruff to 0.15.1 and logged `gh` out. A later one removed `fastapi`,
so `xpublish_erddap` would not even import.

Check at the start of a session:

```bash
python -c "import erddapy; print(erddapy.__version__)"   # CI uses 3.3.1
python -c "import xpublish_erddap, xpublish"              # editable install still there?
gh auth status                                            # if logged out: `! gh auth login`
```

**Preferred (EH, 2026-10-05): a lean venv instead of the notebook env**, which
hides missing dependencies. Python 3.12, because icechunk 2.x needs it:

```bash
/srv/conda/bin/python3.12 -m venv ~/venvs/xpe
~/venvs/xpe/bin/pip install -e . -r requirements-dev.txt -r deploy/requirements.txt
PATH=~/venvs/xpe/bin:$PATH python -m pytest -q   # PATH matters on branches older than #20
```

Fix for the notebook env, if you must use it:

```bash
pip install -U erddapy && pip install -e . && pip install -r requirements-dev.txt
```

pip's warning that `ioos-metrics` needs `bs4` is unrelated; that package was
on the hub already.

**The erddapy version matters most.** erddapy >= 3.2 finds datasets through
`.ncml`; 3.1 uses DDS + csvp. A local pass with 3.1 does not test what CI and
most users run (#10).

## Session gotchas (2026-10-07)

- **A stray `tests/server.py` hangs the test suite.** The live-server tests
  start their own server on port 9000; one left running by hand (for an R
  check, say) makes them hang until the tool times out. Stop it first:
  `pgrep -af server.py`.
- **Do not `pkill -f <pattern>` from a Bash tool call** when the pattern is
  in the command itself: it matches the calling shell and kills the call
  (exit 144). Kill by PID from `pgrep`.
- **`curl -g`** for ERDDAP URLs with `[...]`: without it curl treats the
  brackets as its own globbing and sends nothing.

## Other limits of the hub

- **Python 3.11.** CI tests 3.12–3.14; the package still allows 3.11.
- **No Docker:** no socket, and sudo is blocked ("no new privileges"). This is
  why #1 compared against live public ERDDAP servers instead of a local one.
- **Ruff:** the hub's ruff is newer than the 0.8.6 pinned in
  `.pre-commit-config.yaml` and flags findings in files that pass the pinned
  version. That is version drift; use `pre-commit run`.
- **`check-manifest`** fails here on git's "dubious ownership" of `/tmp`; CI
  does not run it.
- A separate pinned environment is probably the real fix. EH deferred it.

## Running the R tests locally

R has rerddap, rerddapXtracto, httr and ncdf4 installed.

```bash
python tests/server.py &          # serves on :9000, including the store mount
Rscript tests/test_rerddap.R
Rscript tests/test_tutorials.R
```

Stop the server by its PID
(`ps -eo pid,args | grep "[p]ython tests/server.py"`). `pkill -f` also matches
the calling shell and exits with 144.

## Checking what a real ERDDAP does

oceanwatch.pifsc.noaa.gov runs ERDDAP 2.22; erddap.ioos.us runs 2.31. Use
`curl -g`, because curl otherwise globs `[` and `]`. oceanwatch's proxy turns
ERDDAP's query errors into a bare 500 HTML page; erddap.ioos.us shows the
real error.
