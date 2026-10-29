#!/bin/sh
# Runs after 20-envsubst-on-templates.sh (sort order): dump the rendered
# config in full, plus the template it came from and the conf.d listing,
# into the deploy log. Ground truth for the stale-config 502 chase
# (#995); remove once the gateway is verified end-to-end.
echo "=== ls /etc/nginx/conf.d/ ==="
ls -la /etc/nginx/conf.d/
echo "=== rendered /etc/nginx/conf.d/default.conf ==="
cat /etc/nginx/conf.d/default.conf
echo "=== template /etc/nginx/templates/default.conf.template (first 70 lines) ==="
head -70 /etc/nginx/templates/default.conf.template
echo "=== end dumps ==="
