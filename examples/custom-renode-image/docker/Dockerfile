# A "patched" Renode: the stock image plus a marker file. A real patch would add a
# rebuilt Renode, extra peripherals, tools, ...
ARG RENODE_VERSION=1.16.1
FROM antmicro/renode:${RENODE_VERSION}
USER root
RUN echo "patched by examples/custom-renode-image" > /opt/hector-patched
USER developer
