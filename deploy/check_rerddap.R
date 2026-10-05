# Check a running deploy/server.py from R, the way rerddap users call it.
# Usage: Rscript deploy/check_rerddap.R http://127.0.0.1:9100
library(rerddap)

args <- commandArgs(trailingOnly = TRUE)
base <- if (length(args) > 0) sub("/+$", "", args[1]) else "http://127.0.0.1:9100"
url <- paste0(base, "/erddap/")
# rerddap caches responses on disk; a stale cache would hide server changes.
cache_delete_all()

timed <- function(msg, expr) {
  t <- system.time(val <- force(expr))[["elapsed"]]
  cat(sprintf("ok   %6.2fs  %s\n", t, msg))
  invisible(val)
}

i <- timed("info(cefi_nep_hindcast_daily)", info("cefi_nep_hindcast_daily", url = url))
stopifnot("tos" %in% i$variables$variable_name)

res <- timed("griddap() tos subset", griddap(
  "cefi_nep_hindcast_daily", url = url,
  time = c("2024-07-01", "2024-07-03"),
  lat = c(45, 46), lon = c(230, 231),
  fields = "tos"
))
stopifnot(nrow(res$data) > 0, any(is.finite(res$data$tos)))
cat("     rows:", nrow(res$data), " mean tos:", round(mean(res$data$tos, na.rm = TRUE), 3), "\n")

j <- timed("info(gobai_o2_monthly)", info("gobai_o2_monthly", url = url))
stopifnot("oxy" %in% j$variables$variable_name)

res <- timed("griddap() oxy subset", griddap(
  "gobai_o2_monthly", url = url,
  time = c("2020-01-15", "2020-03-15"),
  pres = c(10, 20), lat = c(0, 5), lon = c(180, 185),
  fields = "oxy"
))
stopifnot(nrow(res$data) > 0, any(is.finite(res$data$oxy)))
cat("     rows:", nrow(res$data), " mean oxy:", round(mean(res$data$oxy, na.rm = TRUE), 3), "\n")
