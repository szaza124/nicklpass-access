#!/bin/bash

echo "Killing any process on port 8000..."
PID=$(lsof -t -i:8000)
if [ ! -z "$PID" ]; then
  kill -9 $PID 2>/dev/null
fi

echo "Killing uvicorn and python processes..."
pkill -9 -f uvicorn 2>/dev/null
pkill -9 -f python 2>/dev/null
pkill -9 -f python3 2>/dev/null

echo "Activating venv..."
source venv/bin/activate

echo "Starting server..."
python -m uvicorn main:app --reload