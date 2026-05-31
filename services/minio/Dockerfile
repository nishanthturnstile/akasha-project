# Akasha MinIO — Railway wrapper.
# The upstream image needs an explicit server command; Railway image services do
# not provide a portable repo-level command file, so this tiny wrapper keeps the
# start command versioned with the rest of the deployment config.
FROM minio/minio:RELEASE.2025-09-07T16-13-09Z

EXPOSE 9000
EXPOSE 9001

CMD ["server", "/data", "--console-address", ":9001"]
