import bpy
from mathutils import Quaternion, Vector, Matrix

# --- Calibration Storage ---
# Stores the initial rotation offset for each bone to zero out the T-pose discrepancy.
# Key: Blender Bone Name (e.g., 'Mocap_Spine'), Value: mathutils.Quaternion (offset)
CALIBRATION_OFFSETS = {}

def get_bone_map_from_properties():
    """Dynamically builds the Mocap-to-Blender bone map from the addon properties."""
    props = bpy.context.scene.mocap_properties
    bone_map = {}
    for item in props.mapping_collection:
        # Ensure both names are provided before adding to the live map
        if item.mocap_name and item.blender_name:
            bone_map[item.mocap_name] = item.blender_name
    return bone_map


def auto_map_mixamorig(props):
    """Attempt to auto-populate `props.mapping_collection` for common mixamorig rigs.

    This will only add mappings that match existing pose bone names in the selected armature.
    """
    # Defensive: ensure we have an armature object
    arm_obj = props.target_armature
    if not arm_obj or arm_obj.type != 'ARMATURE':
        return

    pose_names = {pb.name for pb in arm_obj.pose.bones}

    wanted = {
        'Hips': 'mixamorig:Hips',
        'Spine': 'mixamorig:Spine',
        'Neck': 'mixamorig:Neck',
        'Head': 'mixamorig:Head',
        'LeftShoulder': 'mixamorig:LeftShoulder',
        'LeftElbow': 'mixamorig:LeftForeArm',
        'LeftWrist': 'mixamorig:LeftHand',
        'RightShoulder': 'mixamorig:RightShoulder',
        'RightElbow': 'mixamorig:RightForeArm',
        'RightWrist': 'mixamorig:RightHand',
        'LeftUpLeg': 'mixamorig:LeftUpLeg',
        'LeftLeg': 'mixamorig:LeftLeg',
        'RightUpLeg': 'mixamorig:RightUpLeg',
        'RightLeg': 'mixamorig:RightLeg'
    }

    # Clear existing mappings to avoid duplication
    props.mapping_collection.clear()

    added = []
    for mocap_name, pattern in wanted.items():
        # exact match first
        if pattern in pose_names:
            found = pattern
        else:
            # try without prefix
            short = pattern.split(':')[-1]
            found = next((bn for bn in pose_names if short.lower() in bn.lower()), None)

        if found:
            item = props.mapping_collection.add()
            item.mocap_name = mocap_name
            item.blender_name = found
            added.append((mocap_name, found))

    if added:
        print(f"Auto-mapped {len(added)} bones: {added}")
    else:
        print("Auto-map: no compatible mixamorig bones found in armature")

def apply_rotation(pose_bone, rotation_data):
    """Safely applies rotation data (Quaternion W, X, Y, Z) to a pose bone, accounting for calibration."""
    if rotation_data and len(rotation_data) == 4:
        try:
            # 1. Convert Mocap data (assuming W, X, Y, Z order) to Blender Quaternion
            # Note: mathutils.Quaternion expects (w, x, y, z)
            mocap_quat = Quaternion((rotation_data[0], rotation_data[1], rotation_data[2], rotation_data[3]))
            
            # 2. Apply Calibration Offset (pre-multiplication for local offset)
            blender_bone_name = pose_bone.name
            if blender_bone_name in CALIBRATION_OFFSETS:
                offset_quat = CALIBRATION_OFFSETS[blender_bone_name]
                # Pre-multiply the offset (offset @ mocap_rotation)
                # This applies the offset rotation, then the incoming mocap rotation
                final_quat = offset_quat @ mocap_quat
            else:
                final_quat = mocap_quat

            # 3. Apply the final rotation to the pose bone
            pose_bone.rotation_mode = 'QUATERNION'
            pose_bone.rotation_quaternion = final_quat

        except Exception as e:
            # Report error, but allow other bones to proceed
            print(f"Error applying rotation to bone '{pose_bone.name}': {e}")


def map_whole_body(armature_obj, mocap_joints):
    """Applies rotation and location data for full body motion capture."""
    bone_map = get_bone_map_from_properties()
    pose_bones = armature_obj.pose.bones
    
    # 1. Handle Hips/Root Location (if provided by Mocap data)
    hips_mocap_name = "Hips"
    if hips_mocap_name in mocap_joints and hips_mocap_name in bone_map:
        hips_bone = pose_bones.get(bone_map[hips_mocap_name])
        if hips_bone and 'location' in mocap_joints[hips_mocap_name]:
            loc_data = mocap_joints[hips_mocap_name]['location']
            if len(loc_data) == 3:
                # Assuming Mocap system uses X/Y/Z, map to Blender's coordinate system
                # This may require axis swaps depending on the Mocap source
                hips_bone.location = Vector((loc_data[0], loc_data[1], loc_data[2]))

    # 2. Apply Rotations to all mapped bones
    for mocap_name, blender_name in bone_map.items():
        if mocap_name in mocap_joints:
            pose_bone = pose_bones.get(blender_name)
            if pose_bone and 'rotation_wzxy' in mocap_joints[mocap_name]:
                # Assuming rotation_wzxy data is [w, x, y, z] for quaternion
                apply_rotation(pose_bone, mocap_joints[mocap_name]['rotation_wzxy'])


def map_hands_only(armature_obj, mocap_joints):
    """Applies rotation only to hand bones, ignoring the rest of the body."""
    bone_map = get_bone_map_from_properties()
    pose_bones = armature_obj.pose.bones
    
    # Filter by mocap joint name to identify hand-related joints
    HAND_FILTER = ('Hand', 'Finger', 'Index', 'Thumb', 'Middle', 'Ring', 'Pinky')
    
    for mocap_name, blender_name in bone_map.items():
        # Check if the mocap source name matches any of the hand keywords
        if any(f in mocap_name for f in HAND_FILTER):
            if mocap_name in mocap_joints:
                pose_bone = pose_bones.get(blender_name)
                if pose_bone and 'rotation_wzxy' in mocap_joints[mocap_name]:
                    apply_rotation(pose_bone, mocap_joints[mocap_name]['rotation_wzxy'])
                    

def apply_mocap_data(armature_obj, mocap_data_json):
    """
    Main function to parse the incoming Mocap data and apply it to the armature.
    """
    try:
        data = mocap_data_json
        mocap_mode = data.get('mode', 'WHOLE_BODY') # Default mode
        mocap_joints = data.get('joints', {})
        mediapipe_data = data.get('mediapipe', None)

        if not armature_obj or armature_obj.type != 'ARMATURE':
            print("Error: Target object is not a valid Armature.")
            return

        # Ensure we are in POSE mode to manipulate bones
        if bpy.context.object != armature_obj:
            bpy.context.view_layer.objects.active = armature_obj
        # Only switch mode if needed to avoid overhead, though it's generally safe here
        if armature_obj.mode != 'POSE':
            try:
                bpy.ops.object.mode_set(mode='POSE')
            except RuntimeError as e:
                print(f"Error: Could not set Pose Mode on armature. Aborting update. Details: {e}")
                return

        # If mediapipe pose landmarks are available, use them to compute simple limb rotations
        if mediapipe_data:
            try:
                apply_mediapipe_pose(armature_obj, mediapipe_data)
            except Exception as e:
                print(f"Error applying MediaPipe data: {e}")

        # Select the mapping function based on the UI setting
        props = bpy.context.scene.mocap_properties
        if props.mocap_mode == 'WHOLE_BODY':
            map_whole_body(armature_obj, mocap_joints)
        elif props.mocap_mode == 'HANDS_ONLY':
            map_hands_only(armature_obj, mocap_joints)

    except Exception as e:
        print(f"Critical error during Mocap data processing: {e}")
    finally:
        # Force a redraw of the viewport after changes
        if armature_obj and hasattr(armature_obj, 'mode') and armature_obj.mode == 'POSE':
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass

def calibrate_pose(armature_obj):
    """
    Captures the current pose of the armature to establish calibration offsets.
    The goal is to set the current pose as the 'zero' pose for incoming mocap data.
    """
    global CALIBRATION_OFFSETS
    CALIBRATION_OFFSETS.clear()
    
    if not armature_obj or armature_obj.type != 'ARMATURE':
        print("Calibration Error: Target object is not an Armature.")
        return False

    # Retrieve the live bone map to know which bones to calibrate
    bone_map = get_bone_map_from_properties()
    
    # Ensure we are in POSE mode for correct rotation data access
    if bpy.context.object != armature_obj:
        bpy.context.view_layer.objects.active = armature_obj
    if armature_obj.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')

    pose_bones = armature_obj.pose.bones
    
    bones_calibrated = 0
    # Iterate over the values (Blender Bone Names) in the bone_map
    for blender_name in bone_map.values():
        pose_bone = pose_bones.get(blender_name)
        if pose_bone:
            # Store the current rotation as the inverse offset. 
            # When new data comes in (Offset @ NewData), the original pose is effectively subtracted.
            CALIBRATION_OFFSETS[blender_name] = pose_bone.rotation_quaternion.inverted()
            bones_calibrated += 1

    print(f"Calibration successful: Stored offsets for {bones_calibrated} bones.")
    return True


def apply_mediapipe_pose(armature_obj, mediapipe_data):
    """Very simple mapper: uses MediaPipe pose landmarks to orient upper arm and forearm.

    mediapipe_data['pose'] is a list of [x,y,z] landmarks in normalized image coords.
    We'll use landmarks indices: 11 (left_shoulder), 12 (right_shoulder), 13/14 elbows, 15/16 wrists.
    This is an approximation and assumes a frontal camera and a T-pose neutral mapping.
    """
    pose_list = mediapipe_data.get('pose') if isinstance(mediapipe_data, dict) else None
    if not pose_list or len(pose_list) < 16:
        return

    bone_map = get_bone_map_from_properties()
    pose_bones = armature_obj.pose.bones

    # Helper: resolve mocap joint name to a blender bone name using mapping or common fallbacks
    def resolve_bone_name(mocap_name):
        # Direct mapping first
        if mocap_name in bone_map:
            return bone_map[mocap_name]
        # Common alternative names to try
        candidates = []
        if mocap_name.lower().startswith('left'):
            side = '.L'
            side_names = ['.L', '_L', '_left', ' L']
        elif mocap_name.lower().startswith('right'):
            side = '.R'
            side_names = ['.R', '_R', '_right', ' R']
        else:
            side = ''
            side_names = ['','.L','.R','_L','_R']

        base = mocap_name
        # remove side prefix if present
        for prefix in ('left','right','Left','Right'):
            if base.startswith(prefix):
                base = base[len(prefix):]
                break

        # Normalize base
        base = base.strip().replace(' ','')

        # Try a few common Blender bone name patterns
        for s in side_names:
            candidates.append(base + s)
            candidates.append('Upper' + base + s)
            candidates.append('upper_' + base.lower() + s)
            candidates.append(base.capitalize() + s)

        # Search for first candidate present in pose bones
        for c in candidates:
            if c in pose_bones:
                return c
        # fallback: search any bone containing the base name
        for b in pose_bones:
            if base.lower() in b.name.lower():
                return b.name
        return None

    # Helper to convert normalized image coords to a pseudo-3D vector in Blender space
    def lm_to_vec(lm):
        # Mediapipe gives x,y in [0,1], z roughly relative depth; convert to Blender-ish coords
        # Flip Y because image coords start top-left
        return Vector(( (lm[0] - 0.5) * 2.0, (0.5 - lm[1]) * 2.0, -lm[2] ))

    # Simple temporal smoothing for landmark positions to reduce jitter
    _LAST_LM = {}
    def smooth_lm(idx, vec, alpha=0.6):
        # alpha = new sample weight
        prev = _LAST_LM.get(idx)
        if prev is None:
            _LAST_LM[idx] = vec.copy()
            return vec
        res = prev * (1.0 - alpha) + vec * alpha
        _LAST_LM[idx] = res
        return res

    # Landmark indices (MediaPipe Pose):
    # 11 = left_shoulder, 12 = right_shoulder,
    # 13 = left_elbow, 14 = right_elbow,
    # 15 = left_wrist, 16 = right_wrist,
    # 23 = left_hip, 24 = right_hip, 25 = left_knee, 26 = right_knee, 27 = left_ankle, 28 = right_ankle
    try:
        ls = smooth_lm(11, lm_to_vec(pose_list[11]))
        rs = smooth_lm(12, lm_to_vec(pose_list[12]))
        le = smooth_lm(13, lm_to_vec(pose_list[13]))
        re = smooth_lm(14, lm_to_vec(pose_list[14]))
        lw = smooth_lm(15, lm_to_vec(pose_list[15]))
        rw = smooth_lm(16, lm_to_vec(pose_list[16]))
    except Exception:
        return

    # Compute vectors and set bone orientations for mapped bones if present
    def set_bone_direction(source_vec, target_vec, blender_bone_name):
        pose_bone = pose_bones.get(blender_bone_name)
        if not pose_bone:
            # print missing mapping for easier debugging
            # (don't spam if many are missing)
            #print(f"[MOCAP] Missing pose bone for mapping: {blender_bone_name}")
            return
        # direction from source to target
        try:
            dir_vec = (target_vec - source_vec)
            if dir_vec.length == 0:
                return
            dir_vec = dir_vec.normalized()

            # Create a quaternion that points bone's local Y axis to dir_vec (approximation)
            up = Vector((0.0, 1.0, 0.0))
            axis = up.cross(dir_vec)
            if axis.length == 0:
                quat = Quaternion()
            else:
                angle = up.angle(dir_vec)
                quat = Quaternion(axis.normalized(), angle)

            # Apply calibration offset if available
            bname = pose_bone.name
            if bname in CALIBRATION_OFFSETS:
                offset_q = CALIBRATION_OFFSETS[bname]
                final_q = offset_q @ quat
            else:
                final_q = quat

            pose_bone.rotation_mode = 'QUATERNION'
            pose_bone.rotation_quaternion = final_q
            print(f"[MOCAP] Mediapipe -> set {bname}")
        except Exception as e:
            print(f"Error setting bone {blender_bone_name} direction: {e}")

    def two_bone_ik(root_vec, mid_vec, tip_vec, upper_name, lower_name):
        """Simple two-bone IK solver: positions are in the same pseudo-world space as lm_to_vec.
        root_vec = shoulder position, tip_vec = wrist position. mid_vec is optional initial elbow.
        """
        upper = pose_bones.get(upper_name)
        lower = pose_bones.get(lower_name)
        if not upper or not lower:
            return

        # Get bone lengths from the armature's bone data (in armature local space units)
        try:
            L1 = upper.bone.length
            L2 = lower.bone.length
        except Exception:
            # fallback to measured distance between head/tail
            L1 = (upper.tail - upper.head).length
            L2 = (lower.tail - lower.head).length

        target = tip_vec
        root = root_vec
        d = (target - root).length
        # Clamp to reachable range
        eps = 1e-6
        if d < eps:
            return
        maxd = max(L1 + L2 - 1e-3, eps)
        d_clamped = min(max(d, abs(L1 - L2) + 1e-3), L1 + L2 - 1e-3)

        # Direction from root to target
        dir_rt = (target - root).normalized()

        # Distance along dir to the joint (law of cosines)
        # a = (L1^2 - L2^2 + d^2) / (2d)
        a = (L1 * L1 - L2 * L2 + d_clamped * d_clamped) / (2.0 * d_clamped)
        joint_pos = root + dir_rt * a

        # Apply directions: upper from root->joint, lower from joint->target
        set_bone_direction(root, joint_pos, upper_name)
        set_bone_direction(joint_pos, target, lower_name)
        print(f"[MOCAP] IK applied {upper_name} -> {lower_name}")

    # Map a larger set of limb segments using landmark pairs
    segments = [
        ('LeftShoulder','LeftElbow', ls, le),
        ('LeftElbow','LeftWrist', le, lw),
        ('RightShoulder','RightElbow', rs, re),
        ('RightElbow','RightWrist', re, rw),
        # legs: hips -> knee, knee -> ankle
        ('Hips','LeftUpLeg', (ls+le)/2.0, Vector(((pose_list[23][0]-0.5)*2.0, (0.5-pose_list[23][1])*2.0, -pose_list[23][2])) ),
        ('LeftUpLeg','LeftLeg', Vector(((pose_list[23][0]-0.5)*2.0, (0.5-pose_list[23][1])*2.0, -pose_list[23][2])), Vector(((pose_list[25][0]-0.5)*2.0, (0.5-pose_list[25][1])*2.0, -pose_list[25][2]))),
        ('RightUpLeg','RightLeg', Vector(((pose_list[24][0]-0.5)*2.0, (0.5-pose_list[24][1])*2.0, -pose_list[24][2])), Vector(((pose_list[26][0]-0.5)*2.0, (0.5-pose_list[26][1])*2.0, -pose_list[26][2]))),
    ]

    # Apply for arms/upper body first
    for mocap_a, mocap_b, a_vec, b_vec in segments:
        a_name = resolve_bone_name(mocap_a)
        b_name = resolve_bone_name(mocap_b)
        # prefer applying rotation to the proximal bone (a_name)
        if a_name:
            set_bone_direction(a_vec, b_vec, a_name)
        elif b_name:
            # fallback: set distal bone
            set_bone_direction(a_vec, b_vec, b_name)

    # Try to set hips/spine/neck/head using simple landmark positions if available
    try:
        hip_l = Vector(((pose_list[23][0]-0.5)*2.0, (0.5-pose_list[23][1])*2.0, -pose_list[23][2]))
        hip_r = Vector(((pose_list[24][0]-0.5)*2.0, (0.5-pose_list[24][1])*2.0, -pose_list[24][2]))
        hips_mid = (hip_l + hip_r) / 2.0
        spine = Vector(((pose_list[11][0]-0.5)*2.0, (0.5-pose_list[11][1])*2.0, -pose_list[11][2]))
        neck_mid = (Vector(((pose_list[11][0]-0.5)*2.0, (0.5-pose_list[11][1])*2.0, -pose_list[11][2])) + Vector(((pose_list[12][0]-0.5)*2.0, (0.5-pose_list[12][1])*2.0, -pose_list[12][2]))) / 2.0

        # Hips bone
        hip_bname = resolve_bone_name('Hips')
        if hip_bname:
            set_bone_direction(hips_mid, spine, hip_bname)

        # Spine bone
        spine_bname = resolve_bone_name('Spine')
        if spine_bname:
            set_bone_direction(hips_mid, neck_mid, spine_bname)

        # Neck / Head
        neck_bname = resolve_bone_name('Neck')
        head_bname = resolve_bone_name('Head')
        nose = Vector(((pose_list[0][0]-0.5)*2.0, (0.5-pose_list[0][1])*2.0, -pose_list[0][2]))
        if neck_bname:
            set_bone_direction(neck_mid, nose, neck_bname)
        if head_bname:
            set_bone_direction(neck_mid, nose, head_bname)
    except Exception:
        pass