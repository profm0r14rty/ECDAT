# ECDAT web image — serves the React + Vite + TS dashboard.
#
# Multi-stage build:
#   1. `build` — installs dependencies and compiles the Vite production bundle
#      (tsc -b && vite build).
#   2. `runtime` — nginx serves the static bundle and reverse-proxies /api and
#      /health to the `api` service (see nginx.conf).
#
# The bundle keeps the default same-origin `VITE_API_BASE_URL`, so no runtime
# env substitution is needed: the browser talks to nginx, nginx forwards to
# the backend. This is the simplest configuration to get right in a container
# (see nginx.conf header for the rationale).
#
# Build context is ./frontend (see docker-compose.yml: build: ./frontend).

# ---- Stage 1: build the Vite production bundle ----------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Install deps first (cache-friendly): package files rarely change vs src/.
COPY package.json package-lock.json ./
RUN npm ci

# Copy source + config, then compile.
COPY . .
RUN npm run build

# ---- Stage 2: nginx static server + API reverse proxy ---------------------
FROM nginx:1.27-alpine AS runtime

# Serve the compiled bundle.
COPY --from=build /app/dist /usr/share/nginx/html

# Replace default config with ours (serves SPA + proxies /api, /health).
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
