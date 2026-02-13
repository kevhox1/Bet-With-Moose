#!/bin/bash
# Start all services for local development
set -e
cd "$(dirname "$0")/.."
docker-compose up --build
