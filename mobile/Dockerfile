FROM forthecommunity/flutter:3.50.0 AS build

WORKDIR /src
COPY pubspec.yaml pubspec.lock* ./
RUN flutter --version && dart --version && flutter pub get
COPY . .

ARG API_BASE_URL=http://localhost:8000
ARG SUPABASE_URL=
ARG SUPABASE_PUBLISHABLE_KEY=
RUN flutter build web --release \
    --dart-define=API_BASE_URL=${API_BASE_URL} \
    --dart-define=SUPABASE_URL=${SUPABASE_URL} \
    --dart-define=SUPABASE_PUBLISHABLE_KEY=${SUPABASE_PUBLISHABLE_KEY}

FROM nginx:stable-alpine AS runtime
COPY docker/nginx-spa.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/build/web /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=20s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
