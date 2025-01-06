#!/bin/sh

echo "Purging old session data..."
rm -rf /config/chromium_profiles/*

# Define the path to the Chromium profile directory
CHROMIUM_PROFILE_DIR="/config/xdg/config/chromium"

# Check if the directory exists
if [ -d "$CHROMIUM_PROFILE_DIR" ]; then
  echo "Chromium profile directory found: $CHROMIUM_PROFILE_DIR"

  # Navigate to the Chromium profile directory
  cd "$CHROMIUM_PROFILE_DIR"

  # Remove the Singleton files that lock the profile
  echo "Removing lock files..."
  rm -f SingletonCookie SingletonLock SingletonSocket

  # Verify the removal
  echo "Remaining files in profile directory:"
  ls

  echo "Chromium profile unlocked. You can now restart Chromium."
else
  echo "Chromium profile directory not found. Please check the path."
  #exit 1
fi


python3 /main.py
#uvicorn main:app --host 0.0.0.0 --port 8888
# Wait for all background processes to complete
wait
