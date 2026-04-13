FROM minio/minio:latest
# Use ENTRYPOINT to override — harder to override than CMD
ENTRYPOINT ["minio", "server", "/data", "--console-address", ":9001"]
