# Exercise the R client (rerddap) against a live xpublish-erddap server.
# Run by CI after starting tests/server.py; see .github/workflows/tests.yml.
library(rerddap)
library(rerddapXtracto)

url <- "http://127.0.0.1:9000/erddap/"
ok <- function(msg) cat("ok -", msg, "\n")

i <- info("air", url = url)
stopifnot(attr(i, "type") == "griddap")
stopifnot("air" %in% i$variables$variable_name)
ok("info() returns a griddap dataset with the expected variable")

dims <- rerddap:::dimvars(i)
stopifnot(all(c("time", "latitude", "longitude") %in% dims))
ok("info() exposes the expected dimensions")

res <- griddap(
  "air", url = url,
  time = c("2013-01-05", "2013-01-08"),
  latitude = c(40, 50), longitude = c(240, 250),
  fields = "air"
)
stopifnot(nrow(res$data) > 0)
stopifnot(all(c("latitude", "longitude", "time", "air") %in% names(res$data)))
stopifnot(all(res$data$latitude >= 40 & res$data$latitude <= 50))
ok(sprintf("griddap() returned %d rows with the expected columns", nrow(res$data)))

# The catalog splits a source with mixed dimensions into several datasets
j <- info("mixed_level", url = url)
stopifnot("air_levels" %in% j$variables$variable_name)
ok("the split dataset is usable from R")

# Regression test for app.mount() and root_path: an ERDDAP root below a store
# path (tests/flux_host.py is the Flux stand-in; this mount is a plain store path)
store <- paste0(
  "http://127.0.0.1:9000/v1/services/dap2/NOAA-PMEL/",
  "cefi-nep-hindcast-daily/main/regrid/main/erddap/"
)
k <- info("cefi_nep_hindcast_daily_regrid", url = store)
stopifnot("tos" %in% k$variables$variable_name)
res <- griddap(
  k, time = c("2020-01-02", "2020-01-03"),
  latitude = c(22, 23), longitude = c(231, 232), fields = "tos"
)
stopifnot(nrow(res$data) == 2 * 3 * 3)
ok("info() and griddap() work against a store-level ERDDAP root")

# --- The rest of rerddap's griddap surface (#67) -----------------------------
# Data come from tests/tutorial_data.py: formula values, so every number is
# checked. CRW_sst_v1_0_monthly has the real axes (time irregular, 0.05 degree
# grid centred on .025); the *_like datasets are small and carry the vertical
# axes (and the north-to-south latitude) the CoastWatch/rerddap examples use.

# tests/tutorial_data.py::sst, in R
sst_formula <- function(time, lat, lon) {
  lt <- as.POSIXlt(time, tz = "GMT")
  month <- ((lt$year - 70) * 12 + lt$mon) %% 12
  28 - 20 * (lat / 90)^2 + cos(2 * pi * month / 12) + 0.01 * lon
}
# tests/tutorial_data.py::vert_value, in R
vert_formula <- function(time, vert, lat, lon) {
  day <- floor(as.numeric(as.POSIXct(time, tz = "GMT")) / 86400) %% 365
  15 + 0.1 * lat - 0.01 * lon - 0.05 * vert + day / 100
}

crw <- info("CRW_sst_v1_0_monthly", url = url)
box <- list(latitude = c(17, 17.5), longitude = c(195, 195.5))
t_start <- "2018-01-01T12:00:00Z"
t_end <- "2018-03-01T12:00:00Z"
# note: rerddap's check_time_range compares strings, so a date-only bound that
# equals the first time ("1985-01-01" vs "1985-01-01T12:00:00Z") halts, as it
# does against real ERDDAP (so it is not a server bug); these tests
# give full timestamps.
get_crw <- function(...) {
  suppressMessages(griddap(crw, ...))
}

# fmt = "csv" gives a griddap_csv with the same values as the default nc
res_csv <- get_crw(time = c(t_start, t_end), latitude = box$latitude,
                   longitude = box$longitude, fmt = "csv")
res_nc <- get_crw(time = c(t_start, t_end), latitude = box$latitude,
                  longitude = box$longitude)
stopifnot(inherits(res_csv, "griddap_csv"))
stopifnot(nrow(res_csv) == 3 * 11 * 11, nrow(res_nc$data) == 3 * 11 * 11)
stopifnot(identical(names(res_csv), c("time", "latitude", "longitude", "analysed_sst")))
key <- function(d) paste(d$time, round(d$latitude, 4), round(d$longitude, 4))
res_csv <- res_csv[order(key(res_csv)), ]
res_nc_data <- res_nc$data[order(key(res_nc$data)), ]
stopifnot(identical(key(res_csv), key(res_nc_data)))
stopifnot(max(abs(res_csv$analysed_sst - res_nc_data$analysed_sst)) < 1e-6)
stopifnot(max(abs(res_csv$analysed_sst -
  sst_formula(res_csv$time, res_csv$latitude, res_csv$longitude))) < 1e-6)
ok("griddap(fmt = 'csv') matches the nc values and the formula")

# "last": rerddap writes (last), the nearest value of the final time
res <- get_crw(time = c("last", "last"), latitude = box$latitude, longitude = box$longitude)
stopifnot(unique(res$data$time) == "2020-08-01T12:00:00Z")
stopifnot(nrow(res$data) == 11 * 11)
ok("griddap(time = c('last', 'last')) returns the final time")

# "last-n" on a value axis is ERDDAP's (last-d): d in axis units, so
# last-0.1 reaches back two 0.05-degree latitude steps (three rows).
res <- get_crw(time = c("last", "last"), latitude = c("last-0.1", "last"),
               longitude = box$longitude)
lats <- sort(unique(res$data$latitude))
top <- get_crw(time = c("last", "last"), latitude = c("last", "last"),
               longitude = box$longitude)
stopifnot(length(lats) == 3, max(lats) == unique(top$data$latitude))
stopifnot(all(abs(diff(lats) - 0.05) < 1e-4))
ok("griddap(latitude = c('last-0.1', 'last')) reaches back 0.1 degrees")

# stride, scalar (every dimension) and a vector (time, latitude, longitude)
res <- get_crw(time = c(t_start, t_end), latitude = box$latitude,
               longitude = box$longitude, stride = 2)
stopifnot(identical(unique(res$data$time), c(t_start, t_end)))
stopifnot(length(unique(res$data$latitude)) == 6, length(unique(res$data$longitude)) == 6)
stopifnot(max(abs(res$data$analysed_sst -
  sst_formula(res$data$time, res$data$latitude, res$data$longitude))) < 1e-6)
ok("griddap(stride = 2) takes every second point on every axis")

res <- get_crw(time = c(t_start, t_end), latitude = box$latitude,
               longitude = box$longitude, stride = c(1, 2, 3))
stopifnot(length(unique(res$data$time)) == 3)
stopifnot(length(unique(res$data$latitude)) == 6, length(unique(res$data$longitude)) == 4)
stopifnot(all(abs(diff(sort(unique(res$data$latitude))) - 0.1) < 1e-4))
stopifnot(all(abs(diff(sort(unique(res$data$longitude))) - 0.15) < 1e-4))
ok("griddap(stride = c(1, 2, 3)) strides each axis separately")

# A dimension left out means its whole axis (every time here)
res <- get_crw(latitude = c(17, 17.1), longitude = c(195, 195.1))
times <- unique(res$data$time)
stopifnot(length(times) == 428)
stopifnot(times[1] == "1985-01-01T12:00:00Z", times[428] == "2020-08-01T12:00:00Z")
ok("a dimension left out is requested in full")

# fields = "none" asks for the axes only. Over nc rerddap itself fails (its
# reader indexes the first variable), so the csv form is the one that works.
res <- get_crw(time = c("last", "last"), latitude = c(17, 17.1),
               longitude = c(195, 195.1), fields = "none", fmt = "csv")
stopifnot(identical(names(res), c("time", "latitude", "longitude")))
stopifnot(identical(res$time[1], "2020-08-01T12:00:00Z"))
stopifnot(isTRUE(all.equal(sort(res$latitude[!is.na(res$latitude)]), c(17.025, 17.075))))
stopifnot(isTRUE(all.equal(sort(res$longitude), c(195.025, 195.075, 195.125))))
ok("griddap(fields = 'none') returns the axes alone")

# --- Search, the dataset list and the version ---------------------------------
stopifnot(grepl("^ERDDAP_version=", rerddap::version(url)))
ok("version() reads /erddap/version")

found <- ed_search("CRW", url = url)
stopifnot(length(found$info$dataset_id) == 1, found$info$dataset_id == "CRW_sst_v1_0_monthly")
ok("ed_search() finds a dataset by a word of its id")

found <- suppressMessages(ed_search_adv(query = "CRW", url = url))
stopifnot(length(found$info$dataset_id) == 1, found$info$dataset_id == "CRW_sst_v1_0_monthly")
ok("ed_search_adv() finds it too")

listing <- ed_datasets("griddap", url = url)
stopifnot(all(c("CRW_sst_v1_0_monthly", "etopo5_EDDGridCopy", "air", "mixed",
                "viirs_like", "soda_like", "oisst_like") %in% listing$Dataset.ID))
ok("ed_datasets('griddap') lists every dataset")

found <- global_search("CRW", url, "griddap")
stopifnot(length(found$dataset_id) == 1, found$dataset_id == "CRW_sst_v1_0_monthly", found$url == url)
ok("global_search() over a server list of one (ours)")

# --- A descending latitude axis (VIIRS), altitude, depth and zlev -----------
# viirs_like: latitude runs 30 -> 20, one altitude (0). rerddap reads the order
# from info() and writes the latitude bounds north first.
viirs <- info("viirs_like", url = url)
res <- suppressMessages(griddap(
  viirs, time = c("last", "last"), altitude = c(0, 0),
  latitude = c(22, 24), longitude = c(202, 203)
))
stopifnot(grepl("[(24):1:(22)]", attr(res, "url"), fixed = TRUE))
stopifnot(nrow(res$data) == 9 * 5, range(res$data$latitude) == c(22, 24))
stopifnot(all(res$data$altitude == 0))
stopifnot(max(abs(res$data$chlor_a - vert_formula(
  res$data$time, res$data$altitude, res$data$latitude, res$data$longitude))) < 1e-6)
ok("griddap() on a north-to-south latitude axis with an altitude dimension")

# rxtracto's zcoord is what carries the altitude (rerddapXtracto's zName)
track <- rxtracto(
  viirs, parameter = "chlor_a", xcoord = c(202.5, 203), ycoord = c(23, 24),
  tcoord = c("2018-01-02", "2018-01-03"), zcoord = c(0, 0)
)
expected <- vert_formula(c("2018-01-02", "2018-01-03"), 0, c(23, 24), c(202.5, 203))
stopifnot(max(abs(track[["mean chlor_a"]] - expected)) < 1e-6)
stopifnot(all(track[["requested z min"]] == 0))
ok("rxtracto(zcoord = ) on the altitude dimension")

soda <- info("soda_like", url = url)
res <- suppressMessages(griddap(
  soda, time = c("last", "last"), depth = c(70.02, 70.02),
  latitude = c(0, 1), longitude = c(100, 101)
))
stopifnot(nrow(res$data) == 9, all(res$data$depth == 70.02))
stopifnot(max(abs(res$data$temp - vert_formula(
  res$data$time, res$data$depth, res$data$latitude, res$data$longitude))) < 1e-6)
ok("griddap() with a depth dimension (SODA's depth = 70.02)")

oisst <- info("oisst_like", url = url)
res <- suppressMessages(griddap(
  oisst, time = c("last", "last"), zlev = c(0, 0),
  latitude = c(0, 1), longitude = c(100, 101)
))
stopifnot(nrow(res$data) == 9, all(res$data$zlev == 0))
stopifnot(max(abs(res$data$sst - vert_formula(
  res$data$time, res$data$zlev, res$data$latitude, res$data$longitude))) < 1e-6)
ok("griddap() with a zlev dimension (OISST's zlev = 0)")

# --- estimate_griddap_size ------------------------------------------------------
# estimate_griddap_size() was added in rerddap 1.3.0; skip on older versions.
if (exists("estimate_griddap_size", asNamespace("rerddap"))) {
  est <- rerddap:::estimate_griddap_size(
    crw, time = c(t_start, "2018-12-31T12:00:00Z"),
    latitude = c(17, 30), longitude = c(195, 210), verbose = FALSE
  )
  # time from nValues and actual_range, latitude and longitude from
  # geospatial_lat/lon_resolution: all three come from info()
  stopifnot(identical(unlist(est$dim_npts), c(time = 12L, latitude = 261L, longitude = 300L)) ||
            all(unlist(est$dim_npts) == c(12, 261, 300)))
  stopifnot(est$n_cells == 12 * 261 * 300)
  ok("estimate_griddap_size() counts 12 x 261 x 300 cells on CRW")
} else if (nzchar(Sys.getenv("CI"))) {
  stop("rerddap ", as.character(packageVersion("rerddap")), " lacks estimate_griddap_size")
} else {
  cat("skipped - estimate_griddap_size needs rerddap >= 1.3.0, have",
      as.character(packageVersion("rerddap")), "\n")
}

cat("\nAll rerddap checks passed\n")
