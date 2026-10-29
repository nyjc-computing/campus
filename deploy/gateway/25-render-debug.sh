#!/bin/sh
# Runs after 20-envsubst-on-templates.sh (sort order): dump the rendered
# config in full, plus the template it came from and the conf.d listing,
# into the deploy log. Ground truth for the stale-config 502 chase
# (#995); remove once the gateway is verified end-to-end.
echo "=== ls conf.d + templates ==="
ls -la /etc/nginx/conf.d/ /etc/nginx/templates/
echo "=== rendered /etc/nginx/conf.d/campus-gateway.conf ==="
cat /etc/nginx/conf.d/campus-gateway.conf
echo "=== template /etc/nginx/templates/campus-gateway.conf.template (first 40 lines) ==="
head -40 /etc/nginx/templates/campus-gateway.conf.template
echo "=== end dumps ==="
