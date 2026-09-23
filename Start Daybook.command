#!/bin/zsh
cd "${0:A:h}/dist"
python3 - <<'PY'
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import subprocess
try:
    server = ThreadingHTTPServer(('127.0.0.1', 4173), SimpleHTTPRequestHandler)
except OSError:
    print('Port 4173 is already in use. If Daybook is already running, open http://localhost:4173. Otherwise stop the other server and try again.')
    input('Press Enter to close.')
    raise SystemExit(1)
print('Daybook: http://localhost:4173\nKeep this window open. Press Control-C to stop.')
subprocess.Popen(['/usr/bin/open', 'http://localhost:4173'])
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
PY
