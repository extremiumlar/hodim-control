FROM node:20-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json* /app/
RUN npm install
COPY web /app
RUN npm run build

FROM nginx:alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
