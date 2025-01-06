# browser_launcher.py

import os
import subprocess
import time
from typing import Optional
from models import BrowserInstance
from config import CHROMIUM_ARGS, CHROMIUM_PROFILE_BASE_DIR, HEALTH_CHECK_INTERVAL

class BrowserLauncher:
    def __init__(self):
        pass

    def launch_browser(self, debugging_port: int) -> Optional[BrowserInstance]:
        """Launches a new browser instance with a dedicated profile and enhanced error handling."""
        profile_path = os.path.join(CHROMIUM_PROFILE_BASE_DIR, f"profile-{debugging_port}")
        os.makedirs(profile_path, exist_ok=True)

        try:
            chrome_cmd = [
                "chromium-browser",
                "--disable-gpu",
                "--no-first-run",
                f"--remote-debugging-port={debugging_port}",
                f"--user-data-dir={profile_path}"  # Use a dedicated profile
            ] + CHROMIUM_ARGS
            chrome_process = subprocess.Popen(chrome_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Check if process started successfully
            time.sleep(HEALTH_CHECK_INTERVAL)
            if chrome_process.poll() is not None:
                stderr = chrome_process.stderr.read().decode()
                print(f"Chromium process failed to start (port {debugging_port}): {stderr}")
                return None

            return BrowserInstance(
                process=chrome_process,
                debugging_port=debugging_port,
                last_used=time.time(),
                profile_path=profile_path
            )
        except Exception as e:
            print(f"Failed to launch browser: {e}")
            return None