# Test-suite review, 2026-10-09 (#110)

EH asked, before the move to xpublish-community, whether the 600+ tests
were too many: duplicates, things to prune. This is what was found and
why. The work is #111–#114; this note is the detail they point at.

| Order | Issue | Work | Suggested model |
|---|---|---|---|
| 1 of 4 | #111 | Tests that cannot fail; CI file selection | Sonnet 5.5 |
| 2 of 4 | #112 | Run time: server fixture, 28 s test, parity skips | Sonnet 5.5 |
| 3 of 4 | #113 | Prune duplicates and parity-covered tests | Sonnet 5.5 |
| 4 of 4 | #114 | Tidy test comments and labels before the move | Haiku 4.5 |

None needs Opus: the judgment (what is covered, what to keep) is made
here; the work is checking each claim against the goldens and editing.

## Method

Read-only, on `main` after #69 (PR #108). Three agents each read a group
of test files against the source, the parity goldens and `git log`, and
listed duplicates, parity overlap, over-wide parametrizations and things
that only look redundant. Their claims were spot-checked (all the test
names below exist; the `test_api.py` 404 duplicate and the `erddapy-3-1`
grep were confirmed by hand). One agent's line numbers in `test_limits.py`
were wrong, so tests are named here, not numbered.

**A "covered by parity" claim must be checked against the golden manifest
before a test is deleted.** Parity compares the exact error body only when
the golden starts with `Error {` (ERDDAP's own); two golden error bodies
(`CRW_sst_v1_0_monthly.foo`, `info/.../index.foo`) are proxy pages, so
their wording is not compared. Parity snapshots load *decoded* data with
ERDDAP's generated attributes already present, so nothing about raw
integers, packing, `_Unsigned`, inferred `ioos_category` or derived
coverage globals is covered by parity.

## The numbers

974 collected: 922 passed, 43 skipped, 9 xfailed, 126 s on the hub
(`~/venvs/xpe`).

- **478 are `test_parity.py`**: two functions × 239 golden requests from
  10 datasets. Cheap (in-process), and the contract with real ERDDAP.
  **The 43 skips are all `test_media_type_matches_real_erddap` on error
  goldens**, skipped at run time instead of left out of the parameters.
- About 496 are hand-written (about 270 functions).
- **Run time is dominated by two things, not by test count:**
  - `xpublish_server` (`conftest.py`) is function-scoped, so the same
    static `tests/server.py` starts about 38 times, ~3 s each: ~60–70 s.
  - `test_none_means_no_limit_for_csv` builds a 1,000,000-row csv: 28 s.
  - Next: the four real-calendar cases of
    `test_no_served_time_differs_from_its_source`, ~7 s together.

Doing everything below: about 650–840 tests (depending on whether the two
parity functions are folded into one) and under a minute.

## Problems (#111)

- `test_catalog_cache.py::test_a_new_commit_is_listed_after_the_check_interval`
  cannot fail at its first assertion: it checks `"s0_2" not in` the
  listing, but the new dataset is `s0_depth`. It also never checks that
  `s0_depth` is still absent *after* the commit and *before* `now[0] += 10`,
  which is the guarantee (#69) it is named for.
- The `erddapy-3-1` CI job picks files with `grep -rl erddapy`, which
  matches docstrings: it also runs `test_api.py` and `test_constraints.py`,
  which never import erddapy.
- `test_categorize.py` does `import erddapy`, not `importorskip`, so
  without erddapy the whole file errors instead of skipping.

## Run time (#112)

- Session-scope `xpublish_server`. Check no live test depends on a fresh
  server (the server is static; its catalog check interval is 10 s).
- Shrink `test_none_means_no_limit_for_csv` to a strided request
  (`v[0][0:10:999][0:10:999]`); it still shows `None` passes the check.
- Leave error goldens out of the media-type parameters instead of skipping.
- **EH's call:** fold the media-type check into `test_matches_real_erddap`
  (−239 ids; `KNOWN_MEDIA` would need its own handling), and trim the CI
  matrix (3 OS × 3 Python; Windows skips every live test), e.g. Ubuntu ×
  3 Pythons + one macOS + one Windows.

## Prune (#113)

### Covered by parity (verify each against the manifest first)

- `test_constraints.py`: `test_time_zone_with_raw_or_encoded_plus`
  (jplMURSST41 has raw, `%2B`, `+08`, `+0800`; javaparse has them too),
  `test_impossible_dates_roll_over`, `test_value_beyond_the_half_spacing_margin_is_refused`,
  `test_start_and_stop_are_both_checked`, `test_wrong_longitude_convention_is_refused`,
  `test_error_names_the_variable_and_constraint` (etopo5 error goldens),
  `test_iso_times_are_not_split_on_their_colons` (CRW queries),
  `test_epoch_seconds_and_numbers_on_a_time_axis` (`time[(1.5e9)]`).
  Trim, not drop: `test_bad_last_is_a_400_with_erddaps_text` (keep only
  `(last-)`), `test_indices_are_digits_within_the_axis` (keep only `last+1`),
  `test_unreadable_times_are_a_400` (keep `2019:01:01` and `NaN`; fold in
  `test_unreadable_value_is_a_400_like_erddap`, whose Stop role is the only
  new thing).
- `test_api.py`: `test_search_for_all_lists_every_dataset`,
  `test_search_needs_a_query` (etopo5 search goldens),
  `test_raw_plus_in_a_time_zone`, `test_last_plus_and_a_negative_index`,
  `test_value_off_an_axis_is_404_like_erddap`, `test_stride_is_honoured`,
  `test_index_subsetting_matches_coordinate_subsetting`,
  `test_axis_only_columns_sit_side_by_side`, `test_axis_only_netcdf_holds_only_the_axes`.
  The early format tests (`.dds` keywords, `.das` order, info columns,
  NcML, `.nc` round trip, json shape, info media type) predate parity
  (2026-09-15/16) and are covered by it; their only value left is the
  docstring naming the client that depends on each. Drop or keep as one
  smoke test.
- `test_erddap_grammar.py`: `test_axis_only_csv_pads_numbers_with_nan_and_time_with_blank`
  (keep only a `.json` null check), `test_two_variables_with_one_subset_are_still_served`
  (noaacwBLENDED u+v); weak drop: `test_ncml_escapes_percent_as_a_numeric_entity`
  (dhw_5km has `&#37;`, but the test adds `<>&"`).
- `test_search.py::test_tables_have_erddaps_columns` (parity catalog cases).
- `test_formats.py`: the `CRW_sst_v1_0_monthly` case of `test_duration`,
  `test_spacing_of_a_descending_float32_axis`.

### Duplicates

- `test_api.py::test_unknown_dataset_is_404` ⊂ `test_errors_have_erddaps_body`.
- `test_api.py::test_search_finds_and_filters` ⊂ `test_search_for_all_lists_every_dataset`.
- `test_api.py::test_coordinate_value_subsetting` = same query as
  `test_fully_percent_encoded_csv_request` (#52); keep the latter.
- `test_erddap_grammar.py`: `test_jsonp_on_a_data_request` and
  `test_jsonp_on_a_whole_dataset_request` repeat `test_jsonp_wraps_a_json_response`
  (one wrap point in `plugin.py`).
- `test_constraints.py::test_wrong_selector_count_rejected` and
  `test_empty_parentheses_are_missing_values` repeat grammar tests; move
  the `(  ):1:(5)` whitespace case across first.
- Superseded prototypes (2026-09-15): `test_coordinate_values_use_nearest`,
  `test_reversed_range_is_tolerated`, `test_last_forms`.
- `test_time_axes.py`: `test_projected_xy_are_not_lat_lon` and
  `test_supplied_bounds_go_like_erddap` both assert polar `.das` has no
  `geospatial_lat_min`: merge. `test_dates_that_do_not_exist_are_refused`
  and `test_monthly_360_day_keeps_labels` are covered by the big calendar
  test plus `test_daily_360_day_is_refused`.
- `test_erddap_grammar.py::test_calendar_and_coordinates_are_served` and
  its `_in_ncml_info_and_nc` sibling test one fix: merge.
- `test_head.py::test_head_on_data_builds_no_body` and
  `test_dods.py::test_head_builds_no_body` take the same branch: add `dods`
  to the former's parameters, drop the latter. Neither checks HEAD's
  content-type equals GET's for csv/json/nc; worth adding.
- `test_limits.py::test_the_smaller_limit_is_reported` repeats the `nc`
  case of `test_default_settings_refuse_a_whole_variable`.
- Live-server duplicates: `test_server.py::test_mixed_dimensions_split_into_two_datasets`
  (in-process in `test_api.py`, and through erddapy next to it),
  `test_categorize.py::test_erddapy_over_a_socket` (erddapy only builds
  URLs; also no win32 skip), `test_tutorials.py::test_erddapy_griddap_example_download`
  (move its bound asserts into `test_erddapy_griddap_page_exactly`, #52).
  Optional: `test_tutorials.py::test_erddapy_opendap_response` (same
  request as `test_open_dataset_on_the_griddap_url`),
  `test_store_mount.py::test_erddapy_finds_the_split_dataset`,
  `test_server.py::test_erddapy_download_file_rejects_unknown_types`
  (tests erddapy's own error), R tutorial 1 in `test_tutorials.R` (same URL
  and checks as the Python tutorial 1; EH's call, it is a user tutorial).

### Parametrizations wider than the code paths

- `test_convert.py::test_and_on_a_per_dataset_root`: 6 paths through a
  one-line route; 1 is enough (keep the 6 on `/erddap`, they are real
  rerddap/rerddapXtracto calls).
- `test_time_axes.py::test_no_served_time_differs_from_its_source`: drop
  one of each cftime alias pair (`gregorian`/`standard`,
  `365_day`/`noleap`, `366_day`/`all_leap`). Keep the test: it guards EH's
  "never change a value" rule (#60).
- `test_names.py::test_recognised_axis` (22): `t`/`valid_time`,
  `j`/`y`+`degrees_north`, string `lon`/`lead_time` share branches; ~4 go.
  The rename HTTP tests check one rename in `build_catalog` across six
  formats; 2–3 would do.
- `test_javaparse.py::test_iso_to_epoch_seconds`: 8 time-zone cases → 4.
  Everything else there tests a separate ERDDAP quirk.
- `test_erddap_grammar.py::test_empty_and_bad_parts_of_a_range_are_refused`
  (11 → ~6), `test_an_and_clause_must_start_with_a_dot` (`&` and `FULL&`
  share a path).
- `test_limits.py`: `test_configured_limit_refuses_every_data_format`
  (5 → csv, nc; `check_size` ignores format except the `.nc` 2 GB rule),
  `test_default_settings_refuse_a_whole_variable` (3 → 1).
- `test_head.py::test_head_matches_get`: 7 paths through one wrapper → 2–3.
- `test_dods.py::test_types_and_fills`: rebuilds `typed_client()` per case;
  make it a module fixture (speed only, keep all 8 cases).

### Looks redundant, keep

These guard bugs that happened or rules EH set; do not prune them:
`test_far_dates_do_not_wrap_into_the_axis` (2577 served as 1993), the
float32 margin/digit tests (live erdMH1chla8day text), the tie tests (#11),
raw vs decoded integer types (#78, #64), `_Unsigned` and packed tests,
`test_types_and_fills` (unsigned `.dods` is only tested here; parity's is
an xfail), `test_one_value_axis_*` (only double axes in parity), the
`ROOTS` × 3 in `test_catalog_cache.py` (two caching paths, #69 and #61),
the request order in `test_dataset_router.py` (#61), both "no server-wide
root" tests (async getter vs Flux host), `test_store_mount.py` (a mounted
root; a different hosting shape from `dataset_router`), the numeric/string
split in `test_tutorials.py` (erddapy 3.1 vs 3.3, #10), `engine="erddapy"`
(min-deps skips it on purpose), the stride-rounding and `&`-clause tests
(#71, no parity case), the 7 bad-jsonp-name cases (one rule each), and
the R scripts as a whole (rerddap and rxtracto paths with no Python
equivalent). `test_javaparse.py` is where unit-level parse cases belong;
its docstring says the user-facing ones are also parity cases on purpose,
so cut the copies elsewhere, not there.

**Do not prune golden directories casually:** `tutorial_data.real_axes()`
reads `oceanwatch.pifsc.noaa.gov__CRW_sst_v1_0_monthly` and
`erddap.ioos.us__etopo5_EDDGridCopy` `snapshot.nc`; the tutorial tests,
the R scripts and `tests/server.py` depend on them.

## Before the move (#114)

- `test_rerddap.R` cites `claude/notes/client-compatibility.md` and
  mentions "the hub's 1.2.1"; say it in terms an outside contributor can
  follow.
- `test_store_mount.py`'s docstring, `test_rerddap.R` and README say the
  `STORE_PREFIX` mount is "as Flux would serve it"; since #18
  `flux_host.py` is the Flux stand-in, and the mount is a regression test
  for `app.mount()`/`root_path` (`erddap-parity-plan.md`).
- `tests/server.py` binds `0.0.0.0`; the fixture uses `127.0.0.1`.
- `tests/benchmark_server_catalog.py` is a tool, not collected; consider
  `benchmarks/` (`docs/hosting.md` cites its path).
