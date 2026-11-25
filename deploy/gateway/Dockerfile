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

# Placeholder defaults for the downstream-app upstreams (#1274). The
# template references these env vars, and the stock envsubst runner
# substitutes ONLY defined variables — an undefined ${TIMETABLE_HOST}
# would render literally and nginx would fail config load (gateway-wide
# outage). These placeholders keep the rendered config valid in an
# environment that hasn't opted an app into the gateway yet: the .invalid
# name never resolves, so those paths 502 harmlessly while the rest of
# the dispatch works. Service variables of the same names override these
# (env > image ENV), which is exactly how an environment wires an app in:
# set TIMETABLE_HOST/TIMETABLE_PORT etc. on the gateway service, redeploy.
ENV TIMETABLE_HOST=downstream-unrouted.invalid \
    TIMETABLE_PORT=8080 \
    APPHOST_HOST=downstream-unrouted.invalid \
    APPHOST_PORT=8080 \
    ADMIN_HOST=downstream-unrouted.invalid \
    ADMIN_PORT=8080 \
    PROFILE_HOST=downstream-unrouted.invalid \
    PROFILE_PORT=8080 \
    CLASSROOM_HOST=downstream-unrouted.invalid \
    CLASSROOM_PORT=8080

# NOTE: this file is named campus-gateway.conf.template, NOT the
# conventional default.conf.template, on purpose. Railway's incremental
# snapshot builder once patch-merged a changed default.conf.template
# into a garbled hybrid of old and new versions (2026-10-29, #995) —
# a fresh filename forces a wholesale copy instead of a diff-apply.
#
# Snapshot-proofing: the incremental snapshot may still carry stale
# config/templates under ANY of these paths (it once resurrected the old
# default.conf.template by content-hash collision, and the stock envsubst
# runner renders EVERY *.template — two rendered server blocks on the
# same port, first-wins on requests). Remove them all before copying
# exactly one template.
RUN rm -f /etc/nginx/templates/default.conf.template \
          /etc/nginx/templates/campus-gateway.conf.template \
          /etc/nginx/conf.d/default.conf \
          /etc/nginx/conf.d/campus-gateway.conf
COPY campus-gateway.conf.template /etc/nginx/templates/campus-gateway.conf.template
