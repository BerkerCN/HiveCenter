#!/usr/bin/env bash
# HiveCenter starter (Linux / macOS)

cd "$(dirname "$0")" || exit 1

echo "Starting HiveCenter..."
echo "Ensuring Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate VENV
source venv/bin/activate

echo "Installing Python dependencies..."
venv/bin/python3 -m pip install -q -r requirements.txt

# 2. Check Playwright Browsers (For Visual Auto-RPA)
if ! venv/bin/python3 -m playwright --version >/dev/null 2>&1; then
    echo "Installing Playwright Chromium..."
    venv/bin/python3 -m playwright install chromium
fi

# 3. Create generic workspace directory
mkdir -p workspace

# 4. Start the Hive API & Dashboard Engine in Background
echo "Starting API server and dashboard launcher..."
venv/bin/python3 hive_app.py &
HIVE_PID=$!

# Wait for process
echo "Running. Press Ctrl+C to stop."
wait $HIVE_PID
