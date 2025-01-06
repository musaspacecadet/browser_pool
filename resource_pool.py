# resource_pool.py

import threading
import queue
import time
import uuid
import gc
from typing import List, Optional, Dict, Tuple, Callable, Any

class ResourcePool:
    def __init__(self, max_instances: int, create_resource_func: Callable, cleanup_resource_func: Callable, health_check_func: Callable, warm_resources: int = 0, health_check_interval: int = 60, scale_down_interval: int = 300):
        self.resources: Dict[Any, Any] = {}
        self.available_resource_ids = queue.Queue()
        self.lock = threading.RLock()
        self.sessions: Dict[str, Any] = {}
        self.create_resource_func = create_resource_func
        self.cleanup_resource_func = cleanup_resource_func
        self.health_check_func = health_check_func
        self.warm_resources = warm_resources
        self.health_check_interval = health_check_interval
        self.scale_down_interval = scale_down_interval
        self.all_resources_occupied = False
        self.max_instances = max_instances

        for i in range(max_instances):
            self.available_resource_ids.put(i)

        self.maintain_warm_pool()
        self.start_health_check_thread()
        ##self.start_resource_replacement_thread()

    def maintain_warm_pool(self):
        def _maintain():
            while True:
                with self.lock:
                    unassigned_count = len([r for r in self.resources.values() if r.is_active and r.session_id is None])
                    needed = max(0, self.warm_resources - unassigned_count)
                    for _ in range(needed):
                        try:
                            resource_id = self.available_resource_ids.get_nowait()
                            resource = self.create_resource_func(resource_id)
                            if resource:
                                self.resources[resource_id] = resource
                            else:
                                self.available_resource_ids.put(resource_id)
                                print(f"Failed to create resource for warming up at id {resource_id}.")

                        except queue.Empty:
                            print("No more resource IDs available to warm up.")
                            break
                time.sleep(5)

        thread = threading.Thread(target=_maintain, daemon=True)
        thread.start()

    def start_health_check_thread(self):
        """Starts a thread to periodically check the health of resources."""
        def _health_check():
            while True:
                with self.lock:
                    for resource_id, resource in self.resources.items():
                        if resource.is_active:
                            self.health_check_func(resource)
                time.sleep(self.health_check_interval)

        thread = threading.Thread(target=_health_check, daemon=True)
        thread.start()

    def start_resource_replacement_thread(self):
        """Starts a thread to periodically replace terminated resources."""
        def _replace_resources():
            while True:
                with self.lock:
                    inactive_ids = [resource_id for resource_id, resource in self.resources.items() if not resource.is_active]
                    for resource_id in inactive_ids:
                        try:
                            new_resource = self.create_resource_func(resource_id)
                            if new_resource:
                                self.resources[resource_id] = new_resource
                                print(f"Replaced terminated resource at id {resource_id}.")
                            else:
                                print(f"Failed to launch replacement resource at id {resource_id}.")

                        except Exception as e:
                            print(f"Error replacing resource at id {resource_id}: {e}")
                time.sleep(self.scale_down_interval)

        thread = threading.Thread(target=_replace_resources, daemon=True)
        thread.start()

    def _timeout_handler(self, resource_id: Any, session_id: str):
        if resource_id in self.resources:
            resource = self.resources[resource_id]
            if resource.session_id == session_id:
                print(f"Session {session_id} timed out. Terminating resource at id {resource_id}.")
                self.terminate_resource(resource_id)

    def get_resource(self, timeout: int = 30) -> Optional[Tuple[Any, str]]:
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self.lock:
                if all(r.session_id is not None for r in self.resources.values() if r.is_active):
                    self.all_resources_occupied = True
                else:
                    self.all_resources_occupied = False

                if self.all_resources_occupied:
                    print("All resources are currently occupied.")
                    return None

                for resource_id, resource in self.resources.items():
                    if resource.is_active and resource.session_id is None:
                        return self.assign_resource(resource, resource_id, timeout)

            time.sleep(0.5)

        print(f"No resource available within the timeout of {timeout} seconds.")
        return None

    def assign_resource(self, resource: Any, resource_id: Any, timeout: int) -> Tuple[Any, str]:
        """Assigns a resource to a session."""
        session_id = str(uuid.uuid4())
        resource.session_id = session_id
        resource.last_used = time.time()
        resource.timeout = timeout
        resource.startup_attempts = 0

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
        return resource_id, session_id

    def terminate_resource(self, resource_id: Any) -> bool:
        """Terminates a resource and cleans up."""
        with self.lock:
            if resource_id in self.resources:
                resource = self.resources[resource_id]

                # Cancel the timer if it exists
                if resource.timeout_thread:
                    resource.timeout_thread.cancel()
                    resource.timeout_thread = None

                # Remove session
                if resource.session_id:
                    self.sessions.pop(resource.session_id, None)

                self.cleanup_resource_func(resource)

                resource.is_active = False
                resource.session_id = None
                self.available_resource_ids.put(resource_id)
                print(f"Resource at id {resource_id} terminated and resources cleaned up.")

                # Trigger garbage collection
                gc.collect()

                return True
            print(f"No resource found at id {resource_id} to terminate.")
            return False

    def extend_timeout(self, session_id: str, additional_time: int) -> bool:
        with self.lock:
            if session_id in self.sessions:
                resource_id = self.sessions[session_id]
                resource = self.resources[resource_id]

                if resource.timeout_thread:
                    resource.timeout_thread.cancel()

                resource.timeout = additional_time
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

    def validate_session(self, session_id: str, resource_id: Any) -> bool:
        with self.lock:
            is_valid = (session_id in self.sessions and
                        self.sessions[session_id] == resource_id and
                        self.resources[resource_id].is_active)
            if not is_valid:
                print(f"Session validation failed for session_id: {session_id}, resource_id: {resource_id}")
            return is_valid

    def list_resources(self) -> List[dict]:
        with self.lock:
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