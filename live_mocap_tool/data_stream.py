import socket
import threading
import json
import time
from queue import Queue, Empty

# Status Definitions
STATUS_DISCONNECTED = "DISCONNECTED"
STATUS_CONNECTING = "CONNECTING"
STATUS_CONNECTED = "CONNECTED"
STATUS_RECONNECTING = "RECONNECTING"
STATUS_ERROR = "ERROR"

class MocapReceiver:
    """
    Handles non-blocking, real-time data reception via a TCP socket in a separate thread.
    Includes reconnection logic and thread safety.
    """
    def __init__(self, ip, port, max_queue_size=1):
        self.ip = ip
        self.port = port
        self.running = False
        self.thread = None
        # Use a Queue to pass data safely between threads (max_queue_size=1 means only the latest frame is kept)
        self.data_queue = Queue(maxsize=max_queue_size) 
        self._status = STATUS_DISCONNECTED
        self.lock = threading.Lock() # Lock for thread-safe status updates

    @property
    def status(self):
        """Thread-safe status getter."""
        with self.lock:
            return self._status

    @status.setter
    def status(self, value):
        """Thread-safe status setter."""
        with self.lock:
            self._status = value

    def start(self):
        """Starts the background thread for socket listening."""
        if self.running:
            print("Receiver already running.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_socket_listener, daemon=True)
        self.thread.start()
        print(f"MocapReceiver thread starting for {self.ip}:{self.port}")

    def stop(self):
        """Sets the flag to stop the thread gracefully."""
        self.running = False
        if self.thread:
            # Optionally join the thread with a timeout to wait for it to finish
            self.thread.join(timeout=1.0)
            if self.thread.is_alive():
                print("Warning: Receiver thread did not stop gracefully.")
        self.thread = None
        self.status = STATUS_DISCONNECTED


    def _connect_socket(self, timeout=2.0):
        """Attempts to connect the socket, handling timeouts and failures."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Using SO_REUSEADDR helps with rapid restarts
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
        sock.settimeout(timeout) # Timeout for initial connection attempt

        try:
            print(f"Attempting connection to {self.ip}:{self.port}...")
            self.status = STATUS_CONNECTING
            sock.connect((self.ip, self.port))
            
            # Set a smaller timeout for the main receive loop
            sock.settimeout(0.1) 
            self.status = STATUS_CONNECTED
            print("Connection successful.")
            return sock
        except socket.error as e:
            # Specific error handling for connection issues
            print(f"Connection failed: {e}. Retrying...")
            sock.close()
            self.status = STATUS_RECONNECTING
            return None


    def _run_socket_listener(self):
        """The main loop for the background thread, handles connection and data reception."""
        
        reconnect_delay = 1.0
        
        while self.running:
            # 1. Connection/Reconnection Loop
            sock = None
            while self.running and not sock:
                if self.status != STATUS_CONNECTING:
                    self.status = STATUS_RECONNECTING
                
                sock = self._connect_socket(timeout=reconnect_delay)
                if not sock:
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 8.0) # Exponential backoff up to 8s
                else:
                    reconnect_delay = 1.0 # Reset delay on successful connection

            if not self.running:
                break # Exit if stop() was called during connection attempt

            # 2. Data Reception Loop (only runs when connected)
            buffer = ""
            while self.running and sock:
                try:
                    # Receive small chunks to keep the socket non-blocking
                    chunk = sock.recv(4096).decode('utf-8')
                    
                    if not chunk:
                        # Server closed the connection gracefully (recv returns 0 bytes)
                        self.status = STATUS_RECONNECTING
                        print("Server closed connection. Attempting reconnection...")
                        break
                        
                    buffer += chunk
                    
                    # Process the buffer for complete JSON messages (separated by newline)
                    while '\n' in buffer:
                        mocap_line, buffer = buffer.split('\n', 1)
                        if not mocap_line.strip():
                            continue

                        try:
                            mocap_frame = json.loads(mocap_line)
                            
                            # Safely put data into the queue (dropping old frames if queue is full)
                            if self.data_queue.full():
                                # Clear the old frame to make room for the new one
                                self.data_queue.get_nowait() 
                            self.data_queue.put_nowait(mocap_frame)
                                    
                        except json.JSONDecodeError:
                            print(f"Warning: Received invalid JSON frame: {mocap_line[:50]}...")
                            # Attempt to clear buffer up to the next newline to discard invalid data
                            buffer = buffer.split('\n', 1)[-1]
                            
                except socket.timeout:
                    # Expected timeout for non-blocking check, loop continues
                    pass
                except ConnectionResetError:
                    self.status = STATUS_RECONNECTING
                    print("Connection reset by peer (server crashed?). Attempting reconnection...")
                    break
                except Exception as e:
                    self.status = STATUS_ERROR
                    print(f"Critical socket error during data stream: {e}")
                    time.sleep(1) # Small pause before next connection attempt
                    break
            
            # Close the current socket before attempting to reconnect or exiting
            if sock:
                sock.close()
            
        self.status = STATUS_DISCONNECTED
        print("MocapReceiver thread ended cleanly.")


    def get_latest_data(self):
        """Called by the main thread to safely retrieve the latest data (non-blocking)."""
        # We only care about the latest frame, so clear out older ones
        latest = None
        while True:
            try:
                latest = self.data_queue.get_nowait()
            except Empty:
                return latest # Return the last frame retrieved, or None if the queue was empty initially
