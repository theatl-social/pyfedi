#!/bin/bash

# Get the currently logged-in user
USER_NAME=$(whoami)

# List of directories to create and change ownership
DIRS=("pgdata" "media" "logs" "tmp")

for DIR in "${DIRS[@]}"; do
    sudo mkdir -p "$DIR"
    sudo chown -R "$USER_NAME:$USER_NAME" "./$DIR"
done
