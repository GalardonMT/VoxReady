FROM node:22-alpine AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM dependencies AS build

COPY . .

# Build arguments para variables publicas de Next.js (Azure y API)
ARG NEXT_PUBLIC_AUTH_MODE
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_AZURE_TENANT_ID
ARG NEXT_PUBLIC_AZURE_CLIENT_ID
ARG NEXT_PUBLIC_AZURE_AUTHORITY
ARG NEXT_PUBLIC_REDIRECT_URI
ARG NEXT_PUBLIC_AZURE_REDIRECT_URI
ARG NEXT_PUBLIC_AZURE_API_SCOPE
ARG NEXT_PUBLIC_DEV_AUTH=false

ENV NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_AZURE_TENANT_ID=$NEXT_PUBLIC_AZURE_TENANT_ID \
    NEXT_PUBLIC_AZURE_CLIENT_ID=$NEXT_PUBLIC_AZURE_CLIENT_ID \
    NEXT_PUBLIC_AZURE_AUTHORITY=$NEXT_PUBLIC_AZURE_AUTHORITY \
    NEXT_PUBLIC_REDIRECT_URI=${NEXT_PUBLIC_REDIRECT_URI:-$NEXT_PUBLIC_AZURE_REDIRECT_URI} \
    NEXT_PUBLIC_AZURE_REDIRECT_URI=${NEXT_PUBLIC_REDIRECT_URI:-$NEXT_PUBLIC_AZURE_REDIRECT_URI} \
    NEXT_PUBLIC_AZURE_API_SCOPE=$NEXT_PUBLIC_AZURE_API_SCOPE \
    NEXT_PUBLIC_DEV_AUTH=$NEXT_PUBLIC_DEV_AUTH

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM dependencies AS test
COPY src ./src
COPY tests ./tests
CMD ["sh", "-c", "node --experimental-strip-types tests/routeAccess.test.mjs && node --experimental-strip-types tests/mediaCheck.test.mjs"]

FROM nginx:1.28-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/out /usr/share/nginx/html

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/login/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
