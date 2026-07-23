#!/usr/bin/env sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
APP_USER="${APP_USER:-xona}"
APP_GROUP="${APP_GROUP:-xona}"
CONFIG_DIR="${CONFIG_DIR:-/config}"

require_numeric_id() {
    name="$1"
    value="$2"
    case "$value" in
        ""|*[!0-9]*)
            echo "$name must be a numeric id" >&2
            exit 1
            ;;
    esac
}

group_name_for_gid() {
    getent group "$1" | awk -F: 'NR == 1 { print $1 }'
}

user_name_for_uid() {
    getent passwd "$1" | awk -F: 'NR == 1 { print $1 }'
}

ensure_group() {
    group_name="$(group_name_for_gid "$PGID")"
    if [ -n "$group_name" ]; then
        return
    fi

    group_name="$APP_GROUP"
    if getent group "$group_name" >/dev/null 2>&1; then
        group_name="${APP_GROUP}-${PGID}"
    fi
    groupadd --gid "$PGID" "$group_name"
}

ensure_user() {
    user_name="$(user_name_for_uid "$PUID")"
    if [ -n "$user_name" ]; then
        return
    fi

    group_name="$(group_name_for_gid "$PGID")"
    user_name="$APP_USER"
    if getent passwd "$user_name" >/dev/null 2>&1; then
        user_name="${APP_USER}-${PUID}"
    fi
    useradd \
        --uid "$PUID" \
        --gid "$group_name" \
        --home-dir "$CONFIG_DIR" \
        --no-create-home \
        --shell /usr/sbin/nologin \
        "$user_name"
}

run_as_app() {
    if [ "$(id -u)" = "$PUID" ] && [ "$(id -g)" = "$PGID" ]; then
        "$@"
    elif command -v setpriv >/dev/null 2>&1; then
        setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
    elif command -v gosu >/dev/null 2>&1; then
        gosu "$PUID:$PGID" "$@"
    elif command -v su-exec >/dev/null 2>&1; then
        su-exec "$PUID:$PGID" "$@"
    else
        echo "setpriv, gosu, or su-exec is required to drop privileges" >&2
        exit 1
    fi
}

exec_as_app() {
    if [ "$(id -u)" = "$PUID" ] && [ "$(id -g)" = "$PGID" ]; then
        exec "$@"
    elif command -v setpriv >/dev/null 2>&1; then
        exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
    elif command -v gosu >/dev/null 2>&1; then
        exec gosu "$PUID:$PGID" "$@"
    elif command -v su-exec >/dev/null 2>&1; then
        exec su-exec "$PUID:$PGID" "$@"
    else
        echo "setpriv, gosu, or su-exec is required to drop privileges" >&2
        exit 1
    fi
}

require_numeric_id PUID "$PUID"
require_numeric_id PGID "$PGID"

if [ "$(id -u)" = "0" ]; then
    ensure_group
    ensure_user
    mkdir -p "$CONFIG_DIR"
    chown -R "$PUID:$PGID" "$CONFIG_DIR"
fi

run_as_app python -m backend.app.db.migrations
exec_as_app "$@"
