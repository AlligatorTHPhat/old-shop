# syntax=docker/dockerfile:1

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# Exact versions from the lockfile; no package lifecycle scripts are executed.
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY . .
RUN npm run build -- --configuration production


# Runs as an unprivileged user (uid 101) and therefore listens on 8080 instead of 80.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
