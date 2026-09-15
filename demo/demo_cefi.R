library(rerddap)
url <- "http://127.0.0.1:9600/erddap/"

i <- info("cefi_nep_hindcast_daily", url = url)
print(i)

cat("\n-- griddap() --\n")
res <- griddap("cefi_nep_hindcast_daily", url = url,
               time = c("2024-07-01", "2024-07-05"),
               lat = c(45, 47), lon = c(230, 232),
               fields = "tos")
cat("rows:", nrow(res$data), "\n")
print(head(res$data, 4))
cat("mean tos:", round(mean(res$data$tos, na.rm = TRUE), 3), "\n")
