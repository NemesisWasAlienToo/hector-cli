# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Hector CLI bundled on top of the official Renode image — a single, self-contained
# container with renode + renode-test + the hector CLI, so you can run hector
# without installing anything (not even Python) on the host.
#
# Because Renode already lives in this image, hector runs in-process (--no-docker,
# set via HECTOR_NO_DOCKER): it drives the in-image renode / renode-test directly.
# That means NO Docker socket, NO sibling containers, and NO host-path matching —
# just mount your project and run:
#
#   docker build -t hector-renode .
#   docker run --rm -it -u "$(id -u):$(id -g)" -v "$PWD":"$PWD" -w "$PWD" \
#     hector-renode test
#
# (The bundled `hector-docker` wrapper fills in the UID + mounts for you.)
#
# Match the Renode version to your project's `renode:` version at build time:
#   docker build --build-arg RENODE_VERSION=1.16.1 -t hector-renode:1.16.1 .
#
# Caveat: in --no-docker mode a `shell` test's `image:` is ignored and the
# script runs in THIS image instead; module builds (apt-get + cmake) likewise rely
# on this image's toolchain. For full per-step image isolation, install the CLI
# natively (pip) and let hector launch real per-step containers.

ARG RENODE_VERSION=1.16.1
FROM antmicro/renode:${RENODE_VERSION}

# The Renode image runs as a non-root user; switch to root to install. At run time
# the `hector-docker` wrapper sets -u to the host UID, so output stays host-owned.
USER root

# hector is pure-Python and calls the in-image renode/renode-test as subprocesses.
# Ensure pip + git are present (git: hector clones the Renode source on demand for
# configs that build modules: or use ${RENODE_DIR}).
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-pip git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install the CLI → the `hector` entry-point lands on PATH (renode/renode-test stay
# reachable from the base image's PATH).
COPY . /opt/hector-cli
RUN pip3 install --no-cache-dir /opt/hector-cli \
 || pip3 install --no-cache-dir --break-system-packages /opt/hector-cli

# Renode is in this image, so default to in-process execution: `hector run` /
# `hector test` work with no docker socket. Override per-invocation if ever needed.
ENV HECTOR_NO_DOCKER=1

# The project is bind-mounted from the host (host-owned) while hector may run as an
# arbitrary UID; trust any such checkout so on-demand git clones don't fail on
# "dubious ownership".
RUN git config --system --add safe.directory '*' || true

ENTRYPOINT ["hector"]
CMD ["--help"]
