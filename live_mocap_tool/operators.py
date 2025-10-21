import bpy
import time
from . import data_stream
from . import mocap_logic
from . import ui_panel # Import to access the UIList operators

# Global variable to hold the receiver instance
MOCAP_RECEIVER = None

class MOCAP_OT_live_capture(bpy.types.Operator):
    """Starts the live motion capture streaming."""
    bl_idname = "mocap.live_capture"
    bl_label = "Start Live Mocap"

    _timer = None
    
    def modal(self, context, event):
        global MOCAP_RECEIVER
        props = context.scene.mocap_properties
        
        # 1. Stop Condition 
        if not MOCAP_RECEIVER or not MOCAP_RECEIVER.running:
            # If the receiver thread has naturally ended or been stopped by MOCAP_OT_stop_capture
            if props.is_running:
                return self.cancel(context)
            else:
                return {'PASS_THROUGH'} # Allow other events to be processed

        # 2. Main Update Loop (only run on TIMER events, ensures regular update rate)
        if event.type == 'TIMER':
            
            # --- Performance/Status Update ---
            # Update is_running status based on the receiver thread's state
            props.is_running = MOCAP_RECEIVER.running
            
            # Only process data if we are actively connected and receiving
            if MOCAP_RECEIVER.status == data_stream.STATUS_CONNECTED:
                mocap_data = MOCAP_RECEIVER.get_latest_data()
                
                if mocap_data:
                    # Debug: show what keys arrived in the frame (helps diagnose mediapipe presence)
                    try:
                        keys = list(mocap_data.keys()) if isinstance(mocap_data, dict) else []
                        print(f"[MOCAP] Received frame keys: {keys}")
                    except Exception:
                        pass
                    armature_obj = props.target_armature
                    if armature_obj:
                        # Set a flag that data is currently flowing
                        props.data_active = True 
                        
                        # Call the core logic to apply transforms
                        mocap_logic.apply_mocap_data(armature_obj, mocap_data)
                    else:
                        self.report({'WARNING'}, "No target armature selected to apply Mocap data.")
                else:
                    # If connected but no data for a bit, set data_active to False
                    props.data_active = False 
            
            else:
                 # Ensure data_active is false if not connected (e.g., in RECONNECTING state)
                 props.data_active = False


        return {'PASS_THROUGH'}


    def execute(self, context):
        global MOCAP_RECEIVER
        props = context.scene.mocap_properties
        
        if props.is_running:
            self.report({'WARNING'}, "Mocap Stream is already running.")
            return {'CANCELLED'}
            
        # Auto-select single armature if none is set (convenience)
        if not props.target_armature:
            arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
            if arm:
                props.target_armature = arm
                self.report({'INFO'}, f"Auto-selected armature: {arm.name}")

        # Try to auto-map common mixamorig bone names if we have an armature selected
        try:
            if props.target_armature:
                # This will populate props.mapping_collection where possible
                mocap_logic.auto_map_mixamorig(props)
        except Exception as e:
            print(f"Auto-mapping warning: {e}")

        # 1. Initialize and start the receiver thread
        try:
            MOCAP_RECEIVER = data_stream.MocapReceiver(props.ip_address, props.port_number)
            MOCAP_RECEIVER.start()
            
            # 2. Setup the modal timer
            # Update frequency (1/60th of a second for 60 FPS)
            wm = context.window_manager
            self._timer = wm.event_timer_add(1.0 / 60.0, window=context.window) 
            context.window_manager.modal_handler_add(self)
            
            props.is_running = True
            props.data_active = False # Reset active flag
            
            self.report({'INFO'}, f"Mocap Stream started. Connecting to {props.ip_address}:{props.port_number}...")
            return {'RUNNING_MODAL'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to start Mocap Stream: {e}")
            if MOCAP_RECEIVER:
                MOCAP_RECEIVER.stop()
            MOCAP_RECEIVER = None
            return {'CANCELLED'}

    def cancel(self, context):
        global MOCAP_RECEIVER
        props = context.scene.mocap_properties
        
        # 1. Stop the background thread
        if MOCAP_RECEIVER:
            MOCAP_RECEIVER.stop()
        
        # 2. Remove the timer
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None
        
        # 3. Reset properties
        props.is_running = False
        props.data_active = False
        MOCAP_RECEIVER = None

        self.report({'INFO'}, "Mocap Stream Stopped.")
        return {'CANCELLED'}

# --- Stop Operator ---
class MOCAP_OT_stop_capture(bpy.types.Operator):
    """Utility operator to stop the live motion capture streaming."""
    bl_idname = "mocap.stop_capture"
    bl_label = "Stop Live Mocap"
    
    def execute(self, context):
        global MOCAP_RECEIVER
        
        # This triggers the receiver thread's stop flag, which the modal checks
        if MOCAP_RECEIVER and MOCAP_RECEIVER.running:
            MOCAP_RECEIVER.stop() 
            self.report({'INFO'}, "Stop signal sent to Mocap Stream.")
        else:
            self.report({'INFO'}, "Mocap Stream is not currently running.")
            # Also force the is_running flag to false in case the modal operator is stuck
            context.scene.mocap_properties.is_running = False
            context.scene.mocap_properties.data_active = False

        return {'FINISHED'}

class MOCAP_OT_calibrate_pose(bpy.types.Operator):
    """Calibrates the target armature's current pose as the zero offset."""
    bl_idname = "mocap.calibrate_pose"
    bl_label = "Calibrate Pose Offset"
    bl_description = "Use the armature's current pose (T-Pose, A-Pose) as the zero point for Mocap rotations."
    
    def execute(self, context):
        props = context.scene.mocap_properties
        armature_obj = props.target_armature
        
        if not armature_obj:
            self.report({'ERROR'}, "Please select a target Armature before calibrating.")
            return {'CANCELLED'}
        
        # Call the logic function to capture the current pose
        if mocap_logic.calibrate_pose(armature_obj):
            self.report({'INFO'}, "Calibration successful. Armature pose saved as zero offset.")
        else:
            self.report({'ERROR'}, "Calibration failed. Check console for details.")

        return {'FINISHED'}

# --- Bone Mapping Management Operators (For the UIList) ---

class MOCAP_OT_add_mapping(bpy.types.Operator):
    """Adds a new bone mapping entry to the list."""
    bl_idname = "mocap.add_mapping"
    bl_label = "Add Mapping"
    bl_description = "Add a new Mocap Joint to Blender Bone mapping pair."

    def execute(self, context):
        props = context.scene.mocap_properties
        # Use a list of default names to help user
        default_mocap_name = f"Mocap_Joint_{len(props.mapping_collection) + 1}"
        default_blender_name = f"Bone_{len(props.mapping_collection) + 1}"
        
        item = props.mapping_collection.add()
        item.mocap_name = default_mocap_name
        item.blender_name = default_blender_name
        
        # Select the newly added item
        props.mapping_index = len(props.mapping_collection) - 1
        return {'FINISHED'}

class MOCAP_OT_remove_mapping(bpy.types.Operator):
    """Removes the selected bone mapping entry from the list."""
    bl_idname = "mocap.remove_mapping"
    bl_label = "Remove Mapping"
    bl_description = "Remove the selected mapping pair."

    def execute(self, context):
        props = context.scene.mocap_properties
        mapping_list = props.mapping_collection
        index = props.mapping_index
        
        if 0 <= index < len(mapping_list):
            mapping_list.remove(index)
            # Adjust index to avoid going out of bounds
            props.mapping_index = min(index, len(mapping_list) - 1) 
            
        return {'FINISHED'}
