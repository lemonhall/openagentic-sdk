FROM nginx:1.27-alpine

COPY deploy/k8s/v58/nginx.default.conf /etc/nginx/conf.d/default.conf
COPY third_party/jaeger-ui/packages/jaeger-ui/build/ /usr/share/nginx/html/
