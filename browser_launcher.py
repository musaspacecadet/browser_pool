import os
import subprocess
import time
import shutil
from typing import Optional
from models import BrowserInstance
from config import CHROMIUM_ARGS, CHROMIUM_PROFILE_BASE_DIR, HEALTH_CHECK_INTERVAL

class BrowserLauncher:
    def __init__(self):
        self.chromium_profile_dir = "/config/xdg/config/chromium"  # Or get it from your config

    def _purge_old_session_data(self):
        """Purges old session data from the specified directory."""
        session_data_dir = "/config/chromium_profiles"
        print("Purging old session data...")
        try:
            shutil.rmtree(session_data_dir, ignore_errors=True)  # Use ignore_errors=True to avoid issues if the directory doesn't exist
            os.makedirs(session_data_dir, exist_ok=True) #recreate to avoid issues later
            print("Session data purged.")
        except Exception as e:
            print(f"Error purging session data: {e}")

    def _unlock_chromium_profile(self):
        """Removes Chromium lock files to unlock the profile."""
        if os.path.isdir(self.chromium_profile_dir):
            print(f"Chromium profile directory found: {self.chromium_profile_dir}")
            lock_files = ["SingletonCookie", "SingletonLock", "SingletonSocket"]
            for file in lock_files:
                file_path = os.path.join(self.chromium_profile_dir, file)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"Removed lock file: {file_path}")
                    except Exception as e:
                        print(f"Error removing lock file {file_path}: {e}")
            print("Chromium profile unlocked.")
        else:
            print("Chromium profile directory not found. Please check the path.")

    def launch_browser(self, debugging_port: int) -> Optional[BrowserInstance]:
        """Launches a new browser instance with a dedicated profile, after purging data and unlocking profiles."""
        
        # Purge old session data and unlock profile before launching each browser
        self._purge_old_session_data()
        self._unlock_chromium_profile()

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

            # Check if the process started successfully
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