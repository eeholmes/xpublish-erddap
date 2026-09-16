# Exercise the R client (rerddap) against a live xpublish-erddap server.
# Run by CI after starting tests/server.py; see .github/workflows/tests.yml.
library(rerddap)

url <- "http://127.0.0.1:9000/erddap/"
ok <- function(msg) cat("ok -", msg, "\n")

i <- info("air", url = url)
stopifnot(attr(i, "type") == "griddap")
stopifnot("air" %in% i$variables$variable_name)
ok("info() returns a griddap dataset with the expected variable")

dims <- rerddap:::dimvars(i)
stopifnot(all(c("time", "lat", "lon") %in% dims))
ok("info() exposes the expected dimensions")

res <- griddap(
  "air", url = url,
  time = c("2013-01-05", "2013-01-08"),
  lat = c(40, 50), lon = c(240, 250),
  fields = "air"
)
stopifnot(nrow(res$data) > 0)
stopifnot(all(c("lat", "lon", "time", "air") %in% names(res$data)))
stopifnot(all(res$data$lat >= 40 & res$data$lat <= 50))
ok(sprintf("griddap() returned %d rows with the expected columns", nrow(res$data)))

# The catalog splits a source with mixed dimensions into several datasets
j <- info("mixed_level", url = url)
stopifnot("air_levels" %in% j$variables$variable_name)
ok("the split dataset is usable from R")

# One Arraylake store as Flux would serve it: an ERDDAP root below a store path
store <- paste0(
  "http://127.0.0.1:9000/v1/services/dap2/NOAA-PMEL/",
  "cefi-nep-hindcast-daily/main/regrid/main/erddap/"
)
k <- info("cefi_nep_hindcast_daily_regrid", url = store)
stopifnot("tos" %in% k$variables$variable_name)
res <- griddap(
  k, time = c("2020-01-02", "2020-01-03"),
  lat = c(22, 23), lon = c(231, 232), fields = "tos"
)
stopifnot(nrow(res$data) == 2 * 3 * 3)
ok("info() and griddap() work against a store-level ERDDAP root")

cat("\nAll rerddap checks passed\n")
