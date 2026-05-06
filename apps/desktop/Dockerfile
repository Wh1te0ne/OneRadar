FROM node:22-alpine AS build

WORKDIR /app

COPY apps/desktop/package*.json ./
RUN npm ci

COPY apps/desktop ./

ARG VITE_ONERADAR_DEFAULT_API_URL=http://127.0.0.1:8000
ENV VITE_ONERADAR_DEFAULT_API_URL=$VITE_ONERADAR_DEFAULT_API_URL

RUN npm run build

FROM nginx:1.27-alpine

COPY apps/desktop/nginx.conf /etc/nginx/conf.d/default.conf
COPY apps/desktop/docker-entrypoint.d/10-oneradar-config.sh /docker-entrypoint.d/10-oneradar-config.sh
COPY --from=build /app/dist /usr/share/nginx/html

RUN chmod +x /docker-entrypoint.d/10-oneradar-config.sh

EXPOSE 80
