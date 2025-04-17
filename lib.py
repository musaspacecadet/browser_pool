import requests
import websocket
import json
import time
import uuid
import asyncio

class APIClientBase:
    """Base class to avoid code duplication."""
    def __init__(self, api_base_url):
        self.api_base_url = api_base_url
        self.session_id = None
        self.ws = None
        self.next_cdp_id = 1
        self.cdp_id_to_uuid_map = {}
        self.pending_cdp_requests = {}
        self.loop = asyncio.get_event_loop() # Get the event loop

    def allocate_browser(self, timeout=120):
        try:
            response = requests.post(f"{self.api_base_url}/browser", params={"timeout": timeout})
            response.raise_for_status()
            data = response.json()
            self.session_id = data["session_id"]
            return self.session_id
        except requests.exceptions.RequestException as e:
            print(f"Error allocating browser: {e}")
            return None

    def deallocate_browser(self):
        if not self.session_id:
            print("No browser session to deallocate.")
            return False
        try:
            response = requests.delete(f"{self.api_base_url}/browser/{self.session_id}")
            response.raise_for_status()
            self.session_id = None
            if self.ws:
                self.ws.close()
                self.ws = None
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error deallocating browser: {e}")
            return False

    def extend_timeout(self, additional_timeout=30):
        if not self.session_id:
            print("No browser session to extend timeout for.")
            return False
        try:
            response = requests.post(
                f"{self.api_base_url}/browser/{self.session_id}/timeout",
                params={"timeout": additional_timeout}
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error extending timeout: {e}")
            return False

    def list_browsers(self):
        try:
            response = requests.get(f"{self.api_base_url}/browsers")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error listing browsers: {e}")
            return None

    def connect_ws(self, on_message=None, on_error=None, on_close=None, on_open=None, **kwargs):
        if not self.session_id:
            print("No browser session to connect to.")
            return False

        def on_message_wrapper(ws, message):
            try:
                data = json.loads(message)
                if "id" in data:
                    cdp_id = data["id"]
                    if cdp_id in self.cdp_id_to_uuid_map:
                        request_uuid = self.cdp_id_to_uuid_map[cdp_id]
                        if request_uuid in self.pending_cdp_requests:
                            # Set the result of the future in the event loop:
                            self.loop.call_soon_threadsafe(self.pending_cdp_requests[request_uuid].set_result, data)
                            del self.pending_cdp_requests[request_uuid]
                            del self.cdp_id_to_uuid_map[cdp_id]
                    else:
                        print(f"Received CDP response with unknown id: {cdp_id}")
                elif "method" in data:
                    pass
                else:
                    print(f"Received unknown WebSocket message: {data}")
            except json.JSONDecodeError:
                print(f"Received non-JSON WebSocket message: {message}")

            if on_message:
                on_message(self, message)

        def on_error_wrapper(ws, error):
            if on_error:
                on_error(self, error)

        def on_close_wrapper(ws, close_status_code, close_msg):
            if on_close:
                on_close(self, close_status_code, close_msg)

        def on_open_wrapper(ws):
            if on_open:
                on_open(self)

        try:
            ws_url = f"ws://{self.api_base_url.split('//')[1]}/session/{self.session_id}"
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message_wrapper,
                on_error=on_error_wrapper,
                on_close=on_close_wrapper,
                on_open=on_open_wrapper,
                **kwargs
            )
            import threading
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            while not self.ws.sock or not self.ws.sock.connected:
                time.sleep(0.1)
            return True
        except Exception as e:
            print(f"Error connecting to WebSocket: {e}")
            return False

    def send_ws_message(self, message):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            print("WebSocket connection not established.")
            return False
        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            self.ws.send(message)
            return True
        except Exception as e:
            print(f"Error sending WebSocket message: {e}")
            return False

class APIClient(APIClientBase):  # Inherit from APIClientBase
    """
    A client library for interacting with the browser automation API.
    """

    def __init__(self, api_base_url):
        """
        Initializes the API client.

        Args:
            api_base_url: The base URL of the API (e.g., http://localhost:8888).
        """
        super().__init__(api_base_url) # Initialize the base class
        self.page_session_id = None  # To store the session ID for the page target

    async def allocate_browser(self, timeout=120):
        """
        Allocates a browser instance and automatically attaches to a page target.

        Args:
            timeout: The timeout in seconds for the allocation and attachment.

        Returns:
            The session ID if successful, None otherwise.
        """
        if not super().allocate_browser(timeout):
            return None

        if not self.connect_ws():
            self.deallocate_browser()
            return None

        # Automatically attach to a page target
        targets_response = await self.get_targets()
        if targets_response and "result" in targets_response and "targetInfos" in targets_response["result"]:
            page_target = next((t for t in targets_response["result"]["targetInfos"] if t["type"] == "page"), None)
            if page_target:
                session_response = await self.attach_to_target(page_target["targetId"])
                if session_response:
                    self.page_session_id = session_response
                    return self.session_id
                else:
                    print("Failed to attach to the page target.")
                    self.deallocate_browser()
                    return None
            else:
                print("No page target found.")
                self.deallocate_browser()
                return None
        else:
            print("Failed to get targets.")
            self.deallocate_browser()
            return None

    def deallocate_browser(self):
        """
        Deallocates the current browser instance.

        Returns:
            True if successful, False otherwise.
        """
        success = super().deallocate_browser()
        self.page_session_id = None
        return success

    def extend_timeout(self, additional_timeout=30):
        """
        Extends the timeout for the current browser instance.

        Args:
            additional_timeout: The additional timeout in seconds.

        Returns:
            True if successful, False otherwise.
        """
        return super().extend_timeout(additional_timeout)

    def list_browsers(self):
        """
        Lists all browser instances.

        Returns:
            A list of browser details if successful, None otherwise.
        """
        return super().list_browsers()

    def connect_ws(self, on_message=None, on_error=None, on_close=None, on_open=None, **kwargs):
        """
        Connects to the WebSocket endpoint for the current browser instance.

        Args:
            on_message: Callback function for received messages.
            on_error: Callback function for errors.
            on_close: Callback function for connection close.
            on_open: Callback function for connection open.
            **kwargs: used to pass extra params to the websocket

        Returns:
            True if the connection is successful, False otherwise.
        """
        return super().connect_ws(on_message, on_error, on_close, on_open, **kwargs)

    async def send_cdp_request(self, method, params=None):
        """
        Sends a CDP (Chrome DevTools Protocol) request and waits for a response.

        Args:
            method: The CDP method name (e.g., "Page.navigate").
            params: The parameters for the method (a dictionary).

        Returns:
            The CDP response if successful, None otherwise.
        """
        if not self.session_id:
            print("No browser session for CDP request.")
            return None

        if not self.ws:
            print("WebSocket not connected.")
            return None

        if params is None:
            params = {}

        cdp_id = self.next_cdp_id
        self.next_cdp_id += 1

        request_uuid = str(uuid.uuid4())

        self.cdp_id_to_uuid_map[cdp_id] = request_uuid

        request = {
            "id": cdp_id,
            "method": method,
            "params": params
        }

        if self.page_session_id:
            request["sessionId"] = self.page_session_id

        print(request)

        request_future = self.loop.create_future()
        self.pending_cdp_requests[request_uuid] = request_future

        if not self.send_ws_message(request):
            del self.pending_cdp_requests[request_uuid]
            if cdp_id in self.cdp_id_to_uuid_map:
                del self.cdp_id_to_uuid_map[cdp_id]
            return None

        try:
            # Await the future without a timeout:
            response = await request_future
            return response
        except Exception as e:
            print(f"Error in CDP request: {e}")
            if request_uuid in self.pending_cdp_requests:
                del self.pending_cdp_requests[request_uuid]
            if cdp_id in self.cdp_id_to_uuid_map:
                del self.cdp_id_to_uuid_map[cdp_id]
            return None

    async def get_targets(self):
        """
        Retrieves a list of available targets.
        """
        return await self.send_cdp_request("Target.getTargets")

    async def attach_to_target(self, target_id, flatten=True):
        """
        Attaches to a specific target and returns the session ID.
        """
        params = {"targetId": target_id, "flatten": flatten}
        response = await self.send_cdp_request("Target.attachToTarget", params)
        if response and "result" in response and "sessionId" in response["result"]:
            return response["result"]["sessionId"]
        return None