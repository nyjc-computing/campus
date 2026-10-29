#!/bin/sh
# Export the variables the gateway nginx template needs before the base
# image's envsubst runner renders it (docker-entrypoint.d scripts run in
# sort order: this file sorts before 20-envsubst-on-templates.sh).
#
# RESOLVER_IP: Railway re-issues service private IPs on every redeploy,
# and nginx resolves literal proxy_pass hostnames once at config load —
# a static upstream would 502 after the next backend deploy. The gateway
# therefore re-resolves upstreams per request through the container's
# own resolver (see default.conf.template).
#
# PORT: Railway injects it at runtime; keep a fallback so a missing
# variable fails at request time, never at config render time.
RESOLVER_IP="$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf)"
export RESOLVER_IP
export PORT="${PORT:-8080}"
