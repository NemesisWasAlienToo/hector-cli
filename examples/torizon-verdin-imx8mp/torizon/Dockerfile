FROM debian:trixie-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        e2fsprogs fdisk zstd xz-utils gzip u-boot-tools device-tree-compiler python3 tar \
    && rm -rf /var/lib/apt/lists/*
