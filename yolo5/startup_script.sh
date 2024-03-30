#!/bin/bash

# ARGS
ARG=$1
VER="latest"

# Update repositories
sudo apt update

# Install docker-engine
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Cleanup script
rm -f get-docker.sh

# Cleanup old container
sudo docker kill yolo-aws
sudo docker rm yolo-aws

# Run docker container for Polybot
sudo docker run -d --restart=always --name=yolo-aws selotapetm/yoloaws:${ARG:-$VER}