#!/bin/sh
set -e
if [ ! -f /ansible/.ssh/id_rsa ]; then
  mkdir -p /ansible/.ssh
  ssh-keygen -t ed25519 -f /ansible/.ssh/id_rsa -N ""
fi
cp /ansible/.ssh/id_rsa.pub /ssh_pubkey/id_rsa.pub
# Start metrics exporter (port 9101) for Prometheus scrape
python3 /ansible/metrics_exporter.py &
exec "$@"
