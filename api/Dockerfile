# The API. Build context is `api/` — also Railway's Root Directory.
# 3.11 matches api/.python-version, which is copied in; on a mismatch uv
# downloads its own 3.11 and this image's interpreter goes unused.
FROM python:3.11-slim

# The two binaries the YouTube tool shells out to, neither of which the slim
# image carries. Both were missing in production and both fail late, in a job,
# rather than at boot:
#
#   ffmpeg  `process.py` trims and concats with it as a subprocess.
#   node    `sources.py` pins yt-dlp's JS-challenge solver to the node runtime
#           (`js_runtimes={"node": {}}`). Without it a bot-challenged video
#           cannot be solved, and the rotation burns all three player clients
#           before reporting the generic "session expired" line.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg nodejs ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy the application into the container.
COPY . /app

# Install the application dependencies.
WORKDIR /app
RUN uv sync --frozen --no-cache --no-dev

# Run the application.
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
CMD ["/app/.venv/bin/fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
