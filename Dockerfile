# The board in one container: the panel, its REST API and the MCP server the
# plugin talks to, all one process on port 8787.
#
# Built from the checkout, not from a published package: there is no published
# package, and the compose file next to this is how the board is meant to run.
FROM python:3.12-slim

# No .pyc files baked into the image, and logs that reach `docker compose logs`
# the moment they are written rather than when a buffer fills.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# The three files the build backend reads, then the package. pyproject names
# README.md as the long description, so it has to be here for `pip install` to
# succeed at all.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY docker/entrypoint.sh /usr/local/bin/tasktracker-entrypoint
RUN chmod 0755 /usr/local/bin/tasktracker-entrypoint

EXPOSE 8787
ENTRYPOINT ["tasktracker-entrypoint"]
