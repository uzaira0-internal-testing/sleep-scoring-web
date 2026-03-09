#!/bin/sh
# Generate runtime config from environment variables
cat > /usr/share/nginx/html/config.js << JSEOF
window.__CONFIG__ = {
  basePath: "${BASE_PATH:-}",
};
JSEOF

# Inject base href if BASE_PATH is set
if [ -n "$BASE_PATH" ]; then
    sed -i "s|<head>|<head><base href=\"${BASE_PATH}/\">|" /usr/share/nginx/html/index.html
fi

# Start nginx
exec nginx -g "daemon off;"
