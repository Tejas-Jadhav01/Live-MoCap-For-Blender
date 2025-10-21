# Live-MoCap-For-Blender

Live-MoCap-For-Blender is a lightweight toolkit and Blender add-on for receiving and applying live motion-capture data to armatures inside Blender in real time. It aims to let animators and developers stream motion data (WebSocket/UDP/VRPN/OSC/ROS/other) into Blender, map incoming skeletons to Blender armatures, and preview or record live animation.



Table of contents
- Project overview
- Key features
- Requirements
- Supported sources / protocols
- Quick install (user)
- Quick install (developer / from source)
- Usage
- Configuration & mapping
- Troubleshooting
- Development and contribution
- Roadmap & known missing pieces
- License & credits

Project overview
----------------
Live-MoCap-For-Blender connects live motion capture sources to Blender so you can preview, retarget, and record animated armatures in real time. Use it for live puppeteering, previs, virtual production, or performance capture workflows.

Key features
------------
- Connect to live mocap feeds (WebSocket, UDP, OSC, VRPN, etc.)
- Map incoming skeletons to Blender armatures with configurable retargeting
- Stream pose updates frame-by-frame to Blender object bones
- Record live animation to NLA/Action for later editing
- Lightweight and designed to be extended for custom protocols and input devices

Requirements
------------
- Blender 3.x or later (tested with 3.0+; adjust if you need other versions)
- Python 3.8+ (Blender bundles its own Python — addon must be compatible)
- OS: Windows / macOS / Linux
- Network access if using networked mocap sources
- (Optional) Dependencies listed in requirements.txt (see developer section)

Supported sources / protocols (examples)
----------------------------------------
- WebSocket (JSON messages)
- UDP (custom binary or text formats)
- OSC (Open Sound Control)
- VRPN (via appropriate Python bindings)
- ROS messages (ROS bridge or ROS2)
- Custom sources (extend connector layer)

Quick install (user)
--------------------
1. Download or clone this repository:
   git clone https://github.com/Tejas-Jadhav01/Live-MoCap-For-Blender.git
2. In Blender:
   - Edit > Preferences > Add-ons > Install...
   - Select the zipped add-on or the add-on folder inside this repo (the folder that contains __init__.py for the Blender add-on).
   - Enable the add-on from the list.
3. Open the Live MoCap panel (usually in the 3D View > Sidebar or Properties > Scene) to configure source, port, and mapping.
4. Start your mocap source. Click "Connect" in the add-on UI. Incoming frames will update the selected armature.
5. To record: enable "Record to Action" and press Start/Stop recording.

Quick install (developer / from source)
---------------------------------------
1. Clone the repo:
   git clone https://github.com/Tejas-Jadhav01/Live-MoCap-For-Blender.git
   cd Live-MoCap-For-Blender
2. (Optional) Create virtual environment for offline tooling (tests/linting):
   python -m venv .venv
   source .venv/bin/activate   # macOS/Linux
   .venv\Scripts\activate      # Windows
3. Install development dependencies (if provided):
   pip install -r requirements.txt
4. Open Blender and install as developer add-on (use "Install from File" and point to the add-on folder). For live development, use Blender's "Install Add-on from File" and enable "Auto Reload" (or use the built-in add-on reloading workflow).

Usage
-----
- Configure the incoming protocol (WebSocket/UDP/OSC/Custom) and port.
- Choose the target armature in Blender and map the incoming joint names to Blender bones.
- Adjust retargeting options: scale, offset, axis remapping, joint filters.
- Toggle smoothing/interpolation and sample-rate handling for stable playback.
- Record to Action or NLA strip if you want persistent animation clips.

Configuration & mapping
-----------------------
- Mapping UI should allow:
  - Automatic mapping by name (if the mocap joint names match Blender bone names)
  - Manual mapping via dropdowns or drag-and-drop
  - Save/load mapping presets per rig
- Retargeting pipeline:
  - Joint name mapping -> pre-scale -> axis conversion -> rotation order handling -> bone constraints or direct pose application
- Provide a "Test Frame" feature to sanity-check mapping without a live feed.

Troubleshooting
---------------
- If Blender doesn't receive data:
  - Verify network settings and firewall
  - Confirm the mocap server is sending to the configured port and host
  - Use a simple test client (netcat, websocat) to see raw traffic
- If bones appear mirrored or rotated:
  - Check axis conversion settings and root orientation
  - Use local space vs world space toggles
- High jitter:
  - Enable smoothing or interpolation
  - Lower incoming update rate or throttle updates in add-on
- If the add-on fails to install:
  - Check that __init__.py exists and register/unregister functions are correct
  - See the console output (Window > Toggle System Console on Windows)

Development and contribution
----------------------------
If you plan to contribute:
- Follow consistent coding style (PEP8, type hints where helpful)
- Write unit tests for protocol parsing and mapping logic
- Add integration tests that simulate streams (use fixtures that send prerecorded packets)
- Provide reproducible examples and a small test data generator


License & credits
-----------------
- Add a LICENSE file (MIT recommended if you want permissive open-source)
- Crediting: list contributors and any third-party libraries used

Contact
-------
- Repo: https://github.com/Tejas-Jadhav01/Live-MoCap-For-Blender
- Author: Tejas-Jadhav01
- For issues and feature requests: open a GitHub issue

Examples
--------
- Include a folder `examples/` with:
  - Example mocap JSON frames
  - A sample Blender file (.blend) with a pre-rigged armature and saved mapping
  - A simple mock server script to stream example frames over WebSocket/UDP
