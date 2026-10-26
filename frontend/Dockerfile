# syntax=docker/dockerfile:1
# 1) Build the React app
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# 2) Caddy serves the static files and reverse-proxies /api to the backend (automatic HTTPS in production).
FROM caddy:2-alpine
COPY --from=build /src/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
