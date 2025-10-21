import bpy
from bpy.types import Panel, UIList
from . import operators, data_stream

# --- UI List for Bone Mappings ---

class MOCAP_UL_bone_list(UIList):
    """Draws the list of Mocap-to-Blender bone mappings."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # We need the item to display its properties
        custom_icon = 'BONE_DATA'
        
        row = layout.row(align=True)
        # Mocap Joint Name (Source)
        row.prop(item, "mocap_name", text="", emboss=False)

        # Separator
        row.label(text='→')

        # Blender Bone Name (Target)
        row.prop(item, "blender_name", text="", emboss=False)


# --- Main Control Panel ---

class MOCAP_PT_control_panel(Panel):
    """Creates a Mocap Control Panel in the 3D Viewport (N-Panel)"""
    bl_label = "Live Mocap Controller"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Mocap"

    def draw(self, context):
        import traceback
        layout = self.layout
        try:
            props = context.scene.mocap_properties

            # Get the current receiver status from the thread-safe property
            receiver_status = operators.MOCAP_RECEIVER.status if operators.MOCAP_RECEIVER else data_stream.STATUS_DISCONNECTED

            # --- Connection Status Display (Dynamic Feedback) ---
            box = layout.box()
            status_row = box.row()

            label = "IDLE (Not Running)"
            if receiver_status == data_stream.STATUS_CONNECTED:
                if props.data_active:
                    label = "LIVE STREAMING"
                else:
                    label = "CONNECTED (Waiting for Data)"
            elif receiver_status == data_stream.STATUS_CONNECTING:
                label = "CONNECTING..."
            elif receiver_status == data_stream.STATUS_RECONNECTING:
                label = "RECONNECTING..."
            elif receiver_status == data_stream.STATUS_ERROR:
                label = "ERROR: See Console"

            status_row.label(text=label)

            # --- Configuration ---
            layout.label(text="Setup")

            # Target Armature Selector
            layout.prop(props, "target_armature")

            # Calibration Button (Only active when an armature is selected)
            row = layout.row()
            # Disable the button when no armature is selected
            row.enabled = (props.target_armature is not None)
            row.operator("mocap.calibrate_pose", text="Calibrate Pose")

            layout.separator()

            # Mocap Mode Toggle
            layout.label(text="Mocap Mode:")
            row = layout.row(align=True)
            row.prop(props, "mocap_mode", expand=True)

            # IP and Port settings
            layout.label(text="Network Settings:")
            split = layout.split(factor=0.6)
            split.prop(props, "ip_address", text="IP")
            split.prop(props, "port_number", text="Port")

            layout.separator()

            # --- Control Button ---
            if props.is_running:
                # STOP button is visible when running
                layout.operator("mocap.stop_capture", text="STOP Live Capture")
            else:
                # START button is visible when stopped; disable if no armature selected
                row = layout.row()
                row.enabled = (props.target_armature is not None)
                row.operator("mocap.live_capture", text="START Live Capture")

            layout.separator(factor=0.5)

            # --- Bone Mapping UI List ---
            layout.label(text="Bone Mapping (Mocap -> Blender)")

            row = layout.row()
            # Draw the custom UI list
            row.template_list("MOCAP_UL_bone_list", "mocap_bone_list",
                              props, "mapping_collection",
                              props, "mapping_index")

            # Add/Remove buttons for the list
            col = row.column(align=True)
            col.operator("mocap.add_mapping", text="")
            col.operator("mocap.remove_mapping", text="")

            # Display properties for the selected item below the list
            if 0 <= props.mapping_index < len(props.mapping_collection):
                item = props.mapping_collection[props.mapping_index]
                box2 = layout.box()
                box2.label(text="Selected Mapping:")
                box2.prop(item, "mocap_name")
                box2.prop(item, "blender_name")
        except Exception:
            # Prevent UI from crashing; show a simple label and print traceback to system console
            layout.label(text="Live Mocap UI Error - check system console")
            print("[Live Mocap] UI draw error:")
            traceback.print_exc()
