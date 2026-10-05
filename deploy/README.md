# Flux-like test server

A small xpublish server that serves public Icechunk stores through stock
xpublish-opendap and xpublish-erddap, the way Earthmover Flux serves Arraylake
stores. Used to test this package on a real deployment (issue #17).

| file | what it is |
|---|---|
| `server.py` | the server: a dataset-provider plugin plus the OPeNDAP and ERDDAP plugins |
| `requirements.txt` | what the server needs on top of the package |
| `check_clients.py` | erddapy checks against a running server, including a comparison with a direct read of each store |
| `check_rerddap.R` | the same idea from R with rerddap |

## Run it locally

Needs Python 3.12 or newer (icechunk 2.x does), and an Arraylake login for the
CEFI store (`arraylake auth login`; the repo is public to any account).

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e . -r requirements-dev.txt -r deploy/requirements.txt
python deploy/server.py &                     # http://127.0.0.1:9100
python deploy/check_clients.py http://127.0.0.1:9100
Rscript deploy/check_rerddap.R http://127.0.0.1:9100
```

ERDDAP clients point at `http://127.0.0.1:9100/erddap`. Datasets:
`cefi_nep_hindcast_daily` (Arraylake) and `gobai_o2_monthly` (Source Cooperative S3).

The AWS deployment recipe will be added here (#17).
