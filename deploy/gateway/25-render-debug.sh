#!/bin/sh
# Runs after 20-envsubst-on-templates.sh (sort order): print the
# rendered config's upstream lines to the deploy log. This is the
# ground truth of what THIS container's nginx loaded — added while
# chasing the stale-config 502s (#995); remove once the gateway is
# verified end-to-end.
echo "=== rendered upstream config: ==="
grep -nE "set .*_upstream|resolver |listen " /etc/nginx/conf.d/default.conf
echo "=== end rendered upstream config ==="
