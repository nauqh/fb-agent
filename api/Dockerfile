# The bgutil PO token server, built first because the API stage below copies
# out of this one.
#
# The plugin (bgutil-ytdlp-pot-provider, in pyproject) only *fetches* tokens;
# something must generate them. That is this server: an Express app on
# 127.0.0.1:4416 which runs Botguard in node. It has to share the container
# because a PO token is bound to the IP it was minted from — a second Railway
# service would mint tokens for the wrong egress and be useless here.
#
# There is no npm package: the server ships as a git clone + `npm ci` + `tsc`.
# The tag must match the plugin's version (they release together).
FROM node:22-bookworm-slim AS pot-server
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch 2.0.0 \
      https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /bgutil \
 && cd /bgutil/server && npm ci && npx tsc

# The API. Build context is `api/` — also Railway's Root Directory.
# 3.11 matches api/.python-version, which is copied in; on a mismatch uv
# downloads its own 3.11 and this image's interpreter goes unused.
FROM python:3.11-slim

# The two binaries the YouTube tool shells out to, neither of which the slim
# image carries. Both were missing in production and both fail late, in a job,
# rather than at boot:
#
#   ffmpeg        `process.py` trims and concats with it as a subprocess.
#   (node, below) yt-dlp's JS-challenge solver runs on it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the application into the container.
COPY . /app

# Install the application dependencies.
WORKDIR /app
RUN uv sync --frozen --no-cache --no-dev

# node >= 20 is what Botguard needs; Debian's nodejs (18) is older, so the
# runtime binary comes from the image the server was built with — copied into
# /usr/local/bin, which PATH searches before /usr/bin. Same binary that ran
# `tsc`, so the canvas/native modules built in the stage above are guaranteed
# loadable here.
COPY --from=pot-server /usr/local/bin/node /usr/local/bin/node
COPY --from=pot-server /bgutil/server /opt/bgutil-server

# Run the application.
#
# The token server starts in the background first; if it dies, downloads
# degrade to tokenless with a plugin warning rather than an outage, so a
# supervisor for one helper process is not bought. Its log goes to the same
# stdout Railway shows.
#
# 8000, not 80: ports below 1024 are privileged, so 80 works only as root and
# fails with a bare PermissionError the day this grows a non-root user.
# Railway must be told this port — set PORT=8000 in the service variables.
#
# --workers 1 is a correctness requirement, not a default worth inheriting.
# `generate.sweep_stranded` marks *every* row at `generating` as failed on
# startup, which is only safe while one process can own them; a second worker
# booting would kill a live run mid-generate. `init_db()` also runs
# `alembic upgrade head` here, which wants one process migrating, not four.
EXPOSE 8000
CMD ["sh", "-c", "node /opt/bgutil-server/build/main.js --port 4416 & exec /app/.venv/bin/fastapi run app/main.py --host 0.0.0.0 --port 8000 --workers 1"]
