# Renode with the Verdin iMX8M Plus / Torizon fixes, built from source:
# upstream master at the commits below + patches/, packaged as a portable build, then layered onto
# the stock image, which provides the runtime pieces (python, Robot Framework, renode-test deps).
#   docker build -t renode-verdin:1.17.0-torizon renode
# The first build takes ~15 min and needs network; later builds hit Docker's cache unless the
# patches change.

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git cmake make gcc g++ automake autoconf libtool pkg-config python3 libglib2.0-dev \
        libicu-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

ARG RENODE_COMMIT=8056b03eb6c0f154a815e122747ec15236464608
ARG RESOURCES_COMMIT=9d7824771f3db67663950cae06f5bb7f89fbf33b
# Submodules are pinned by the renode commit: renode-infrastructure f730546, tlib 5bb3e20
RUN git clone -q https://github.com/renode/renode.git /renode \
    && cd /renode && git checkout -q "$RENODE_COMMIT" \
    && git submodule update -q --init --recursive \
    && ./tools/building/fetch_libraries.sh \
    && git -C lib/resources fetch -q origin "$RESOURCES_COMMIT" \
    && git -C lib/resources checkout -q "$RESOURCES_COMMIT"

COPY patches/ /patches/
RUN cd /renode \
    && git apply /patches/renode.patch \
    && git -C src/Infrastructure apply /patches/renode-infrastructure.patch \
    && git -C src/Infrastructure/src/Emulator/Cores/tlib apply /patches/tlib.patch \
    && ./build.sh -t --no-gui --skip-fetch \
    && mkdir /out && tar -xzf output/packages/renode-*.linux-portable-headless.tar.gz -C /out --strip-components=1

FROM antmicro/renode:1.16.1
USER root
RUN rm -rf /opt/renode
COPY --from=build /out/ /opt/renode/
# Config passed explicitly: hector runs containers as the host UID with HOME=/tmp, so the default
# location isn't stable. Renode creates a lock file next to it, so the directory is world-writable.
# (No comments in renode.config: Renode hangs at startup on them.)
COPY renode.config /etc/renode/config
RUN chmod 1777 /etc/renode && chmod 666 /etc/renode/config \
 && printf '#!/bin/sh\nexec /opt/renode/renode --config /etc/renode/config "$@"\n' > /usr/bin/renode \
 && printf '#!/bin/sh\nexec /opt/renode/renode-test --renode-config /etc/renode/config "$@"\n' > /usr/bin/renode-test \
 && chmod 755 /usr/bin/renode /usr/bin/renode-test
USER developer
