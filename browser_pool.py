import os
import subprocess
import queue
import threading
import time
import uuid
from typing import List, Optional, Dict, Tuple, Callable, Any
from models import BrowserInstance
from config import *
from browser_launcher import BrowserLauncher
from resource_pool import ResourcePool

class BrowserPool(ResourcePool):
    def __init__(self):
        self.browser_launcher = BrowserLauncher()
        self.session_browser_map: Dict[str, int] = {}
        self.next_available_port = DEBUGGING_PORT_START
        self.available_ports = queue.Queue()
        self.all_resources_occupied = False
        self._lock_owner = None

        if not os.path.exists(CHROMIUM_PROFILE_BASE_DIR):
            os.makedirs(CHROMIUM_PROFILE_BASE_DIR)

        super().__init__(
            max_instances=MAX_INSTANCES,
            create_resource_func=self.create_browser,
            cleanup_resource_func=self.cleanup_browser,
            health_check_func=self.check_browser_health,
            warm_resources=NUM_WARM,
            health_check_interval=HEALTH_CHECK_INTERVAL,
            scale_down_interval=SCALE_DOWN_INTERVAL
        )

    def create_browser(self, resource_id: Optional[int] = None) -> Optional[BrowserInstance]:
        """Creates a new browser instance."""
        if resource_id is None:
          if self.available_ports.empty():
              debugging_port = self.next_available_port
              self.next_available_port += 1
          else:
              debugging_port = self.available_ports.get()
        else:
          debugging_port = resource_id

        instance = self.browser_launcher.launch_browser(debugging_port)
        if instance:
            return instance
        else:
            print(f"Failed to launch browser at port {debugging_port}.")
            if resource_id is None:
              self.available_ports.put(debugging_port)
            return None

    def cleanup_browser(self, instance: BrowserInstance):
        """Cleans up a browser instance."""
        try:
            instance.process.terminate()
            instance.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"Force killing browser process at port {instance.debugging_port}")
            instance.process.kill()

        try:
            import shutil
            shutil.rmtree(instance.profile_path)
            print(f"Removed profile directory: {instance.profile_path}")
        except Exception as e:
            print(f"Error removing profile directory {instance.profile_path}: {e}")

    def check_browser_health(self, instance: BrowserInstance):
        """Checks the health of a browser instance and restarts it if necessary."""
        if instance.process.poll() is not None:
            print(f"Browser on port {instance.debugging_port} has exited. Attempting to restart...")
            instance.startup_attempts += 1
            if instance.startup_attempts < MAX_STARTUP_ATTEMPTS:
                new_instance = self.browser_launcher.launch_browser(instance.debugging_port)
                if new_instance:
                    if self.lock.acquire(timeout=5):
                        try:
                            # Check if the current thread is the lock owner
                            if self.lock._is_owned():
                              self.resources[instance.debugging_port] = new_instance
                              self._lock_owner = threading.current_thread()
                            else:
                              self.resources[instance.debugging_port] = new_instance
                              self._lock_owner = threading.current_thread()
                        finally:
                            self.lock.release()
                    else:
                        print(f"Failed to acquire lock to update browser on port {instance.debugging_port}.")
                        return

                    print(f"Browser on port {instance.debugging_port} restarted successfully.")
                else:
                    print(f"Failed to restart browser on port {instance.debugging_port} after multiple attempts.")
                    self.handle_failed_restart(instance)
            else:
                print(f"Max restart attempts reached for browser on port {instance.debugging_port}.")
                self.handle_failed_restart(instance)

    def handle_failed_restart(self, instance: BrowserInstance):
        """Handles the case where a browser instance fails to restart after multiple attempts."""
        self.cleanup_browser(instance)
        if self.lock.acquire(timeout=5):
            try:
                # Check if the current thread is the lock owner
                if self.lock._is_owned():
                    instance.is_active = False
                    instance.session_id = None
                    self.available_ports.put(instance.debugging_port)
                    self._lock_owner = threading.current_thread()
                else:
                  instance.is_active = False
                  instance.session_id = None
                  self.available_ports.put(instance.debugging_port)
                  self._lock_owner = threading.current_thread()
            finally:
                self.lock.release()
        else:
            print(f"Failed to acquire lock to handle failed restart for browser at port {instance.debugging_port}.")
            return
        print(f"Browser at port {instance.debugging_port} marked as inactive and resources cleaned up.")

    def get_browser(self, timeout: int = 30) -> Optional[Tuple[int, int, str]]:
        """Gets a browser instance, creating a new one if necessary."""
        result = self.get_resource(timeout)
        if result:
            debugging_port, session_id = result
            if self.lock.acquire(timeout=5):
                try:
                  # Check if the current thread is the lock owner
                    if self.lock._is_owned():
                        self.session_browser_map[session_id] = debugging_port
                        self._lock_owner = threading.current_thread()
                    else:
                      self.session_browser_map[session_id] = debugging_port
                      self._lock_owner = threading.current_thread()
                finally:
                    self.lock.release()
            else:
                print("Failed to acquire lock to update session_browser_map.")
                return None

            return debugging_port, None, session_id
        else:
            return None

    def list_browsers(self) -> List[dict]:
        """Lists all browser instances with details."""
        browser_list = super().list_resources()
        for browser_info in browser_list:
            debugging_port = browser_info["resource_id"]
            browser_info["debugging_port"] = debugging_port
            del browser_info["resource_id"]
        return browser_list

    def get_browser_by_session(self, session_id: str) -> Optional[Tuple[BrowserInstance, int]]:
        """Gets the browser instance and port associated with a session ID."""
        if self.lock.acquire(timeout=5):
            try:
                # Check if the current thread is the lock owner
                if self.lock._is_owned():
                    debugging_port = self.session_browser_map.get(session_id)
                    self._lock_owner = threading.current_thread()
                else:
                  debugging_port = self.session_browser_map.get(session_id)
                  self._lock_owner = threading.current_thread()
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock to get browser by session.")
            return None, None

        if debugging_port is None:
            return None, None

        if self.lock.acquire(timeout=5):
            try:
                # Check if the current thread is the lock owner
                if self.lock._is_owned():
                    instance = self.resources.get(debugging_port)
                    self._lock_owner = threading.current_thread()
                else:
                    instance = self.resources.get(debugging_port)
                    self._lock_owner = threading.current_thread()
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock to get browser instance.")
            return None, debugging_port

        if instance is None or not instance.is_active:
            return None, debugging_port

        return instance, debugging_port

    def terminate_browser_by_session(self, session_id: str) -> bool:
        """Terminates the browser instance associated with a session ID."""
        instance, port = self.get_browser_by_session(session_id)
        if instance:
            self.terminate_resource(port)
            if self.lock.acquire(timeout=5):
                try:
                    # Check if the current thread is the lock owner
                    if self.lock._is_owned():
                        if session_id in self.session_browser_map:
                            del self.session_browser_map[session_id]
                            self._lock_owner = threading.current_thread()
                    else:
                        if session_id in self.session_browser_map:
                          del self.session_browser_map[session_id]
                          self._lock_owner = threading.current_thread()
                finally:
                    self.lock.release()
            else:
                print("Failed to acquire lock to delete session from session_browser_map.")
                return False
            return True
        else:
            return False

    def maintain_warm_pool(self):
      def _maintain():
          while True:
              if self.lock.acquire(timeout=5):
                  try:
                      # Check if the current thread is the lock owner
                      if self.lock._is_owned():
                          unassigned_count = sum(1 for r in self.resources.values() if r.is_active and r.session_id is None)
                          needed = self.warm_resources - unassigned_count
                          self._lock_owner = threading.current_thread()
                      else:
                        unassigned_count = sum(1 for r in self.resources.values() if r.is_active and r.session_id is None)
                        needed = self.warm_resources - unassigned_count
                        self._lock_owner = threading.current_thread()

                      if needed > 0:
                          for _ in range(needed):
                              resource = self.create_resource_func()
                              if resource:
                                  self.resources[resource.debugging_port] = resource
                                  print(f"Warming up: Created resource at port {resource.debugging_port}")
                              else:
                                  print("Failed to create resource for warming up.")
                      elif needed < 0:
                          for resource_id, resource in self.resources.items():
                              if resource.is_active and resource.session_id is None:
                                  self.terminate_resource(resource_id)
                                  needed += 1
                                  print(f"Scaling down: Terminated resource at port {resource_id}")
                                  if needed == 0:
                                      break
                  finally:
                      self.lock.release()
              else:
                  print("Failed to acquire lock for maintain_warm_pool.")
              time.sleep(5)

      thread = threading.Thread(target=_maintain, daemon=True)
      thread.start()

    def start_resource_replacement_thread(self):
        """Starts a thread to periodically replace terminated resources."""
        def _replace_resources():
            while True:
                if self.lock.acquire(timeout=5):
                    try:
                        # Check if the current thread is the lock owner
                        if self.lock._is_owned():
                            inactive_ports = [resource_id for resource_id, resource in self.resources.items() if not resource.is_active]
                            self._lock_owner = threading.current_thread()
                        else:
                          inactive_ports = [resource_id for resource_id, resource in self.resources.items() if not resource.is_active]
                          self._lock_owner = threading.current_thread()
                        for resource_id in inactive_ports:
                            try:
                                new_resource = self.create_resource_func(resource_id)
                                if new_resource:
                                    self.resources[resource_id] = new_resource
                                    print(f"Replaced terminated resource at port {resource_id}.")
                                else:
                                    print(f"Failed to launch replacement resource at port {resource_id}.")

                            except Exception as e:
                                print(f"Error replacing resource at port {resource_id}: {e}")
                    finally:
                        self.lock.release()
                else:
                    print("Failed to acquire lock for start_resource_replacement_thread.")

                time.sleep(self.scale_down_interval)

        thread = threading.Thread(target=_replace_resources, daemon=True)
        thread.start()

    def _timeout_handler(self, resource_id: Any, session_id: str):
        if self.lock.acquire(timeout=5):
            try:
                if resource_id in self.resources:
                    resource = self.resources[resource_id]
                    # Check if the current thread is the lock owner
                    if self.lock._is_owned():
                        if resource.session_id == session_id:
                            print(f"Session {session_id} timed out. Terminating resource at port {resource_id}.")
                            self.terminate_resource(resource_id)
                        self._lock_owner = threading.current_thread()
                    else:
                      if resource.session_id == session_id:
                        print(f"Session {session_id} timed out. Terminating resource at port {resource_id}.")
                        self.terminate_resource(resource_id)
                      self._lock_owner = threading.current_thread()
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock for _timeout_handler.")

    def get_resource(self, timeout: int = 30) -> Optional[Tuple[Any, str]]:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.lock.acquire(timeout=5):
                try:
                    # Check if the current thread is the lock owner
                    if self.lock._is_owned():
                        if len(self.resources) < self.max_instances and all(r.session_id is not None for r in self.resources.values() if r.is_active):
                            self.all_resources_occupied = False
                            resource = self.create_resource_func()
                            if resource:
                                self.resources[resource.debugging_port] = resource
                                return self.assign_resource(resource, resource.debugging_port, timeout)
                        else:
                            for resource_id, resource in self.resources.items():
                                if resource.is_active and resource.session_id is None:
                                    return self.assign_resource(resource, resource_id, timeout)
                        self._lock_owner = threading.current_thread()
                    else:
                      if len(self.resources) < self.max_instances and all(r.session_id is not None for r in self.resources.values() if r.is_active):
                        self.all_resources_occupied = False
                        resource = self.create_resource_func()
                        if resource:
                            self.resources[resource.debugging_port] = resource
                            return self.assign_resource(resource, resource.debugging_port, timeout)
                      else:
                        for resource_id, resource in self.resources.items():
                            if resource.is_active and resource.session_id is None:
                                return self.assign_resource(resource, resource_id, timeout)
                      self._lock_owner = threading.current_thread()
                finally:
                    self.lock.release()
            else:
                print("Failed to acquire lock for get_resource.")
            time.sleep(0.5)

        print(f"No resource available within the timeout of {timeout} seconds.")
        return None

    def assign_resource(self, resource: Any, resource_id: Any, timeout: int) -> Tuple[Any, str]:
        """Assigns a resource to a session."""
        session_id = str(uuid.uuid4())

        if self.lock.acquire(timeout=5):
            try:
                # Check if the current thread is the lock owner
                if self.lock._is_owned():
                    resource.session_id = session_id
                    resource.last_used = time.time()
                    resource.timeout = timeout
                    resource.startup_attempts = 0
                    self._lock_owner = threading.current_thread()
                else:
                    resource.session_id = session_id
                    resource.last_used = time.time()
                    resource.timeout = timeout
                    resource.startup_attempts = 0
                    self._lock_owner = threading.current_thread()

                if resource.timeout_thread:
                    resource.timeout_thread.cancel()

                if timeout > 0:
                    resource.timeout_thread = threading.Timer(
                        timeout,
                        self._timeout_handler,
                        args=[resource_id, session_id]
                    )
                    resource.timeout_thread.start()

                self.sessions[session_id] = resource_id
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock for assign_resource.")
            return None, None

        return resource_id, session_id

    def terminate_resource(self, resource_id: Any) -> bool:
        """Terminates a resource and cleans up."""
        if self.lock.acquire(timeout=5):
            try:
                if resource_id in self.resources:
                    resource = self.resources[resource_id]

                    # Cancel the timer if it exists
                    if resource.timeout_thread:
                        resource.timeout_thread.cancel()
                        resource.timeout_thread = None

                    # Remove session
                    if resource.session_id:
                        self.sessions.pop(resource.session_id, None)

                    self.cleanup_browser(resource)

                    # Check if the current thread is the lock owner
                    if self.lock._is_owned():
                        resource.is_active = False
                        resource.session_id = None
                        self.available_ports.put(resource_id)
                        self._lock_owner = threading.current_thread()
                    else:
                        resource.is_active = False
                        resource.session_id = None
                        self.available_ports.put(resource_id)
                        self._lock_owner = threading.current_thread()
                    print(f"Resource at port {resource_id} terminated and resources cleaned up.")

                    return True
                print(f"No resource found at port {resource_id} to terminate.")
                return False
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock for terminate_resource.")
            return False

    def extend_timeout(self, session_id: str, additional_time: int) -> bool:
        if self.lock.acquire(timeout=5):
            try:
                if session_id in self.sessions:
                    resource_id = self.sessions[session_id]
                    resource = self.resources[resource_id]

                    if resource.timeout_thread:
                        resource.timeout_thread.cancel()
                    # Check if the current thread is the lock owner
                    if self.lock._is_owned():
                        resource.timeout = additional_time
                        self._lock_owner = threading.current_thread()
                    else:
                        resource.timeout = additional_time
                        self._lock_owner = threading.current_thread()

                    resource.timeout_thread = threading.Timer(
                        additional_time,
                        self._timeout_handler,
                        args=[resource_id, session_id]
                    )
                    resource.timeout_thread.start()
                    print(f"Timeout for session {session_id} extended by {additional_time} seconds.")
                    return True
                print(f"Session {session_id} not found.")
                return False
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock for extend_timeout.")
            return False

    def validate_session(self, session_id: str, resource_id: Any) -> bool:
        if self.lock.acquire(timeout=5):
            try:
                # Check if the current thread is the lock owner
                if self.lock._is_owned():
                    is_valid = (session_id in self.sessions and
                                self.sessions[session_id] == resource_id and
                                self.resources[resource_id].is_active)
                    self._lock_owner = threading.current_thread()
                else:
                    is_valid = (session_id in self.sessions and
                                self.sessions[session_id] == resource_id and
                                self.resources[resource_id].is_active)
                    self._lock_owner = threading.current_thread()
                if not is_valid:
                    print(f"Session validation failed for session_id: {session_id}, resource_id: {resource_id}")
                return is_valid
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock for validate_session.")
            return False

    def list_resources(self) -> List[dict]:
        if self.lock.acquire(timeout=5):
            try:
                return [
                    {
                        "resource_id": resource_id,
                        "active": resource.is_active,
                        "last_used": resource.last_used,
                        "session_id": resource.session_id,
                        "timeout": resource.timeout
                    }
                    for resource_id, resource in self.resources.items()
                ]
            finally:
                self.lock.release()
        else:
            print("Failed to acquire lock for list_resources.")
            return []