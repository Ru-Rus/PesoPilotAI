FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY app ./app
COPY proxy.ts next.config.ts next-env.d.ts tsconfig.json ./
COPY public ./public
ARG API_URL=http://backend:8000
ENV API_URL=$API_URL
RUN npm run build
FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3010
ENV PORT=3010 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
