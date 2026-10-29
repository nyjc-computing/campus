# Campus edge gateway (issue #995): nginx path-dispatching reverse proxy
# serving campus.auth, campus.api and campus.audit under one hostname.
#
# The nginx image's entrypoint renders /etc/nginx/templates/*.template
# into /etc/nginx/conf.d/*.conf via envsubst at startup, using only the
# variables present in the environment (nginx runtime variables such as
# $host are left alone). Our template overwrites the stock default.conf,
# so this container serves exactly the campus dispatch config.
FROM nginx:1.29-alpine

# Must be EXECUTABLE and named .envsh. The entrypoint checks the exec
# bit first, then dispatches by extension: executable *.sh runs as a
# child process (exports lost), executable *.envsh is SOURCED (exports
# propagate to the envsubst runner), non-executable files are ignored.
# Deploy findings #2 and #3, see #995.
COPY 15-gateway-env.envsh /docker-entrypoint.d/15-gateway-env.envsh
RUN chmod +x /docker-entrypoint.d/15-gateway-env.envsh
COPY default.conf.template /etc/nginx/templates/default.conf.template
