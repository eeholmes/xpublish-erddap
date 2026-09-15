library(rerddap)
url <- "http://127.0.0.1:9500/erddap/"

cat("1) info()\n")
i <- info("air_temp", url = url)
print(i)

cat("\n2) griddap()\n")
res <- griddap(
  "air_temp", url = url,
  time = c("2013-01-05", "2013-01-08"),
  lat = c(40, 50),
  lon = c(240, 250),
  fields = "air"
)
cat("   summary:\n"); print(dim(res$data)); print(head(res$data))
