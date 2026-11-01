#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if [[ ! -x .venv/bin/uvicorn ]]; then
  .venv/bin/pip install -e '.[test]'
fi
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
print 'Daybook: http://127.0.0.1:18765'
exec .venv/bin/uvicorn meridian.app:app --host 127.0.0.1 --port 18765
