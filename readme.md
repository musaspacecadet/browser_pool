## Project Name: Chrome-Pool

## Description

Chrome-Pool is a robust and scalable system designed to manage a pool of Chromium browser instances for automation and testing purposes. It provides an API to allocate, deallocate, and interact with these instances, efficiently handling resource allocation, health checks, and timeouts. The system ensures high availability and optimal resource utilization through features like automated instance warm-up, scaling, and session management. The inclusion of a dedicated Python client library simplifies integration and interaction with the browser pool.

## Features

-   **Browser Pool Management:**
    -   Dynamically manages a pool of Chromium browser instances.
    -   Allocates and deallocates browser instances on demand.
    -   Maintains a warm pool of browser instances for quick allocation.
    -   Automatically scales the pool based on demand and configured parameters.
-   **Session Management:**
    -   Assigns unique session IDs to allocated browser instances.
    -   Tracks browser instance usage and timeouts.
    -   Supports extending timeouts for active sessions.
    -   Validates sessions to ensure authorized access.
-   **Health Checks and Recovery:**
    -   Periodically checks the health of browser instances.
    -   Automatically restarts unhealthy or crashed instances.
    -   Handles browser instances that fail to restart after multiple attempts.
-   **API Endpoints:**
    -   Provides RESTful API endpoints for browser allocation, deallocation, timeout extension, and listing browsers.
    -   Supports WebSocket connections for real-time interaction with browser instances.
    -   Proxies HTTP and WebSocket requests to the appropriate browser instance.
-   **Client Library:**
    -   Includes a Python client library (APIClient) for easy interaction with the API.
    -   Simplifies browser allocation, deallocation, timeout management, and CDP (Chrome DevTools Protocol) requests.
    -   Handles WebSocket connections and message forwarding.
-   **Resource Optimization:**
    -   Efficiently manages resources by terminating idle instances and scaling down the pool when demand is low.
    -   Uses dedicated Chromium profiles for each instance to ensure isolation and prevent data leakage.
-   **Configurability:**
    -   Allows configuration of various parameters through environment variables, such as the maximum number of instances, warm pool size, timeouts, and health check intervals.
-   **Dockerized Deployment:**
    -   Provides a Dockerfile for easy containerization and deployment.
    -   Configures the Docker container for optimal performance and security.

## Project Structure

-   **`browser_launcher.py`:** Launches Chromium browser instances with specific configurations and debugging ports.
-   **`browser_pool.py`:** Implements the core logic for managing the pool of browser instances, including allocation, deallocation, health checks, and session management.
-   **`config.py`:** Defines configuration parameters and constants for the system.
-   **`lib.py`:** Contains the APIClient and APIClientBase classes for interacting with the browser automation API.
-   **`main.py`:** Implements the HTTP and WebSocket proxy server using aiohttp, handling requests and routing them to the appropriate browser instances.
-   **`models.py`:** Defines data models for `ProxyInstance` and `BrowserInstance`.
-   **`requirements.txt`:** Lists the Python dependencies for the project.
-   **`resource_pool.py`:** Provides a generic resource pool implementation used by `BrowserPool`.
-   **`test.py`:** Contains a test script to demonstrate the usage of the APIClient and perform multi-threaded screenshot capture.
-   **`Dockerfile`:** Specifies the Docker image build instructions.
-   **`entrypoint.sh`:** Entry point script that ensures old sessions are purged, Chromium profile is unlocked, and then starts the main python application.

## Dependencies

-   `aiohttp`: For building the HTTP and WebSocket server.
-   `fastapi`: An alternative for building the HTTP server (commented out in the current code).
-   `pydantic`: For data validation and settings management.
-   `Requests`: For making HTTP requests (used in the client library).
-   `uvicorn`: For running the ASGI server (commented out in the current code).
-   `websocket_client`: For WebSocket client functionality (used in the client library).
-   `websockets`: An alternative for WebSocket server and client functionality (listed in requirements but not directly used).
-   `chromium`: The Chromium browser itself.
-   `python3`: The Python 3 interpreter.
-   `py3-pip`: The package installer for Python 3.

## Setup and Installation

### Using Docker (Recommended)

1. **Build the Docker image:**
    ```bash
    docker build -t musaspacecadet/chrome:alpine-pool .
    ```
2. **Run the Docker container:**
    ```bash
    docker run -d --name chrome-pool \
        -p 8888:8888 \
        -e CHROMIUM_PROFILE_BASE_DIR="/config/chromium_profiles" \
        -e DEBUGGING_PORT_START=9222 \
        -e NUM_WARM=1 \
        -e MAX_INSTANCES=15 \
        -e IDLE_TIMEOUT=300 \
        -v $(pwd)/config:/config \
        --shm-size="2g" \
        --security-opt seccomp=unconfined \
        --cap-add SYS_ADMIN \
        musaspacecadet/chrome:alpine-pool
    ```
    Adjust the environment variables and volume mounts as needed.

### Manual Setup (Without Docker)

1. **Install system dependencies:**
    ```bash
    sudo apt-get update
    sudo apt-get install -y chromium-browser python3 python3-pip
    ```
2. **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd chrome-pool
    ```
3. **Install Python dependencies:**
    ```bash
    pip3 install -r requirements.txt
    ```
4. **Run the application:**
    ```bash
    python3 main.py
    ```
    Or, using uvicorn (uncomment the corresponding line in `entrypoint.sh` and comment out the line above):
    ```bash
    ./entrypoint.sh
    ```

## Configuration

The system can be configured using environment variables:

-   `CHROMIUM_PROFILE_BASE_DIR`: Base directory for storing Chromium profiles (default: `/config/chromium_profiles`).
-   `BASE_PORT`: Base port for internal proxy instances (default: 9000).
-   `DEBUGGING_PORT_START`: Starting port for Chromium debugging (default: 9222).
-   `NUM_WARM`: Number of warm browser instances to keep available (default: 1).
-   `MAX_INSTANCES`: Maximum number of browser instances allowed (default: 15).
-   `IDLE_TIMEOUT`: Timeout in seconds for idle browser instances (default: 300).
-   `SCALE_DOWN_INTERVAL`: Interval in seconds for scaling down the pool (default: 60).
-   `MAX_STARTUP_ATTEMPTS`: Maximum attempts to restart a failed browser instance (default: 3).
-   `HEALTH_CHECK_INTERVAL`: Interval in seconds for health checks (default: 2).
-   `PROXY_CONNECTION_TIMEOUT`: Timeout in seconds for proxy connections (default: 5).

## API Endpoints

### `/browser` (POST)

Allocates a new browser instance.

**Request Parameters:**

-   `timeout` (optional): Timeout in seconds for the allocation (default: 30).

**Response:**

-   `session_id`: Unique ID for the allocated session.
-   `proxy_url`: URL for interacting with the browser instance through the proxy.

**Status Codes:**

-   `200`: Browser successfully allocated.
-   `400`: Invalid timeout value.
-   `503`: All browsers are currently in use or no browser available.

### `/browser/{session_id}` (DELETE)

Deallocates a browser instance associated with the given session ID.

**Response:**

-   `200`: Browser successfully deallocated.
-   `400`: Session ID required.
-   `404`: Session not found.

### `/browser/{session_id}/timeout` (POST)

Extends the timeout for the browser instance associated with the given session ID.

**Request Parameters:**

-   `timeout` (optional): Additional timeout in seconds (default: 30).

**Response:**

-   `200`: Timeout successfully extended.
-   `400`: Session ID required or invalid timeout value.
-   `404`: Session not found.

### `/browsers` (GET)

Lists all currently managed browser instances.

**Response:**

-   A list of browser instances, each containing:
    -   `debugging_port`: The debugging port of the instance.
    -   `active`: Whether the instance is active.
    -   `last_used`: Timestamp of the last usage.
    -   `session_id`: Current session ID, if any.
    -   `timeout`: Remaining timeout for the session.

**Status Codes:**

-   `200`: Browsers successfully listed.

### `/session/{session_id}/*`

Proxies requests to the browser instance associated with the given session ID.

-   **HTTP:** Forwards HTTP requests to the corresponding Chromium instance's debugging port, replacing the `/session/{session_id}` prefix with the root path.
-   **WebSocket:** Establishes a WebSocket connection with the Chromium instance and forwards messages between the client and the browser.

**Status Codes:**

-   `200`: Request successfully proxied (for HTTP).
-   `403`: Invalid session.
-   `404`: Session not found.
-   `502`: Bad Gateway (if fetching data from Chrome fails for HTTP).

## API Client Usage (lib.py)

The `APIClient` class provides a convenient way to interact with the API from Python code.

### Initialization

```python
from lib import APIClient

api_url = "http://localhost:8888"  # Replace with your API URL
api_client = APIClient(api_url)
```

### Allocating a Browser

```python
async def example_allocation():
    session_id = await api_client.allocate_browser(timeout=120)
    if session_id:
        print(f"Browser allocated with session ID: {session_id}")
    else:
        print("Failed to allocate browser.")
```
The `allocate_browser` method automatically attaches to a page target.

### Deallocating a Browser

```python
async def example_deallocation():
    if api_client.deallocate_browser():
        print("Browser deallocated.")
    else:
        print("Failed to deallocate browser or no browser allocated.")
```

### Extending Timeout

```python
async def example_extend_timeout():
    if api_client.extend_timeout(additional_timeout=60):
        print("Browser timeout extended.")
    else:
        print("Failed to extend timeout or no browser allocated.")
```

### Listing Browsers

```python
async def example_list_browsers():
    browsers = api_client.list_browsers()
    if browsers:
        print("Browsers:")
        for browser in browsers:
            print(browser)
    else:
        print("Failed to list browsers.")
```

### Sending CDP Requests

```python
async def example_cdp_request():
    navigate_result = await api_client.send_cdp_request(
        method="Page.navigate",
        params={"url": "https://www.example.com"}
    )
    if navigate_result:
        print(f"Navigation result: {navigate_result}")
    else:
        print("Failed to send CDP request.")

    # Wait for the page to load:
    load_event_fired_result = await api_client.send_cdp_request(method='Page.loadEventFired')
    print(f"Page load event fired result: {load_event_fired_result}")

    screenshot_result = await api_client.send_cdp_request(
        method="Page.captureScreenshot",
        params={"format": "png"}
    )
    if screenshot_result and "result" in screenshot_result and "data" in screenshot_result["result"]:
        with open("screenshot.png", "wb") as f:
            f.write(base64.b64decode(screenshot_result["result"]["data"]))
        print("Screenshot saved to screenshot.png")
    else:
        print("Failed to capture screenshot.")
```

### Connecting to WebSocket

```python
def on_message(client, message):
    print(f"Received message: {message}")

def on_error(client, error):
    print(f"Error: {error}")

def on_close(client, close_status_code, close_msg):
    print("Connection closed.")

def on_open(client):
    print("Connection opened.")

async def example_websocket():
    if api_client.connect_ws(on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open):
        print("Connected to WebSocket.")
        # Send a message (optional)
        api_client.send_ws_message("Hello from client!")
        # Keep the connection alive (you might want to do this in a separate thread)
        while True:
            await asyncio.sleep(1)
    else:
        print("Failed to connect to WebSocket.")
```

### Getting the list of targets

```python
async def example_get_targets():
    targets_response = await api_client.get_targets()
    print(f"Targets response: {targets_response}")
```

### Attaching to a target

```python
async def example_attach_to_target(target_id : str):
    session_response = await api_client.attach_to_target(target_id)
    print(f"Session response: {session_response}")
```

## Test Script Usage (test.py)

The `test.py` script demonstrates how to use the `APIClient` to take screenshots of multiple websites concurrently using multiple threads.

```python
import asyncio
from test import test_api_multithreaded_screenshot

if __name__ == "__main__":
    api_url = "http://localhost:8888"  # Replace with your API URL
    urls = [
        "https://www.youtube.com",
        "https://www.reddit.com",
        # ... more URLs ...
    ]
    asyncio.run(test_api_multithreaded_screenshot(api_url, urls))
```

This will allocate browsers, navigate to the specified URLs, take screenshots, and save them as `screenshot_0.png`, `screenshot_1.png`, etc. It will also print the status of each operation.

## Notes

-   The code uses `threading.RLock` for thread safety in the `BrowserPool` class, which is important for handling concurrent requests.
-   Error handling is implemented throughout the code to catch potential issues like network errors, browser crashes, and allocation failures.
-   The code includes logging statements to provide insights into the system's operation and help with debugging.
-   The `entrypoint.sh` script handles the cleanup of old session data and ensures that the Chromium profile is unlocked before starting the application.
-   The Dockerfile uses a multi-stage build to reduce the final image size and improve security.
-   The `privileged` mode, `security_opt`, and `cap_add` options in the Docker Compose file are necessary for Chromium to function correctly within the container. These settings should be carefully considered in a production environment.
-   The test script has a hardcoded limit of 5 threads for taking screenshots. This can be adjusted based on the available resources and the desired level of concurrency.

## Contributing

Contributions to the project are welcome! Please feel free to submit pull requests or open issues to suggest improvements or report bugs.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Author

musaspacecadet