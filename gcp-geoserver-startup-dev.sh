#!/bin/bash
set -e

apt-get update -q
apt-get install -y -q docker.io
systemctl enable --now docker

docker pull kartoza/geoserver:2.25.2
mkdir -p /opt/geoserver_data

docker rm -f geoserver || true
docker run -d \
  --name geoserver \
  --restart=always \
  -p 8080:8080 \
  -v /opt/geoserver_data:/opt/geoserver/data_dir \
  -e GEOSERVER_ADMIN_USER=admin \
  -e GEOSERVER_ADMIN_PASSWORD=geoserver \
  -e INITIAL_MEMORY=512M \
  -e MAXIMUM_MEMORY=2G \
  -e ADDITIONAL_JAVA_STARTUP_OPTIONS='-XX:ParallelGCThreads=1 -XX:ConcGCThreads=1' \
  kartoza/geoserver:2.25.2
