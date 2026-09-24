# The browser app as a servable image (H6-A).
#
# Two stages: build the bundle with the toolchain, then ship only the
# static files behind nginx. The runtime image carries no node, no source
# and no package manager.
#
# One image, any environment. Vite bakes `VITE_*` into the bundle at build
# time, which normally means a separate image per deployment; instead the
# build uses placeholders and `docker-entrypoint.sh` writes `/config.js`
# from the container's environment at start-up, which `index.html` loads
# before the bundle. See `src/config.ts` -- it reads through a `loadConfig`
# that takes the environment as an argument, which is what makes this a
# small overlay rather than a refactor.

# ── build ─────────────────────────────────────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
# The responsive-shots harness runs on a developer's machine, never here.
ENV PUPPETEER_SKIP_DOWNLOAD=1
RUN npm ci --no-audit --no-fund

COPY . .
# Typecheck and lint are CI's job (they run on the source, not the image);
# this stage only produces the bundle. The values below are placeholders
# that config.js overrides at runtime -- they exist because config.ts
# refuses to build a config it considers incomplete.
ENV VITE_API_BASE_URL=http://runtime.invalid \
    VITE_SUPABASE_URL=http://runtime.invalid \
    VITE_SUPABASE_PUBLISHABLE_KEY=runtime
RUN npm run build:only

# ── serve ─────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/security-headers.conf /etc/nginx/conf.d/security-headers.conf
COPY nginx/docker-entrypoint.sh /docker-entrypoint.d/40-app-config.sh
COPY --from=build /app/dist /usr/share/nginx/html

# nginx's own image already drops to an unprivileged user for the workers;
# this makes the master unprivileged too. The directories nginx writes to
# at runtime (cache, run) have to be owned accordingly, and the listen
# port must be above 1024 -- hence 8080 in default.conf.
RUN chmod +x /docker-entrypoint.d/40-app-config.sh \
    && touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/cache/nginx /var/run/nginx.pid /usr/share/nginx/html
USER nginx

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
