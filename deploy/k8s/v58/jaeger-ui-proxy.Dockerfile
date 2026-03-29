FROM node:24-alpine AS build

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY
ENV NO_PROXY=$NO_PROXY
ENV http_proxy=$HTTP_PROXY
ENV https_proxy=$HTTPS_PROXY
ENV no_proxy=$NO_PROXY

WORKDIR /src
COPY third_party/jaeger-ui/ ./
RUN if [ -n "$HTTP_PROXY" ]; then npm config set proxy "$HTTP_PROXY"; fi
RUN if [ -n "$HTTPS_PROXY" ]; then npm config set https-proxy "$HTTPS_PROXY"; fi
RUN npm ci --ignore-scripts
RUN cd packages/plexus && NODE_ENV=production npx webpack --mode production --config webpack.layout-worker.config.js
RUN cd packages/jaeger-ui && NODE_ENV=production REACT_APP_VSN_STATE='{"version":"2.16.0","snapshot":"openagentic-v58"}' npx vite build

FROM nginx:1.27-alpine

COPY deploy/k8s/v58/nginx.default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/packages/jaeger-ui/build/ /usr/share/nginx/html/
