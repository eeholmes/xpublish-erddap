# Running xpublish-erddap in a host such as Earthmover Flux

This note is for teams that serve xpublish plugins inside their own service,
and Earthmover Flux in particular. The plugin's job is to let people's existing
ERDDAP client code (erddapy, rerddap, hand-built griddap URLs) keep working when
data moves to Zarr/Icechunk, with only the server URL changed.

We built and tested against **a stand-in for Flux's routing**, not Flux itself.
Where we had to guess how a host works, we made a choice and listed it below,
with what to change if yours differs. Discussion: issue
[#18](https://github.com/eeholmes/xpublish-erddap/issues/18).

## What the plugin provides

`ErddapPlugin` registers two xpublish routers that serve the same ERDDAP API
(`/version`, `/griddap/index.*`, `/info/...`, `/search/...`, `/tabledap/index.*`,
`/griddap/{datasetID}.{fileType}`):

| Router | Where | Catalog |
|---|---|---|
| `dataset_router` | below the host's dataset prefix, at `.../erddap` | the one dataset (or group) in the URL, and any groups below it |
| `app_router` | `/erddap` | every group of every dataset; only where it can work (see 3) |

For a Flux-style service, the `dataset_router` is the one that matters: with a
group path in the dataset prefix, each group gets an ERDDAP root beside its
`/opendap`, e.g.
`.../services/erddap/NOAA-PMEL/cefi-nep-hindcast-daily/main/regrid/main/erddap`.

The plugin reads data **only through the `deps` xpublish passes it**
(`deps.datatree`, `deps.dataset_ids`, `deps.cache`), as xpublish's plugin guide
asks and as xpublish-tiles does. The stand-in host is `tests/flux_host.py`: an
`xpublish.Rest` subclass whose dataset prefix is
`/{org}/{repo}/{ref}/{group_path:path}` and whose `deps.datatree` takes
`org`, `repo`, `ref` and the group.

Requires `xpublish>=0.5` (DataTree groups).

## Choices that may need to change for your host

### 1. How a dataset is named (the likeliest change)

ERDDAP clients address data by **datasetID**, so this is user-facing: it is
what people put in `e.dataset_id = ...` or `griddap("...")`.

**Our choice:** the URL's path parameters that name the dataset, in path order,
then the group path, run through the plugin's datasetID rule (non-alphanumerics
become `_`; a dataset whose variables use different dimensions is split, with
a suffix such as `_z_l`). In the stand-in host that gives

    /NOAA-PMEL/cefi-nep-hindcast-daily/main/regrid/main/erddap
    -> NOAA_PMEL_cefi_nep_hindcast_daily_main_regrid_main  (and ..._z_l)

That is long, and it includes the ref, so a client's datasetID would change if
the same data were served from another branch or tag. We kept it because it is
unambiguous and needs no knowledge of the host. "Path parameters" means every
path parameter of the matched route except the plugin's own (`ext`,
`erddap_id`, `target`) and the group (`group_path`), so it depends on what
your parameters are called.

**To change it**, pass a function. It receives those parameters as a dict and
the group path (`""` for a store's root), and returns a name:

```python
def by_repo(params: dict[str, str], group: str) -> str:
    # Drops org and ref: fine, because the plugin never caches on this name
    return f"{params['repo']}/{group}" if group else params["repo"]


ErddapPlugin(name_dataset=by_repo)  # -> cefi_nep_hindcast_daily_regrid_main
```

`tests/test_dataset_router.py::test_flux_like_host_can_drop_org_and_ref`
covers exactly this. Ideally the name would match the datasetID the data had
on the ERDDAP server it came from, so users change nothing but the URL; a host
that knows that ID can return it here.

### 2. How the group is found

**Our choice:** xpublish 0.5's convention. The group is the `{group_path:path}`
path parameter, read with `xpublish.dependencies.get_group_path`, and
`deps.datatree` returns the subtree at that group. Flux's DAP2 service behaves
this way from the outside (any depth of group; parent groups answer with an
empty dataset), so we assumed its internals follow it.

**If yours differs:** as long as `deps.datatree` returns the right subtree, the
catalog is right. Only the *name* uses the group path; a host that routes groups
under another parameter name should pass `name_dataset` (1).

In the stand-in host, a store's root group would need the path
`.../{ref}//erddap`, so only groups below the root are tested. A real host that
serves the root at `.../{ref}/erddap` should work the same, with `group` = `""`.

### 3. When the server-wide `/erddap` is left out

**Our choice:** the `app_router` adds its routes only if `deps.datatree` takes
**exactly one** required argument (a dataset id), because its catalog has to
list datasets and look each one up by id. Otherwise it registers nothing:

- Under `xpublish.SingleDatasetRest`, dataset routers sit at the app root, so
  both routers would claim `/erddap` and xpublish would refuse to build the app.
- In a host that names datasets with several parameters (`org`, `repo`, `ref`),
  a dataset cannot be looked up by one id.

**If you want an org-wide catalog** (one ERDDAP root listing many stores, closer
to how ERDDAP servers are used today), that needs a way to enumerate stores and
open one by name. That is a conversation, not a setting.

### 4. The URLs the plugin hands back

Catalog, search and NcML responses contain absolute URLs back into the same
ERDDAP root, and clients follow them. **Our choice:** build them from the
request: scheme and host from the request URL, then Starlette's `root_path`,
then the request path less the route's own part.

**What this needs from the host:** behind a proxy, the public scheme and host
must reach the app (e.g. uvicorn `--proxy-headers` with `X-Forwarded-Proto`/
`-Host`), and any path the proxy strips must be in `root_path`. Our AWS test
server does this behind Caddy, and `deploy/check_clients.py` checks that every
returned URL starts with the public base URL; it is a quick check to run
against a deployment.

### 5. When a catalog is rebuilt (caching)

A catalog is what the plugin builds from a dataset's metadata (axes, attributes,
the split into ERDDAP datasets) and serves every request from. It holds the
dataset as it was when built, so a stale catalog serves a stale time axis:
clients see old data, not an error. Building one reads metadata only, no data.

**Our choice:** a cached catalog is valid for one **`_xpublish_id`**. On every
request the plugin asks the host for the dataset's current tree (through
`deps.datatree`, as it must anyway), reads `_xpublish_id` from it (the node's
own, else the tree root's), and rebuilds the catalog if it differs from the one
the catalog was built from. This follows xpublish's conventions: xpublish's own
`dataset_info` and Earthmover's xpublish-tiles key their caches on
`_xpublish_id`, and xpublish-tiles asks hosts to make it unique.

**What this needs from the host:** a new `_xpublish_id` whenever the data
changes. Flux, from the outside, already does this: its `_xpublish_id` is
`{org}/{repo}/{snapshot}/{group}`, and a commit makes a new snapshot, so new
commits appear on the next request with nothing else to set up. Plain
`xpublish.Rest` sets `_xpublish_id` to the dataset id, which never changes.

**If your data changes under a fixed id** (a Zarr store appended to in place,
or a provider that reopens a branch but keeps its id), either put a version in
`_xpublish_id` (e.g. `f"{store}@{snapshot_id}"`), or set a maximum age:

```python
ErddapPlugin(catalog_max_age_s=600)  # rebuild at least every 10 minutes
```

**Costs to know:**
- The server-wide `/erddap` asks for *every* dataset's tree on each request to
  check its id (only changed ones are rebuilt). That is cheap when the host
  keeps stores open, and slow if it reopens a store on every call; the
  per-dataset root asks only for its own.
- Catalogs live in xpublish's shared `cachey` cache (`deps.cache`) under
  `erddap_entries/...` and `erddap_catalog/...` keys, one entry per dataset,
  replaced when its id changes, so old catalogs are not kept. A per-dataset
  root keys its entry on the URL's identity (its path parameters and group
  path), **not** on `name_dataset`'s result, so a name that ignores the group
  or the ref cannot make two roots share a catalog; `name_dataset` only
  chooses the datasetID. Each ref or group gets its own entry, which stays
  until cachey evicts it. The plugin tells cachey each catalog's approximate
  size (axes plus attributes), so eviction works under memory pressure; an
  evicted catalog is rebuilt.
- There is no invalidation endpoint (ERDDAP's `setDatasetFlag.txt`): without
  auth (issue [#8](https://github.com/eeholmes/xpublish-erddap/issues/8)),
  anyone could force rebuilds.

### 6. OPeNDAP binary (`.dods`)

ERDDAP can serve `.dods`; this plugin answers it with **501** and a message
pointing at the dataset's OPeNDAP endpoint, because a host like Flux already
serves `/opendap` beside it (issue
[#2](https://github.com/eeholmes/xpublish-erddap/issues/2)).

### 7. Axis and variable names

ERDDAP names the geographic axes `latitude` and `longitude` and the time axis
`time`, and client code relies on it: rerddap and erddapy users write
`latitude = c(40, 50)` or `"latitude>="`, and plotdap reads the axes by those
names. So by default the plugin **serves recognised axes under ERDDAP's names**
in every response (`.dds`, `.das`, `.ncml`, `.nc`, csv/json headers, info,
constraints). A store whose axes are `t`, `lat`, `lon` is served as `time`,
`latitude`, `longitude`; the source names are then unknown variables, as they
would be on an ERDDAP server whose admin renamed them. DatasetIDs (including
the suffix of a split dataset) still come from the source names, so turning
this on or off does not move a dataset.

An axis is recognised only when it is clearly that axis:

- **latitude / longitude**: `standard_name` `latitude`/`longitude`; or CF
  degree units (`degrees_north`, `degrees_east` and the variants ERDDAP
  accepts); or ERDDAP's own test, a lat/lon-like name (`lat`, `latitude`,
  `nav_lon`, ...) with no units or degree units (`EDV.probablyLat`/
  `probablyLon`, used by ERDDAP's GenerateDatasetsXml). Not recognised:
  projected `x`/`y` in metres (ERDDAP would take a unitless `x`/`y`; we need
  degree units for those), an axis whose `standard_name` says something else
  (`grid_latitude`), or one whose name and units disagree.
- **time**: a datetime axis (`t`, `valid_time`, ...). A timedelta axis
  (`lead_time`) is not time, and neither is a numeric axis with CF time units
  that xarray did not decode, since it would be served as raw numbers under a
  name that promises UTC timestamps.

If the target name is already taken by another variable in the dataset, the
axis keeps its own name and a warning is logged.

To change it:

```python
ErddapPlugin(rename_axes=False)  # serve source names
ErddapPlugin(rename_axes={"lat": "latitude", "lon": "longitude"})  # exactly these
```

A dict replaces recognition: only the axes it names are renamed.

**Variable names ERDDAP cannot serve** are made safe either way. ERDDAP allows
a letter or `_` followed by letters, digits and `_` (`String2.isVariableNameSafe`).
A variable called `sst-anom` or `1st` would be listed but could never be
requested (`?sst-anom[0]` reads as `sst`), so it is served under the name
ERDDAP's GenerateDatasetsXml would give it: `sst_anom`, `a_1st`
(`EDD.suggestDestinationName`). If that name is taken too, the variable is left
out with a warning (an axis that cannot be named leaves the whole dataset out).

## Settings at a glance

```python
ErddapPlugin(
    name_dataset=...,  # (1) how a per-dataset root names its dataset
    max_response_mb=500,  # refuse larger data requests with ERDDAP's 413
    metadata={...},  # global attributes for every dataset (ERDDAP's addAttributes)
    strict_axes=True,  # drop datasets with non-monotonic axes, as ERDDAP does
    rename_axes=True,  # (7) serve lat/lon/time axes as latitude/longitude/time
    catalog_max_age_s=None,  # (5) also rebuild catalogs after this many seconds
)
```

`dataset_router_prefix` and `app_router_prefix` (both `/erddap`) are xpublish's
usual plugin fields.
