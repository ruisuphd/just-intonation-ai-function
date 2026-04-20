#!/bin/bash
# Starts both the Python backend and a simple HTTP server for the frontend.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

BACKEND_PORT=5005
FRONTEND_PORT=8000
FINGERPRINT_DB="atepp_filtered_database.pkl"
SCORE_MAPPING="atepp_score_mapping.pkl"
ATEPP_PATH="ATEPP_JI_Dataset/ATEPP-1.2"

BACKEND_PID=""

cleanup() {
    echo ""
    echo "Shutting down..."
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null
        wait "$BACKEND_PID" 2>/dev/null
    fi
    pkill -f "two_stage_server.py" 2>/dev/null
    pkill -f "http.server $FRONTEND_PORT" 2>/dev/null
    echo "Done"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

echo ""
echo "Instant Harmonies - Starting up"
echo ""

# Check required files
echo "Checking files..."

if [ ! -f "$FINGERPRINT_DB" ]; then
    echo "Error: $FINGERPRINT_DB not found. Run: python3 create_filtered_database.py"
    exit 1
fi

if [ ! -f "$SCORE_MAPPING" ]; then
    echo "Error: $SCORE_MAPPING not found. Run: python3 create_filtered_database.py"
    exit 1
fi

if [ ! -d "$ATEPP_PATH" ]; then
    echo "Error: ATEPP dataset not found at $ATEPP_PATH"
    exit 1
fi

if [ ! -f "index.html" ]; then
    echo "Error: index.html not found"
    exit 1
fi

echo "All files found"
echo ""

# Kill any existing servers
pkill -f "two_stage_server.py" 2>/dev/null
pkill -f "http.server $FRONTEND_PORT" 2>/dev/null
sleep 1

echo "Starting backend on port $BACKEND_PORT..."
python3 two_stage_server.py \
    --fingerprint-db "$FINGERPRINT_DB" \
    --score-mapping "$SCORE_MAPPING" \
    --atepp-path "$ATEPP_PATH" \
    --port $BACKEND_PORT &
BACKEND_PID=$!

sleep 4

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend failed to start"
    exit 1
fi

echo "Backend running (PID $BACKEND_PID)"
echo ""
echo "Starting frontend on port $FRONTEND_PORT..."
echo ""
echo "Open http://localhost:$FRONTEND_PORT in your browser"
echo "Press Ctrl+C to stop"
echo ""

python3 -m http.server $FRONTEND_PORT

