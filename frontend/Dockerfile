FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_ENABLE_LOCAL_DASHBOARD=false
ENV VITE_ENABLE_LOCAL_DASHBOARD=$VITE_ENABLE_LOCAL_DASHBOARD
ARG VITE_ALLOW_SIGNUP=false
ENV VITE_ALLOW_SIGNUP=$VITE_ALLOW_SIGNUP
RUN npm run build

FROM nginx:1.30.6-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
