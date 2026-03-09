#!/bin/bash
# Get auth token
token=$(curl -s -X POST http://localhost:8500/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

echo "Token: ${token:0:20}..."

# Get watcher status
echo "Watcher Status:"
curl -s http://localhost:8500/api/v1/files/watcher/status \
  -H "Authorization: Bearer $token" | jq

# Get list of files
echo ""
echo "Files in Database:"
curl -s http://localhost:8500/api/v1/files \
  -H "Authorization: Bearer $token" | jq '.total, .files[].filename'
