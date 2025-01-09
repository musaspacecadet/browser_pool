import asyncio
import time
from lib import APIClient
import base64
import threading
from concurrent.futures import ThreadPoolExecutor

async def take_screenshot(api_url, url, results, index):
    """
    Takes a screenshot of a given URL using a dedicated API client.
    Stores the result (success/failure and image data/error message) in the results list.
    """
    api_client = APIClient(api_url)

    try:
        # Allocate a browser
        session_id = await api_client.allocate_browser()
        if not session_id:
            results[index] = (False, "Failed to allocate browser.")
            return

        # Navigate to the URL
        navigate_result = await api_client.send_cdp_request(
            method="Page.navigate",
            params={"url": url}
        )
        if not navigate_result or navigate_result.get("error"):
            results[index] = (False, f"Failed to navigate to {url}: {navigate_result}")
            await cleanup(api_client)
            return

        # Wait for the page to load
        await api_client.send_cdp_request(method='Page.loadEventFired')
        
        # Take a screenshot
        screenshot_result = await api_client.send_cdp_request(
            method="Page.captureScreenshot",
            params={"format": "png"},
        )

        if screenshot_result and "result" in screenshot_result and "data" in screenshot_result["result"]:
            image_data = base64.b64decode(screenshot_result["result"]["data"])
            results[index] = (True, image_data)
        else:
            results[index] = (False, f"Failed to capture screenshot of {url}: {screenshot_result}")

    except Exception as e:
        results[index] = (False, f"An error occurred for {url}: {e}")
    finally:
        print(f'cleaning up {url}')
        #await cleanup(api_client)

async def cleanup(api_client : APIClient):
    """Helper function to deallocate the browser."""
    if api_client.session_id:
        success = await api_client.deallocate_browser()
        if success:
            print(f"Browser deallocated successfully for {api_client.session_id}.")
        else:
            print(f"Failed to deallocate browser for {api_client.session_id}")

def worker_thread(loop, api_url, url, results, index):
    """
    Worker thread function to run the async screenshot task.
    """
    asyncio.set_event_loop(loop)
    loop.run_until_complete(take_screenshot(api_url, url, results, index))

async def test_api_multithreaded_screenshot(api_url, urls):
    """
    Tests the API client with multiple threads, taking screenshots of a list of websites.
    """
    num_threads = min(len(urls), 15)  # Limit threads to the number of URLs or 15, whichever is smaller
    results = [None] * len(urls)  # Initialize results list to store (success, data) tuples

    # Create a new event loop for the main thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        for i, url in enumerate(urls):
            # Create a new event loop for each thread
            thread_loop = asyncio.new_event_loop()
            executor.submit(worker_thread, thread_loop, api_url, url, results, i)

    # Close the main event loop after all threads have finished
    loop.close()

    # Save screenshots and report results
    for i, (success, data) in enumerate(results):
        if success:
            with open(f"screenshot_{i}.png", "wb") as fh:
                fh.write(data)
            print(f"Screenshot {i} (URL: {urls[i]}) saved successfully.")
        else:
            print(f"Error processing screenshot {i} (URL: {urls[i]}): {data}")

if __name__ == "__main__":
    api_url = "https://chrome-production-271d.up.railway.app"  # Replace with your API URL
    urls = [
        "https://www.youtube.com",
        "https://www.reddit.com",
        "https://www.wikipedia.org",
        "https://www.example.com",
        "https://www.github.com",
    ] #* 2 # Increase the list size to 100
    asyncio.run(test_api_multithreaded_screenshot(api_url, urls))
