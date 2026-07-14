#!/bin/sh
set -e
python3 /usr/local/bin/zoekt_index_http_server.py &
exec zoekt-webserver -index /data/index -listen :6070 -rpc
