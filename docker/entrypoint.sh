#!/bin/sh
# Start the board as whoever owns the home directory it was handed.
#
# The database is a bind mount shared with the plugin's hook, which runs on the
# host as that user. A container writing it as root leaves a tasks.db - or a
# -wal beside it - the hook can no longer open, and the hook swallows every
# failure by design: the board would simply stop filling, with nothing anywhere
# saying why. So the uid is not configured, it is read off the mount.
set -eu

: "${TASKTRACKER_HOME:?TASKTRACKER_HOME must name the board directory}"
: "${TASKTRACKER_OWNER:?TASKTRACKER_OWNER must name the host home directory}"

uid=$(stat -c %u "$TASKTRACKER_OWNER")
gid=$(stat -c %g "$TASKTRACKER_OWNER")

# Docker creates a bind-mount source that does not exist yet, and creates it as
# root. On a first run that is the board directory itself; hand it to the user
# before anything is written into it. Only the directory, never recursively:
# anything already inside was written by the user and already belongs to them.
mkdir -p "$TASKTRACKER_HOME"
if [ "$(stat -c %u "$TASKTRACKER_HOME")" != "$uid" ]; then
    chown "$uid:$gid" "$TASKTRACKER_HOME"
fi

# 0.0.0.0 inside the container is what lets the published port reach it at all.
# What keeps it off the network is the compose file publishing that port on
# 127.0.0.1 only.
exec setpriv --reuid="$uid" --regid="$gid" --clear-groups \
    tasktracker serve --host 0.0.0.0 --port 8787
