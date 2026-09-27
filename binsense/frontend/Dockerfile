# Сборка веб-приложения и раздача статики через Caddy (он же терминирует HTTPS).
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
# Caddyfile монтируется из infra/caddy — так его можно править без пересборки образа
EXPOSE 80 443
