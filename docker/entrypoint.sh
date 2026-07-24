#!/usr/bin/env sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
APP_USER="${APP_USER:-xona}"
APP_GROUP="${APP_GROUP:-xona}"
CONFIG_DIR="${CONFIG_DIR:-/config}"

log_info() {
    printf '%s | INFO    | entrypoint | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log_error() {
    printf '%s | ERROR   | entrypoint | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

require_numeric_id() {
    name="$1"
    value="$2"
    case "$value" in
        ""|*[!0-9]*)
            log_error "$name must be a numeric id"
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
        log_info "Using existing group gid=$PGID name=$group_name"
        return
    fi

    group_name="$APP_GROUP"
    if getent group "$group_name" >/dev/null 2>&1; then
        group_name="${APP_GROUP}-${PGID}"
    fi
    groupadd --gid "$PGID" "$group_name"
    log_info "Created group gid=$PGID name=$group_name"
}

ensure_user() {
    user_name="$(user_name_for_uid "$PUID")"
    if [ -n "$user_name" ]; then
        log_info "Using existing user uid=$PUID name=$user_name"
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
    log_info "Created user uid=$PUID gid=$PGID name=$user_name"
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
        log_error "setpriv, gosu, or su-exec is required to drop privileges"
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
        log_error "setpriv, gosu, or su-exec is required to drop privileges"
        exit 1
    fi
}

require_numeric_id PUID "$PUID"
require_numeric_id PGID "$PGID"

if [ "$(id -u)" = "0" ]; then
    log_info "Preparing runtime uid=$PUID gid=$PGID config_dir=$CONFIG_DIR"
    ensure_group
    ensure_user
    mkdir -p "$CONFIG_DIR"
    chown -R "$PUID:$PGID" "$CONFIG_DIR"
    log_info "Config directory ready path=$CONFIG_DIR owner=$PUID:$PGID"
fi

log_info "Running database migrations"
run_as_app python -m backend.app.db.migrations
log_info "Starting Xona service command=$*"
exec_as_app "$@"
