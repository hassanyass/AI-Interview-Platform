#!/bin/sh
# Write the browser app's configuration at container start (H6-A).
#
# nginx's official image runs every executable in /docker-entrypoint.d/
# before starting, which is what this hooks into. It produces /config.js,
# the one file that differs between deployments of an identical image --
# so the same artefact that was tested in staging is the one that runs in
# production, rather than a rebuild with different constants baked in.
#
# Only VITE_* names are read, so the container's whole environment is not
# reflected into a file the browser downloads. Nothing secret belongs
# here: everything written is public the moment the page loads, which is
# also true of the values Vite would otherwise bake into the bundle.
set -eu

TARGET="${APP_CONFIG_PATH:-/usr/share/nginx/html/config.js}"

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

{
    printf 'window.__APP_CONFIG__ = {\n'
    # `env` rather than a fixed list: a VITE_* setting added to config.ts
    # keeps working here without editing this script.
    env | grep '^VITE_' | sort | while IFS='=' read -r key value; do
        printf '  "%s": "%s",\n' "$(json_escape "$key")" "$(json_escape "$value")"
    done
    printf '};\n'
} > "$TARGET"

echo "[app-config] wrote $TARGET with $(env | grep -c '^VITE_' || true) VITE_* value(s)"
