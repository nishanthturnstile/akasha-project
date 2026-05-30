# Akasha frontend — OPTIONAL standalone image (dev / alternative hosting).
#
# In production the SPA is built and served by the `web` gateway
# (infra/gateway/Dockerfile). This standalone image is only for previewing the
# frontend on its own.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
COPY yarn.loc[k] ./
RUN yarn install --frozen-lockfile || yarn install
COPY . ./
RUN yarn build

FROM node:20-alpine
WORKDIR /app
RUN yarn global add serve@14.2.4
COPY --from=build /app/dist ./dist
EXPOSE 4173
CMD ["sh", "-c", "serve -s dist -l ${PORT:-4173}"]
