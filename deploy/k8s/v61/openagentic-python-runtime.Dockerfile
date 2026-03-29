FROM python:3.12-slim

RUN python -m pip install --no-cache-dir \
    "protobuf<6" \
    "opentelemetry-api<2" \
    "opentelemetry-sdk<2" \
    "opentelemetry-exporter-otlp-proto-http<2"
