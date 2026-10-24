#!/bin/sh
# Only a launcher. Business HTTP/SSE never passes through CGI.
set -eu
base=/var/apps/fnos_music_hub/target
printf 'Content-Type: text/html; charset=utf-8\r\nCache-Control: no-store\r\n\r\n'
cat "$base/ui/launch.html"
