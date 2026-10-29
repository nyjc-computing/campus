# Campus edge gateway (issue #995): nginx path-dispatching reverse proxy
# serving campus.auth, campus.api and campus.audit under one hostname.
#
# The nginx image's entrypoint renders /etc/nginx/templates/*.template
# into /etc/nginx/conf.d/*.conf via envsubst at startup, using only the
# variables present in the environment (nginx runtime variables such as
# $host are left alone). Our template overwrites the stock default.conf,
# so this container serves exactly the campus dispatch config.
#
# Resolver: the stock 15-local-resolvers.envsh (enabled by setting
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS on the service) exports
# NGINX_LOCAL_RESOLVERS from /etc/resolv.conf, bracketing IPv6
# nameservers — the form nginx's resolver directive requires. Do not
# hand-roll this: the resolver address is IPv6 (Railway private
# networking), and a bare literal misparses ("invalid port in resolver").
FROM nginx:1.29-alpine

COPY default.conf.template /etc/nginx/templates/default.conf.template

# Build-time provenance: prints which upstream config got baked into the
# image, so a stale build is visible in the build log (Railway's
# incremental snapshot builds once shipped a stale template — only
# README.md showed as modified in its snapshot diff, 2026-10-29 #995).
RUN grep -nE "set \\\$.*_upstream" /etc/nginx/templates/default.conf.template || true
