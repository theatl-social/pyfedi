# syntax=docker/dockerfile:1.4
FROM --platform=$BUILDPLATFORM python:3-alpine AS builder


RUN adduser -D python

RUN apk add --no-cache pkgconfig gcc python3-dev musl-dev tesseract-ocr tesseract-ocr-data-eng postgresql-client bash

COPY --chown=python:python . /app

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install gunicorn

RUN pybabel compile -d app/translations || true

RUN chmod u+x ./entrypoint.sh
RUN chmod u+x ./entrypoint_celery.sh

USER python
ENTRYPOINT ["./entrypoint.sh"]
