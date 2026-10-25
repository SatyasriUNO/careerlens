#!/usr/bin/env bash
# CareerLens - starts backend and frontend together. Press Ctrl+C once to stop both.
cd "$(dirname "$0")" || exit 1

if [ ! -f backend/venv/bin/activate ]; then
  echo "Backend is not set up yet. Follow README.md section 3 first."; exit 1
fi
if [ ! -d frontend/node_modules ]; then
  echo "Frontend is not set up yet. Follow README.md section 4 first."; exit 1
fi

trap 'echo; echo "Stopping CareerLens..."; kill 0' INT TERM EXIT

(cd backend && source venv/bin/activate && uvicorn main:app --port 8000) &
(cd frontend && npm run dev) &

sleep 10
(xdg-open http://localhost:5173 || open http://localhost:5173) >/dev/null 2>&1 &
echo "CareerLens is running at http://localhost:5173  (Ctrl+C to stop)"
wait
