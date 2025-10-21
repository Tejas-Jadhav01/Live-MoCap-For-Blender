import socket
import time
import json
import random
import threading

# Optional OpenCV support for camera capture
try:
    import cv2
    HAVE_CV2 = True
except Exception:
    cv2 = None
    HAVE_CV2 = False
    
# Optional MediaPipe support for landmark detection (hands/pose)
try:
    import mediapipe as mp
    HAVE_MEDIAPIPE = True
except Exception:
    mp = None
    HAVE_MEDIAPIPE = False

# Configuration
HOST = '127.0.0.1'
PORT = 5555
MAX_CONNECTIONS = 1

# Mock Data Generation
def generate_mock_frame():
    """Generates a sample JSON string for a single Mocap frame."""
    
    # Simulate a small rotation change (Quaternions [w, x, y, z])
    rot_w = 0.9 + random.uniform(-0.01, 0.01)
    rot_x = 0.05 + random.uniform(-0.01, 0.01)
    rot_y = 0.1 + random.uniform(-0.01, 0.01)
    rot_z = 0.0
    
    # Simulate Hand index finger curl
    hand_rot_w = 0.99
    hand_rot_z = random.uniform(0.0, 0.2) # Index finger curl
    
    # NOTE: The keys here must match the default Mocap Joint Names in __init__.py
    data = {
        "mode": "WHOLE_BODY",
        "camera_active": bool(CAMERA.running) if 'CAMERA' in globals() else False,
        "mediapipe": CAMERA.last_mediapipe if ('CAMERA' in globals() and CAMERA.last_mediapipe) else None,
        "joints": {
            # Hips location (Blender uses Z-up, so Z is height)
            "Hips": {"location": [0.0, 0.0, 1.0 + random.uniform(-0.005, 0.005)], 
                     "rotation_wzxy": [1.0, 0.0, 0.0, 0.0]},
            
            "Spine": {"rotation_wzxy": [rot_w, rot_x, rot_y, rot_z]},
            
            # Simple rotation for the arm
            "RightShoulder": {"rotation_wzxy": [0.99, 0.0, 0.0, 0.1]}, 
            "LeftShoulder": {"rotation_wzxy": [0.99, 0.0, 0.0, -0.1]}, 
            
            # Finger data (used for both WHOLE_BODY and HANDS_ONLY modes)
            "RightHandIndex1": {"rotation_wzxy": [hand_rot_w, 0.0, 0.0, hand_rot_z]},
            "LeftHandIndex1": {"rotation_wzxy": [hand_rot_w, 0.0, 0.0, -hand_rot_z]},
            
            # Additional joints can be added here
        }
    }
    
    # Convert to JSON string and append newline delimiter
    return json.dumps(data) + '\n'


class CameraCapture:
    """Simple camera capture thread using OpenCV. Shows a small window and tracks running state.

    This is optional; the script will continue to run without OpenCV installed.
    """
    def __init__(self, device=0, show_window=False):
        self.device = device
        self.show_window = show_window
        self.running = False
        self._thread = None
        self.last_frame = None
        self.last_mediapipe = None

    def start(self):
        if not HAVE_CV2:
            print("OpenCV not available: camera capture disabled. Install with 'pip install opencv-python'.")
            return
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        cap = None
        try:
            cap = cv2.VideoCapture(self.device, cv2.CAP_DSHOW if hasattr(cv2, 'CAP_DSHOW') else 0)
            if not cap or not cap.isOpened():
                print(f"Failed to open camera device {self.device}.")
                self.running = False
                return

            print(f"Camera device {self.device} opened.")

            # Setup MediaPipe if available
            mp_hands = None
            mp_pose = None
            mp_drawing = None
            mp_hands_proc = None
            mp_pose_proc = None
            # Use a local flag so we don't rebind the global HAVE_MEDIAPIPE
            have_mediapipe = HAVE_MEDIAPIPE
            if have_mediapipe:
                try:
                    mp_drawing = mp.solutions.drawing_utils
                    # We'll try hands first; pose can be added similarly
                    mp_hands = mp.solutions.hands
                    mp_pose = mp.solutions.pose
                    mp_hands_proc = mp_hands.Hands(static_image_mode=False,
                                                   max_num_hands=2,
                                                   min_detection_confidence=0.5,
                                                   min_tracking_confidence=0.5)
                    mp_pose_proc = mp_pose.Pose(static_image_mode=False,
                                                min_detection_confidence=0.5,
                                                min_tracking_confidence=0.5)
                except Exception as e:
                    print(f"MediaPipe initialization failed: {e}")
                    have_mediapipe = False

            prev_ts = time.time()
            fps = 0.0
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    # camera read failed; stop
                    print("Camera frame read failed; stopping camera thread.")
                    break

                # Basic processing: flip/frame conversion as needed
                display = frame.copy()

                # MediaPipe processing (if available)
                mp_status = 'MediaPipe: N/A'
                try:
                    if have_mediapipe and mp_hands_proc is not None:
                        # Convert BGR to RGB for MediaPipe
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        results_hands = mp_hands_proc.process(rgb)
                        results_pose = mp_pose_proc.process(rgb) if mp_pose_proc is not None else None
                        # Draw hand landmarks
                        if results_hands and results_hands.multi_hand_landmarks:
                            for hand_landmarks in results_hands.multi_hand_landmarks:
                                try:
                                    mp_drawing.draw_landmarks(display, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                                except Exception:
                                    pass
                        # Draw pose landmarks
                        if results_pose and results_pose.pose_landmarks:
                            try:
                                mp_drawing.draw_landmarks(display, results_pose.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                            except Exception:
                                pass
                        # Prepare mediapipe landmark structures for external use
                        try:
                            pose_list = []
                            if results_pose and results_pose.pose_landmarks:
                                for lm in results_pose.pose_landmarks.landmark:
                                    pose_list.append([lm.x, lm.y, lm.z])

                            hands_dict = {}
                            if results_hands and results_hands.multi_hand_landmarks:
                                # Use handedness from results_hands.multi_handedness to label left/right
                                try:
                                    for hand_idx, hand_landmarks in enumerate(results_hands.multi_hand_landmarks):
                                        handedness = results_hands.multi_handedness[hand_idx].classification[0].label
                                        # convert landmarks
                                        hand_list = [[lm.x, lm.y, lm.z] for lm in hand_landmarks.landmark]
                                        hands_dict[handedness.lower()] = hand_list
                                except Exception:
                                    # fallback: store as numeric keys
                                    for i, hand_landmarks in enumerate(results_hands.multi_hand_landmarks):
                                        hand_list = [[lm.x, lm.y, lm.z] for lm in hand_landmarks.landmark]
                                        hands_dict[str(i)] = hand_list

                            self.last_mediapipe = {
                                'pose': pose_list,
                                'hands': hands_dict
                            }
                        except Exception:
                            # ignore mediapipe serialization errors
                            self.last_mediapipe = None

                        mp_status = 'MediaPipe: OK'
                except Exception:
                    mp_status = 'MediaPipe: Error'

                # Overlay status text: OpenCV and MediaPipe availability and FPS
                now = time.time()
                dt = now - prev_ts
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else (1.0 / dt)
                prev_ts = now

                cv2.putText(display, f"OpenCV: {'OK' if HAVE_CV2 else 'N/A'}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0) if HAVE_CV2 else (0,0,255), 2)
                cv2.putText(display, f"{mp_status}", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0) if mp_status=='MediaPipe: OK' else (0,0,255), 2)
                cv2.putText(display, f"FPS: {fps:.1f}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)

                self.last_frame = display

                # Optionally display a window for verification
                if self.show_window:
                    try:
                        cv2.imshow('MockCam', cv2.resize(display, (960, 540)))
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            # allow user to quit the window
                            break
                    except Exception:
                        # ignore GUI errors
                        pass

                # throttle a bit to reduce CPU
                time.sleep(0.01)

        except Exception as e:
            print(f"Camera thread error: {e}")
        finally:
            try:
                if cap:
                    cap.release()
            except Exception:
                pass
            try:
                if self.show_window:
                    cv2.destroyWindow('MockCam')
            except Exception:
                pass
            self.running = False

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)


# Global camera instance (optional); show_window=True to display feed by default
CAMERA = CameraCapture(device=0, show_window=True)

def handle_client(conn, addr):
    """Handles data transmission to a single connected client (Blender)."""
    print(f"Connection established with {addr}")
    
    try:
        while True:
            # Generate the latest mock frame
            frame_data = generate_mock_frame()
            
            # Send data to the client
            conn.sendall(frame_data.encode('utf-8'))
            
            # Send data at roughly 60 FPS (1/60 = 0.0166 seconds)
            time.sleep(0.016)
            
    except ConnectionResetError:
        print(f"Client {addr} disconnected abruptly.")
    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        print(f"Connection with {addr} closed.")

def start_server():
    """Starts the main TCP server listener."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(MAX_CONNECTIONS)
        print(f"Mock Mocap Server started on {HOST}:{PORT}")
        print("Waiting for Blender to connect... (Press Ctrl+C to stop)")
        
        # Start optional camera capture
        try:
            if 'CAMERA' in globals():
                CAMERA.start()
        except Exception:
            pass

        while True:
            try:
                conn, addr = s.accept()
                # Handle each client in a new thread (though we only allow 1 max)
                client_thread = threading.Thread(target=handle_client, args=(conn, addr))
                client_thread.start()
            except KeyboardInterrupt:
                print("\nServer shutting down.")
                break
            except Exception as e:
                print(f"Server error: {e}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Mock Mocap Server with optional camera preview')
    parser.add_argument('--no-window', action='store_true', help='Do not show the camera preview window')
    parser.add_argument('--device', type=int, default=0, help='Camera device index (default 0)')
    args = parser.parse_args()

    # Configure camera options
    if 'CAMERA' in globals():
        CAMERA.show_window = not args.no_window
        CAMERA.device = args.device

    start_server()
