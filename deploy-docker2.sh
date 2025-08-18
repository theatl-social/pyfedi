#!/bin/bash

export DOCKER_BUILDKIT=1
docker compose down
git pull && docker compose up -d --build
