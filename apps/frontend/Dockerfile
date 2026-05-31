# Akasha frontend — OPTIONAL standalone image (dev / alternative hosting).
#
# In production the SPA is built and served by the `web` gateway
# (infra/gateway/Dockerfile). This standalone image is only for previewing the
# frontend on its own.
FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare yarn@1.22.22 --activate
COPY package.json ./
COPY yarn.lock ./
RUN yarn install --frozen-lockfile
COPY . ./
RUN yarn build

FROM node:24-alpine
WORKDIR /app
RUN corepack enable && corepack prepare yarn@1.22.22 --activate
RUN yarn global add serve@14.2.4
COPY --from=build /app/dist ./dist
EXPOSE 4173
CMD ["sh", "-c", "serve -s dist -l ${PORT:-4173}"]
