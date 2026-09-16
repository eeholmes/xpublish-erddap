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

cat("\nAll tutorial checks passed\n")
