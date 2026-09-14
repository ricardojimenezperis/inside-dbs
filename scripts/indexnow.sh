#!/usr/bin/env bash
# Submit every URL in the live sitemap to IndexNow (Bing, Yandex, Seznam, Naver…).
# Run after a deploy; the key file static/<key>.txt must be served at the site root.
set -euo pipefail
HOST="ricardojimenezperis.com"
KEY="${INDEXNOW_KEY:?set INDEXNOW_KEY}"
SITEMAP="https://${HOST}/sitemap.xml"

urls=$(curl -fsSL "$SITEMAP" | grep -o '<loc>[^<]*</loc>' | sed 's/<loc>//;s#</loc>##')
count=$(printf '%s\n' "$urls" | grep -c . || true)
if [ "$count" -eq 0 ]; then echo "no URLs found in $SITEMAP"; exit 1; fi

json=$(printf '%s\n' "$urls" | python3 -c 'import json,sys,os; u=[l.strip() for l in sys.stdin if l.strip()]; h=os.environ["H"]; k=os.environ["INDEXNOW_KEY"]; print(json.dumps({"host":h,"key":k,"keyLocation":f"https://{h}/{k}.txt","urlList":u}))' H="$HOST")

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST 'https://api.indexnow.org/indexnow' \
  -H 'Content-Type: application/json; charset=utf-8' -d "$json")
echo "IndexNow: HTTP $code for $count URLs"
case "$code" in 200|202) exit 0;; *) exit 1;; esac
