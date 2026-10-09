# CoastWatch satellite-course R tutorials, run against xpublish-erddap.
# Run by CI after starting tests/server.py; see .github/workflows/tests.yml.
#
# The data-access steps are the tutorials' own, with only the server swapped.
# The dataset is the stand-in from tests/tutorial_data.py: the real
# CRW_sst_v1_0_monthly axes, with formula values (sst() below).
suppressMessages({
  library(httr)
  library(ncdf4)
  library(rerddap)
  library(rerddapXtracto)
})

server <- "http://127.0.0.1:9000/erddap/"
ok <- function(msg) cat("ok -", msg, "\n")

# tests/tutorial_data.py::sst, in R
sst_formula <- function(time, lat, lon) {
  lt <- as.POSIXlt(time, tz = "GMT")
  month <- ((lt$year - 70) * 12 + lt$mon) %% 12
  28 - 20 * (lat / 90)^2 + cos(2 * pi * month / 12) + 0.01 * lon
}

# --- Tutorial 1: how to work with satellite data in R -----------------------
url <- paste0(
  server, "griddap/CRW_sst_v1_0_monthly.nc?analysed_sst",
  "[(2018-01-01T12:00:00Z):1:(2018-12-01T12:00:00Z)][(17):1:(30)][(195):1:(210)]"
)
path <- file.path(tempdir(), "sst.nc")
junk <- GET(url, write_disk(path, overwrite = TRUE))
stopifnot(status_code(junk) == 200)

nc <- nc_open(path)
stopifnot("analysed_sst" %in% names(nc$var))
v1 <- nc$var[[1]]
sst <- ncvar_get(nc, v1)
stopifnot(identical(dim(sst), c(301L, 261L, 12L)))
dates <- as.POSIXlt(v1$dim[[3]]$vals, origin = "1970-01-01", tz = "GMT")
lon <- v1$dim[[1]]$vals
lat <- v1$dim[[2]]$vals
nc_close(nc)
ok("tutorial 1: GET + nc_open give a 301 x 261 x 12 array")

stopifnot(format(dates[1], "%Y-%m-%d %H") == "2018-01-01 12")
stopifnot(format(dates[12], "%Y-%m-%d %H") == "2018-12-01 12")
stopifnot(abs(min(lat) - 17) < 0.05, abs(max(lon) - 210) < 0.05)
ok("tutorial 1: dates, latitudes and longitudes are as requested")

grid <- expand.grid(lon = lon, lat = lat, t = seq_along(dates))
expected <- sst_formula(dates[grid$t], grid$lat, grid$lon)
stopifnot(max(abs(as.vector(sst) - expected)) < 1e-6)
ok("tutorial 1: every value matches")

# --- Tutorial 3: extract data within a shapefile using ERDDAP ---------------
# The tutorial uses goes-poes-monthly-ghrsst-RAN; the stand-in is the CRW set.
dataInfo <- rerddap::info("CRW_sst_v1_0_monthly", url = server)
parameter <- dataInfo$variable$variable_name[1]
stopifnot(parameter == "analysed_sst")
ok("tutorial 3: info() names the parameter")

# rerddapXtracto's exported safe_info() (shown in the rxtracto help examples)
# HEADs info/{id}/index.html and returns NULL on a status >= 400 (#62)
head_resp <- HEAD(paste0(server, "info/CRW_sst_v1_0_monthly/index.html"))
stopifnot(status_code(head_resp) < 400)
ok("tutorial 3: HEAD on info/{id}/index.html succeeds, as safe_info() needs")

# A polygon across the dateline, in 0-360 longitudes as the tutorial converts
# them to, standing in for the Papahanaumokuakea monument shapefile.
xcoord <- c(177.5, 181.0, 190.0, 199.0, 198.0, 183.0, 177.5)
ycoord <- c(28.5, 29.5, 26.0, 22.0, 20.0, 25.0, 28.5)
tcoord <- c("2015-03-15", "2015-11-16")

sst <- rxtractogon(
  dataInfo, parameter = parameter,
  xcoord = xcoord, ycoord = ycoord, tcoord = tcoord
)
values <- sst[[parameter]]
stopifnot(length(dim(values)) == 3, dim(values)[3] == 9)
stopifnot(any(is.na(values)), any(!is.na(values)))
ok(sprintf(
  "tutorial 3: rxtractogon() returned %s, masked outside the polygon",
  paste(dim(values), collapse = " x ")
))

times <- as.POSIXct(sst$time, tz = "GMT")
grid <- expand.grid(lon = sst$longitude, lat = sst$latitude, t = seq_along(times))
expected <- sst_formula(times[grid$t], grid$lat, grid$lon)
inside <- !is.na(as.vector(values))
stopifnot(max(abs(as.vector(values)[inside] - expected[inside])) < 1e-6)
# rxtracto reads the axes itself and pads to the enclosing grid cells
stopifnot(min(sst$longitude) > 177.5 - 0.05, max(sst$longitude) < 199.0 + 0.05)
stopifnot(min(sst$longitude) < 180, max(sst$longitude) > 180)
ok("tutorial 3: values inside the polygon match, across the dateline")

# --- rxtracto(): the track matchup the CoastWatch R tutorials use (#67) -----
# Five of the tutorials call rxtracto(info, parameter, xcoord, ycoord, tcoord,
# xlen, ylen) for a ship or animal track and read back the "mean ..." and
# "satellite date" columns.
grid_centre <- function(x) round((x - 0.025) / 0.05) * 0.05 + 0.025
track_x <- c(195.52, 196.02, 200.52)
track_y <- c(17.52, 18.02, 20.27)
track_t <- c("2018-02-15", "2018-03-10", "2018-06-20")

# a box of zero size is the single nearest grid cell, so the value is exact
point <- rxtracto(
  dataInfo, parameter = parameter,
  xcoord = track_x, ycoord = track_y, tcoord = track_t
)
stopifnot(identical(
  point[["satellite date"]],
  c("2018-02-01T12:00:00Z", "2018-03-01T12:00:00Z", "2018-07-01T12:00:00Z")
))
stopifnot(all(point$n == 1))
expected <- sst_formula(point[["satellite date"]], grid_centre(track_y), grid_centre(track_x))
stopifnot(max(abs(point[["mean analysed_sst"]] - expected)) < 1e-6)
ok("rxtracto(): a track of three points returns the formula values and dates")

# a 0.2 degree box averages 20 cells; the surface is nearly flat there
boxed <- rxtracto(
  dataInfo, parameter = parameter,
  xcoord = track_x, ycoord = track_y, tcoord = track_t, xlen = 0.2, ylen = 0.2
)
stopifnot(all(boxed$n > 1))
stopifnot(max(abs(boxed[["mean analysed_sst"]] - expected)) < 0.05)
stopifnot(all(boxed[["stdev analysed_sst"]] < 0.05))
ok("rxtracto(xlen, ylen): a box of cells is averaged")

# --- plotdap (#52): add_griddap reads the griddap object -------------------
# plotdap takes only $summary$dim$time/latitude/longitude$vals and $data from
# the object (names hard-coded), so the dataset's axis names matter (#59).
suppressMessages(library(plotdap))
grd <- suppressMessages(griddap(
  dataInfo,
  time = c("2018-01-01T12:00:00Z", "2018-03-01T12:00:00Z"),
  latitude = c(17, 17.5), longitude = c(195, 195.5)
))
plot <- suppressMessages(add_griddap(plotdap("base"), grd, ~analysed_sst))
stopifnot(inherits(plot, "plotdap"))
ok("plotdap: add_griddap() accepts the griddap object")

rast <- plotdap:::get_raster(grd, ~analysed_sst)
lats <- sort(unique(grd$data$latitude), decreasing = TRUE)
lons <- sort(unique(grd$data$longitude))
ext <- raster::extent(rast)
stopifnot(raster::nlayers(rast) == 3, dim(rast)[1:2] == c(length(lats), length(lons)))
stopifnot(abs(ext@xmin - min(lons)) < 1e-6, abs(ext@xmax - max(lons)) < 1e-6)
stopifnot(abs(ext@ymin - min(lats)) < 1e-6, abs(ext@ymax - max(lats)) < 1e-6)
layer_times <- sort(unique(grd$data$time))
for (k in seq_along(layer_times)) {
  # raster cells run from the top-left: latitude north to south, then longitude
  cells <- expand.grid(lon = lons, lat = lats)
  want <- sst_formula(layer_times[k], cells$lat, cells$lon)
  stopifnot(max(abs(raster::values(rast)[, k] - want)) < 1e-6)
}
ok("plotdap: get_raster() values match the formula, one layer per time")

cat("\nAll tutorial checks passed\n")
