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

## Try the public test server

Until **2026-11-13**, a copy runs at **https://18-119-42-78.sslip.io**. Point
your own ERDDAP client code at its `/erddap` root; nothing else needs to change.

```python
from erddapy import ERDDAP
e = ERDDAP(server="https://18-119-42-78.sslip.io/erddap", protocol="griddap", response="nc")
e.dataset_id = "gobai_o2_monthly"
e.griddap_initialize()
e.constraints.update({"time>=": "2020-01-15", "time<=": "2020-03-15",
                      "pres>=": 10, "pres<=": 20,
                      "lat>=": 0, "lat<=": 5, "lon>=": 180, "lon<=": 185})
e.variables = ["oxy"]
ds = e.to_xarray()
```

```r
library(rerddap)
url <- "https://18-119-42-78.sslip.io/erddap/"
info("cefi_nep_hindcast_daily", url = url)
griddap("cefi_nep_hindcast_daily", url = url,
        time = c("2024-07-01", "2024-07-03"), lat = c(45, 46), lon = c(230, 231),
        fields = "tos")
```

Hand-built griddap URLs work too, for example
`https://18-119-42-78.sslip.io/erddap/griddap/gobai_o2_monthly.csv?oxy[(2020-01-15)][(10)][(0):(2)][(180):(182)]`.

Things to know:

- **Datasets:** `cefi_nep_hindcast_daily` (NOAA CEFI NE Pacific hindcast,
  virtual Icechunk on Arraylake) and `gobai_o2_monthly` (GOBAI-O2, Icechunk on
  Source Cooperative). GOBAI longitudes run 20.5 to 379.5, as in the source.
- **Requests over 500 MB** are refused with ERDDAP's "Your query produced too
  much data" error. Ask for a smaller subset.
- **The OPeNDAP endpoints** (`/datasets/{id}/opendap`) are stock
  xpublish-opendap, which returns **wrong values for strided requests**
  (`lat[0:1:4]` gives 1 value, not 5). They are here to show they run, not for
  real use.
- **Known gaps:** `searchFor=all` returns 404 (#19), and there is no `.dods` on
  the ERDDAP side (#2).

## Deploy to AWS

`aws/stack.yaml` is a CloudFormation stack: one t4g.medium (ARM) running the
server behind [Caddy](https://caddyserver.com), which gets an HTTPS
certificate for an `sslip.io` name made from the instance's Elastic IP. There
is no SSH; use SSM Session Manager. The Arraylake key is kept in an SSM
SecureString parameter and read into memory when the service starts.

```bash
deploy/aws/deploy.sh      # create or update; prints the URL
deploy/aws/teardown.sh    # delete the stack and the key parameter
```

Both use the `greenfield` profile and us-east-2 unless `DEPLOY_PROFILE` and
`DEPLOY_REGION` say otherwise. They deliberately ignore `AWS_REGION`, which
JupyterHub sets for its own account. `GIT_REF` picks the branch the instance
runs (default `main`), and `MAX_RESPONSE_MB` sets the size limit
(default 500). The instance clones the repository on its first boot only, so
push before creating the stack.

To change the code a running instance serves, do it on the instance; running
`deploy.sh` again with another `GIT_REF` only stops and starts the instance,
and does not check anything out. In a Session Manager shell (`aws ssm
start-session --profile greenfield --region us-east-2 --target <InstanceId>`):

```bash
cd /opt/xpublish-erddap
sudo -u xpe git fetch origin && sudo -u xpe git checkout main && sudo -u xpe git pull
sudo systemctl restart xpublish-erddap
```

Run `git` as `xpe`, which owns the checkout; as root it refuses with "dubious
ownership". The live server was created from the `aws-test-server` branch and
switched to `main` this way after #20 merged, so the stack's `GitRef`
parameter still says `aws-test-server`. That is only the first-boot value.

Logs: `journalctl -u xpublish-erddap` and `journalctl -u caddy`.
