# config.py

import os

# Constants
CHROMIUM_PROFILE_BASE_DIR = os.getenv("CHROMIUM_PROFILE_BASE_DIR", "/config/chromium_profiles")  # Base directory for profiles
BASE_PORT = int(os.getenv("BASE_PORT", 9000))
DEBUGGING_PORT_START = int(os.getenv("DEBUGGING_PORT_START", 9222))
NUM_WARM = int(os.getenv("NUM_WARM", 1))
MAX_INSTANCES = int(os.getenv("MAX_INSTANCES", 15))
IDLE_TIMEOUT = int(os.getenv("IDLE_TIMEOUT", 300))
SCALE_DOWN_INTERVAL = int(os.getenv("SCALE_DOWN_INTERVAL", 60))
MAX_STARTUP_ATTEMPTS = int(os.getenv("MAX_STARTUP_ATTEMPTS", 3))
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", 2))
PROXY_CONNECTION_TIMEOUT = int(os.getenv("PROXY_CONNECTION_TIMEOUT", 5))

# Chromium command-line arguments to ensure clean, private browsing
CHROMIUM_ARGS = [
    "--start-maximized",
    "--disable-backgrounding-occluded-windows",
    "--disable-hang-monitor",
    "--metrics-recording-only",
    "--disable-sync",  # Disable syncing to Google accounts
    "--disable-background-timer-throttling",
    "--disable-prompt-on-repost",
    "--disable-background-networking",
    "--disable-infobars",
    "--remote-allow-origins=*",
    "--homepage=about:blank",  # Set a blank homepage
    "--no-service-autorun",
    "--disable-ipc-flooding-protection",
    "--disable-session-crashed-bubble",
    "--force-fieldtrials=*BackgroundTracing/default/",
    "--disable-breakpad",
    "--password-store=basic",  # Don't use the OS's password storage
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-client-side-phishing-detection",
    "--use-mock-keychain",
    "--no-pings",
    "--disable-renderer-backgrounding",
    "--disable-component-update",
    "--disable-dev-shm-usage",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--no-default-browser-check",  # Don't check if Chromium is the default browser
    "--disable-history-quick-provider",
    "--disable-history-url-provider",
    "--disable-save-password-bubble",  # Disable "Save Password" prompts
    "--disable-single-click-autofill",
    "--disable-autofill-download-manager",
    "--disable-offer-store-unmasked-wallet-cards",
    "--disable-offer-upload-credit-cards",
    "--disable-extensions",  # Disable extensions entirely
    "--disable-notifications",  # Disable web notifications
    "--disable-geolocation",  # Disable geolocation
    "--disable-media-source",  # Helps to prevent sites from tracking via media
    "--disable-device-discovery-notifications",  # Disables notifications related to device discovery
    "--disable-component-extensions-with-background-pages", # Disables component extensions that have background pages
    "--disable-backing-store", # Disables the backing store for each renderer, which helps manage memory by not caching content when navigating back/forward
    "--disable-features=OptimizationHints", # Disables optimization hints that can be used for tracking or profiling
]