#!/bin/bash
# Usage: ./release.sh <version>
# Example: ./release.sh v1.0.0

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <version>"
  exit 1
fi

VERSION=$1
IMAGE_NAME=browser-novnc
DOCKERHUB_USER=xing5

# Build image
docker build -t $IMAGE_NAME:latest .

docker tag $IMAGE_NAME:latest $DOCKERHUB_USER/$IMAGE_NAME:$VERSION
docker tag $IMAGE_NAME:latest $DOCKERHUB_USER/$IMAGE_NAME:latest

echo "Pushing $DOCKERHUB_USER/$IMAGE_NAME:$VERSION ..."
docker push $DOCKERHUB_USER/$IMAGE_NAME:$VERSION

echo "Pushing $DOCKERHUB_USER/$IMAGE_NAME:latest ..."
docker push $DOCKERHUB_USER/$IMAGE_NAME:latest

echo "Release $VERSION published!" 