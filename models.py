# models.py

import subprocess
from dataclasses import dataclass
from typing import Optional
import threading

@dataclass
class ProxyInstance:
    process: subprocess.Popen
    external_port: int
    internal_port: int

@dataclass
class BrowserInstance:
    process: subprocess.Popen
    debugging_port: int
    last_used: float
    profile_path: str
    startup_attempts: int = 0
    proxy: Optional[ProxyInstance] = None
    session_id: Optional[str] = None
    timeout: Optional[int] = None
    timeout_thread: Optional[threading.Timer] = None
    is_active: bool = True