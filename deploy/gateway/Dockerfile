# Campus edge gateway (issue #995): nginx path-dispatching reverse proxy
# serving campus.auth, campus.api and campus.audit under one hostname.
#
# The nginx image's entrypoint renders /etc/nginx/templates/*.template
# into /etc/nginx/conf.d/*.conf via envsubst at startup, using only the
# variables present in the environment (nginx runtime variables such as
# $host are left alone). Our template overwrites the stock default.conf,
# so this container serves exactly the campus dispatch config.
FROM nginx:1.29-alpine

# Sourced by the entrypoint before 20-envsubst-on-templates.sh (sort
# order): exports RESOLVER_IP (from /etc/resolv.conf) and a PORT
# fallback so the template renders. MUST be a .envsh file — the
# entrypoint only SOURCES .envsh files, so their exports reach the
# envsubst runner; executable .sh files run as child processes whose
# exports are lost (two deploy findings, see #995).
COPY 15-gateway-env.envsh /docker-entrypoint.d/15-gateway-env.envsh
COPY default.conf.template /etc/nginx/templates/default.conf.template
