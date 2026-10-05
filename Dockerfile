# progettare in a container, for a caller that is not a Python project.
#
# The wheel is built outside and copied in, so the image carries no build
# toolchain and no source tree: what ships is the same artifact attached to
# the release, installed once.
FROM python:3.12-slim

# A blueprint run shells out to three tools besides itself, and a container
# missing any of them fails a run that would have succeeded on the host:
# git (the survey observes the checkout's tree), gh (the issue is loaded
# through the GitHub CLI), and nare (every model session). gh is not in
# Debian's archive, so it comes from GitHub's official apt repository;
# nare is not on PyPI, so it is taken from a pinned nare release wheel.
# The checkout arrives as a host-owned bind mount and the image runs as a
# non-root user, so git's safe.directory is opened to every path: without
# it, git refuses the checkout as dubious and the survey reads nothing.
# NARE_VERSION is passed at build time by the release workflow, so an
# image built from a tag is reproducible: a caller building by hand must
# pass one, e.g. --build-arg NARE_VERSION=2026.10.0.
ARG NARE_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*' \
    && pip install --no-cache-dir \
        "https://github.com/ViviDynamics/nare/releases/download/${NARE_VERSION}/nare-${NARE_VERSION}-py3-none-any.whl"

# Not root. progettare runs model-generated shell commands against a
# surveyed repository, and the container is the containment the README
# tells callers to provide; running those as root inside it would hand
# that away.
RUN useradd --create-home --uid 10001 progettare

ARG WHEEL
COPY ${WHEEL} /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

USER progettare
WORKDIR /work

# No ENTRYPOINT wrapper: `docker run ghcr.io/vividynamics/progettare blueprint
# --issue ...` is the same argv as the CLI, so a caller's command does not
# change shape when it moves into a container.
ENTRYPOINT ["progettare"]
