#!/bin/bash

echo "Killing uvicorn and python processes..."
pkill -9 -f uvicorn
pkill -9 -f python

echo "Activating venv..."
source venv/bin/activate

echo "Starting server..."
python -m uvicorn main:app --reload