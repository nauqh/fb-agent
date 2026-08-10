# The API. Build context is `api/` — also Railway's Root Directory.
# 3.11 matches api/.python-version, which is copied in; on a mismatch uv
# downloads its own 3.11 and this image's interpreter goes unused.
FROM python:3.11-slim

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
