#!/usr/bin/env bash
# Kill everything and restart both servers clean.
# Run from d:/dev/crucible: bash restart.sh

echo "Stopping all Python and Node processes..."
taskkill //F //IM python.exe 2>/dev/null || true
taskkill //F //IM node.exe 2>/dev/null || true
sleep 1

echo "Clearing pyc cache..."
find forge/__pycache__ -name "*.pyc" -delete 2>/dev/null || true
find core/__pycache__ -name "*.pyc" -delete 2>/dev/null || true

echo "Starting backend on :8000..."
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &

echo "Starting frontend on :5173..."
(cd web && npm run dev) &

sleep 5
curl -s http://localhost:8000/ | python -c "import sys,json; print('Backend:', json.load(sys.stdin).get('name'))"
echo "Frontend: http://localhost:5173/forge"
