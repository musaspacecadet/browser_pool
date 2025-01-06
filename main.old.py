import asyncio
import json
import logging
import websockets
import aiohttp
from aiohttp import web
from browser_pool import BrowserPool
import inspect

# --- Configuration ---
PROXY_HOST = "0.0.0.0"  # Host for the proxy server
PROXY_PORT = 8888  # Port for the proxy server
# ---------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

browser_pool = BrowserPool()

async def fetch_chrome_data(debugging_port: int, path: str):
    """
    Fetches data from a specific Chrome instance via HTTP.

    Args:
        debugging_port: The debugging port of the Chrome instance.
        path: The path to request from the Chrome instance (e.g., '/json/version').

    Returns:
        A JSON object containing the response from Chrome, or None if the request fails.
    """
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"http://localhost:{debugging_port}{path}") as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logging.error(f"Error fetching data from Chrome on port {debugging_port}: {resp.status}")
                    return None
        except aiohttp.ClientConnectorError as e:
            logging.error(f"Failed to connect to Chrome on port {debugging_port}: {e}")
            return None

async def handle_request(request):
    """
    Handles all incoming HTTP and WebSocket requests.

    This function acts as the central request handler, routing requests based on the path.
    It manages browser allocation, deallocation, and proxies requests to the appropriate
    Chrome instance.

    Args:
        request: The aiohttp.web.Request object representing the incoming request.

    Returns:
        An aiohttp.web.Response object containing the response to the request.
    """
    # Attempt to extract session_id from the path
    parts = request.path.split('/')
    if len(parts) > 2 and parts[1] == 'session':
        session_id = parts[2]
        browser_instance, port = browser_pool.get_browser_by_session(session_id)
        if browser_instance is None:
            return web.Response(status=404, text="Session not found")

        if not browser_pool.validate_session(session_id, port):
            return web.Response(status=403, text="Invalid session")

        if request.headers.get('Upgrade') == 'websocket':
            # Handle WebSocket Upgrade
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await handle_websocket(ws, request.path)
            return ws
        else:
            # Handle HTTP
            path = request.path.replace(f'/session/{session_id}', '', 1)
            chrome_data = await fetch_chrome_data(port, path)
            if chrome_data is not None:
                browser_pool.extend_timeout(session_id, browser_instance.timeout) # use the original timeout
                return web.json_response(chrome_data)
            else:
                return web.Response(status=502)  # Bad Gateway

    # If not a session request, handle as a regular request
    elif request.path == '/browser' and request.method == 'POST':
        return await allocate_browser(request)
    elif request.path.startswith('/browser') and request.method == 'DELETE':
        return await deallocate_browser(request)
    elif request.path.startswith('/browser') and request.path.endswith('/timeout') and request.method == 'POST':
        return await extend_browser_timeout(request)
    elif request.path == '/browsers' and request.method == 'GET':
        return await list_all_browsers(request)
    else:
        return web.Response(status=404, text="Not Found")

        
async def handle_websocket(client_websocket, path):
    """
    Handles WebSocket connections, proxying messages between the client and the Chrome instance.

    Args:
        client_websocket: The aiohttp.web.WebSocketResponse object for the client connection.
        path: The path of the WebSocket request, containing the session ID.
    """
    session_id = path.split('/')[2]

    browser_instance, port = browser_pool.get_browser_by_session(session_id)
    chrome_ws_url = await get_chrome_ws_url(port)
    print(chrome_ws_url)
    if chrome_ws_url is None:
        if "reason" in inspect.getfullargspec(client_websocket.close).args:
            await client_websocket.close(code=4004, reason="webSocketDebuggerUrl not found")
        else:
            await client_websocket.close(code=4004)
        return

    try:
        async with websockets.connect(chrome_ws_url) as chrome_websocket:
            logging.info(f"Connected to Chrome instance for session: {session_id}")

            async def forward_to_chrome(msg):
                """Forwards messages from the client to Chrome."""
                truncated_msg = (msg[:100] + "...") if isinstance(msg, str) and len(msg) > 100 else msg
                logging.info(f"Client -> Chrome: {truncated_msg}")
                if isinstance(msg, str):
                    await chrome_websocket.send(msg)  # Send string directly
                else:
                    await chrome_websocket.send(msg.data)

            async def forward_to_client(msg):
                """Forwards messages from Chrome to the client."""
                truncated_msg = (msg[:100] + "...") if isinstance(msg, str) and len(msg) > 100 else msg
                logging.info(f"Chrome -> Client: {truncated_msg}")
                # aiohttp websockets only allow sending str, bytes, or json
                if isinstance(msg, str):
                    await client_websocket.send_str(msg)
                elif isinstance(msg, bytes):
                    await client_websocket.send_bytes(msg)
                else:
                    await client_websocket.send_json(msg)


            # Create tasks for forwarding messages in both directions
            client_to_chrome_task = asyncio.create_task(
                forward_messages(client_websocket, forward_to_chrome), name=f"client_to_chrome_{session_id}"
            )
            chrome_to_client_task = asyncio.create_task(
                forward_messages(chrome_websocket, forward_to_client), name=f"chrome_to_client_{session_id}"
            )

            # Keep track of active tasks and remove them when done
            active_tasks = {client_to_chrome_task, chrome_to_client_task}
            for task in list(active_tasks):
                task.add_done_callback(active_tasks.discard)

            # Let the tasks run concurrently in the background
            # The loop will continue until the client_websocket is closed externally
            while not client_websocket.closed:
                await asyncio.sleep(0.1)  # Check periodically

            # If client_websocket is closed, cancel the pending tasks
            for task in active_tasks:
                if not task.done():
                    task.cancel()
                
            browser_pool.extend_timeout(session_id, browser_instance.timeout) # use the original timeout

    except websockets.exceptions.ConnectionClosed:
        logging.info(f"Connection to Chrome closed for session: {session_id}")
    except Exception as e:
        logging.error(f"An error occurred for session {session_id}: {e}")
    finally:
        logging.info(f"Client disconnected for session: {session_id}")

async def forward_messages(websocket, forward_func):
    """
    Continuously forwards messages between a websocket and a forwarding function.

    Args:
        websocket: The websocket object to read messages from.
        forward_func: The function to call to forward the received message.
    """
    try:
        async for message in websocket:
            await forward_func(message)
    except websockets.exceptions.ConnectionClosed:
        logging.info("WebSocket connection closed.")
    except asyncio.CancelledError:
        logging.info("WebSocket task cancelled.")
    except Exception as e:
        logging.error(f"Error in WebSocket forwarding: {e}")

async def get_chrome_ws_url(port: int):
    """
    Fetches the WebSocket URL of a specific Chrome instance.

    Args:
        port: The debugging port of the Chrome instance.

    Returns:
        The WebSocket debugger URL for the Chrome instance, or None if not found.
    """
    chrome_data = await fetch_chrome_data(port, "/json/version")
    if chrome_data:
        return chrome_data.get("webSocketDebuggerUrl")
    else:
        return None

async def allocate_browser(request):
    """
    Allocates a browser instance and returns a unique session ID.

    Args:
        request: The aiohttp.web.Request object.

    Returns:
        An aiohttp.web.json_response containing the session ID and proxy URL,
        or an error response if allocation fails.
    """
    timeout = request.rel_url.query.get("timeout", "30")
    try:
        timeout = int(timeout)
    except ValueError:
        return web.Response(status=400, text="Invalid timeout value")

    result = browser_pool.get_browser(timeout)

    if result:
        debugging_port, external_port, session_id = result
        return web.json_response({
            "session_id": session_id,
            "proxy_url": f"http://{PROXY_HOST}:{PROXY_PORT}/session/{session_id}"
        })
    elif browser_pool.all_resources_occupied:
        return web.Response(status=503, text="All browsers are currently in use")
    else:
        return web.Response(status=503, text="No browser available")

async def deallocate_browser(request):
    """
    Deallocates a specific browser instance based on the session ID in the URL.

    Args:
        request: The aiohttp.web.Request object.

    Returns:
        An aiohttp.web.Response indicating success or failure of deallocation.
    """
    parts = request.path.split('/')
    if len(parts) > 2 and parts[1] == 'browser':
        session_id = parts[2]
        if not session_id:
            return web.Response(status=400, text="Session ID required")

        success = browser_pool.terminate_browser_by_session(session_id)
        if success:
            return web.Response(status=200, text="Browser deallocated")
        else:
            return web.Response(status=404, text="Session not found")
    else:
        return web.Response(status=404, text="Not Found")

async def extend_browser_timeout(request):
    """
    Extends the timeout for a specific browser instance.

    Args:
        request: The aiohttp.web.Request object.

    Returns:
        An aiohttp.web.Response indicating success or failure of extending the timeout.
    """
    session_id = request.match_info['session_id']
    if not session_id:
        return web.Response(status=400, text="Session ID required")

    additional_time = request.rel_url.query.get("timeout", "30")
    try:
        additional_time = int(additional_time)
    except ValueError:
        return web.Response(status=400, text="Invalid timeout value")

    success = browser_pool.extend_timeout(session_id, additional_time)
    if success:
        return web.Response(status=200, text="Timeout extended")
    else:
        return web.Response(status=404, text="Session not found")

async def list_all_browsers(request):
    """
    Lists all currently managed browser instances with their details.

    Args:
        request: The aiohttp.web.Request object.

    Returns:
        An aiohttp.web.json_response containing a list of browser details.
    """
    browsers = browser_pool.list_browsers()
    return web.json_response(browsers)

async def start_proxy():
    """
    Starts the HTTP and WebSocket proxy server.

    This function initializes the aiohttp application, sets up the routing,
    and starts the server to listen for incoming connections.
    """
    app = web.Application()

    # Centralized request handling
    app.router.add_route('*', '/{tail:.*}', handle_request)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, PROXY_HOST, PROXY_PORT)
    await site.start()
    logging.info(f"Proxy server started on http://{PROXY_HOST}:{PROXY_PORT}")

    await asyncio.Future()  # Keep the server running indefinitely

if __name__ == "__main__":
    try:
        asyncio.run(start_proxy())
    except KeyboardInterrupt:
        logging.info("Proxy server stopped.")