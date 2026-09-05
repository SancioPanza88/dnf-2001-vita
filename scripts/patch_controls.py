"""
Patch _functio.h and config.cpp for FPS-style joystick controls on PS Vita.

DESIRED FPS mapping:
  Left Stick  = Movement  → Axis 0 (X) = Strafing, Axis 1 (Y) = Moving
  Right Stick = Camera    → Axis 2 (X) = Turning,  Axis 3 (Y) = Looking
  L2/R2 analog = Axes 4/5 → unmapped (SDL Vita exposes triggers as axes; must not reuse analog_turning etc.)

SDL2 Vita button order (SDL_sysjoystick.c ext_button_map): 0–3 face (△○×□), 4–5 L1/R1,
  6–9 D-Pad Down/Left/Up/Right (not “Up first”), 10–11 Select/Start, 12–15 L2/R2/L3/R3.

APPROACH:
  1. Patch _functio.h:  Add a #ifdef __PSP2__ section to joystickanalogdefaults[]
     so the compile-time defaults are correct (like the GEKKO/Wii preset).
  2. Patch config.cpp:  Force the correct axis mapping in CONFIG_SetDefaults()
     with a #ifdef __PSP2__ block, so it works even if a saved config overrides it.

This replaces the old broken approach of swapping joyaxis[] at SDL event level.
"""
import sys
import re


def patch_functio_h(filepath):
    """Patch _functio.h to add PSP2 joystick analog defaults (FPS layout)."""
    with open(filepath, 'r') as f:
        content = f.read()

    if 'DNF_VITA_CONTROLS' in content:
        print(f"  {filepath} already patched for controls, skipping.")
        return

    changes = 0

    # Find the non-GEKKO joystickanalogdefaults and wrap it with PSP2 override.
    # The structure is:
    #   #else
    #   static const char * joystickanalogdefaults[MAXJOYAXES] =
    #   {
    #       "analog_turning",
    #       "analog_moving",
    #       "analog_strafing",
    #   };
    #
    # We want to add a #elif __PSP2__ before the #else with the correct FPS layout.

    # Strategy: Find the GEKKO #if block end and insert PSP2 before #else
    # The pattern is:  };  (end of GEKKO arrays) then #else
    # Let's find the second (non-GEKKO) joystickanalogdefaults

    # Find all occurrences of joystickanalogdefaults
    positions = [m.start() for m in re.finditer(r'static const char \* joystickanalogdefaults', content)]

    if len(positions) >= 2:
        # The second occurrence is the non-GEKKO (generic) one
        # We need to find the #else that precedes it
        second_pos = positions[1]
        # Search backwards from second_pos for #else
        else_search = content[:second_pos]
        else_idx = else_search.rfind('#else')

        if else_idx != -1:
            # Insert #elif __PSP2__ block before #else
            psp2_block = (
                '#elif defined(__PSP2__)\n'
                '// DNF_VITA_CONTROLS: FPS layout - LStick=Move/Strafe, RStick=Turn/Look\n'
                '// Button indices = SDL2 Vita ext_button_map (not hat bits)\n'
                'static const char * joystickdefaults[MAXJOYBUTTONSANDHATS] =\n'
                '   {\n'
                '   "Previous_Weapon", // 0 Triangle\n'
                '   "Quick_Kick",      // 1 Circle\n'
                '   "Jump",            // 2 Cross\n'
                '   "Crouch",          // 3 Square\n'
                '   "Open",            // 4 L1\n'
                '   "Fire",            // 5 R1\n'
                '   "Inventory",       // 6 D-Pad Down\n'
                '   "Last_Used_Weapon",// 7 D-Pad Left\n'
                '   "Next_Weapon",     // 8 D-Pad Up\n'
                '   "Run",             // 9 D-Pad Right\n'
                '   "Third_Person_View", // 10 Select\n'
                '   "Map",             // 11 Start\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   "",\n'
                '   };\n'
                '\n'
                'static const char * joystickclickeddefaults[MAXJOYBUTTONSANDHATS] =\n'
                '   {\n'
                '   };\n'
                '\n'
                'static const char * joystickanalogdefaults[MAXJOYAXES] =\n'
                '   {\n'
                '   "analog_strafing",          // Axis 0: LStick X = strafe\n'
                '   "analog_moving",            // Axis 1: LStick Y = move fwd/back\n'
                '   "analog_turning",           // Axis 2: RStick X = turn/yaw\n'
                '   "analog_lookingupanddown",  // Axis 3: RStick Y = look up/down\n'
                '   };\n'
                '\n'
                'static const char * joystickdigitaldefaults[MAXJOYDIGITAL] =\n'
                '   {\n'
                '   };\n'
            )

            content = content[:else_idx] + psp2_block + content[else_idx:]
            changes += 1
            print("    [OK] PSP2 joystickanalogdefaults inserted in _functio.h")

    elif len(positions) == 1:
        # Only one definition (no GEKKO block). Wrap it.
        pos = positions[0]
        # Find the opening of the array
        brace = content.find('{', pos)
        # Find the closing };
        close = content.find('};', brace)
        if close != -1:
            close += 2  # include the ;
            # Extract existing block and wrap with #ifndef __PSP2__
            existing = content[pos:close]
            replacement = (
                '#ifdef __PSP2__\n'
                '// DNF_VITA_CONTROLS: FPS layout - LStick=Move/Strafe, RStick=Turn/Look\n'
                'static const char * joystickanalogdefaults[MAXJOYAXES] =\n'
                '   {\n'
                '   "analog_strafing",          // Axis 0: LStick X = strafe\n'
                '   "analog_moving",            // Axis 1: LStick Y = move fwd/back\n'
                '   "analog_turning",           // Axis 2: RStick X = turn/yaw\n'
                '   "analog_lookingupanddown",  // Axis 3: RStick Y = look up/down\n'
                '   };\n'
                '#else\n'
                + existing + '\n'
                '#endif\n'
            )
            content = content[:pos] + replacement + content[close:]
            changes += 1
            print("    [OK] PSP2 joystickanalogdefaults wrapped with #ifdef")

    if changes == 0:
        print(f"  WARNING: Could not find joystickanalogdefaults in {filepath}")
    else:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  _functio.h patched: {changes} changes")


def patch_config_cpp(filepath):
    """Patch config.cpp to force FPS axis mapping on PSP2 in CONFIG_SetDefaults."""
    with open(filepath, 'r') as f:
        content = f.read()

    if 'DNF_VITA_FORCE_CONTROLS' in content:
        print(f"  {filepath} already patched for controls, skipping.")
        return

    changes = 0

    # Find CONFIG_SetDefaults function and the joystick axis setup loop.
    # We want to insert a PSP2 override AFTER the default axis setup loop ends.
    # The loop is:
    #   for (i=0; i<MAXJOYAXES; i++) { ... }
    # followed by:
    #   VM_OnEvent(EVENT_SETDEFAULTS, ...)
    #
    # We insert our override just before VM_OnEvent.

    # Find VM_OnEvent(EVENT_SETDEFAULTS
    vm_event = 'VM_OnEvent(EVENT_SETDEFAULTS'
    vm_idx = content.find(vm_event)

    if vm_idx != -1:
        # Insert PSP2 override block before VM_OnEvent
        psp2_block = (
            '#ifdef __PSP2__\n'
            '    // DNF_VITA_FORCE_CONTROLS: Override axis mapping for FPS layout\n'
            '    // LStick = Move/Strafe, RStick = Turn/Look\n'
            '    ud.config.JoystickAnalogueAxes[0] = analog_strafing;          // LStick X\n'
            '    ud.config.JoystickAnalogueAxes[1] = analog_moving;            // LStick Y\n'
            '    ud.config.JoystickAnalogueAxes[2] = analog_turning;           // RStick X\n'
            '    ud.config.JoystickAnalogueAxes[3] = analog_lookingupanddown;  // RStick Y\n'
            '    CONTROL_MapAnalogAxis(0, analog_strafing, controldevice_joystick);\n'
            '    CONTROL_MapAnalogAxis(1, analog_moving, controldevice_joystick);\n'
            '    CONTROL_MapAnalogAxis(2, analog_turning, controldevice_joystick);\n'
            '    CONTROL_MapAnalogAxis(3, analog_lookingupanddown, controldevice_joystick);\n'
            '    // Sensitivity: lower for look axes to prevent twitchy aiming\n'
            '    ud.config.JoystickAnalogueScale[0] = DEFAULTJOYSTICKANALOGUESCALE;  // strafe\n'
            '    ud.config.JoystickAnalogueScale[1] = DEFAULTJOYSTICKANALOGUESCALE;  // move\n'
            '    ud.config.JoystickAnalogueScale[2] = DEFAULTJOYSTICKANALOGUESCALE;  // turn\n'
            '    ud.config.JoystickAnalogueScale[3] = DEFAULTJOYSTICKANALOGUESCALE;  // look\n'
            '    CONTROL_SetAnalogAxisScale(0, ud.config.JoystickAnalogueScale[0], controldevice_joystick);\n'
            '    CONTROL_SetAnalogAxisScale(1, ud.config.JoystickAnalogueScale[1], controldevice_joystick);\n'
            '    CONTROL_SetAnalogAxisScale(2, ud.config.JoystickAnalogueScale[2], controldevice_joystick);\n'
            '    CONTROL_SetAnalogAxisScale(3, ud.config.JoystickAnalogueScale[3], controldevice_joystick);\n'
            '    // Clear digital axis functions (pure analog sticks + L2/R2 axes; no digital override)\n'
            '    for (i = 0; i < 6; i++) {\n'
            '        ud.config.JoystickDigitalFunctions[i][0] = -1;\n'
            '        ud.config.JoystickDigitalFunctions[i][1] = -1;\n'
            '        CONTROL_MapDigitalAxis(i, -1, 0, controldevice_joystick);\n'
            '        CONTROL_MapDigitalAxis(i, -1, 1, controldevice_joystick);\n'
            '    }\n'
            '    // SDL Vita reports L2/R2 as analog axes 4–5; leave unmapped (avoid stray turning/moving)\n'
            '    ud.config.JoystickAnalogueAxes[4] = -1;\n'
            '    ud.config.JoystickAnalogueAxes[5] = -1;\n'
            '    CONTROL_MapAnalogAxis(4, -1, controldevice_joystick);\n'
            '    CONTROL_MapAnalogAxis(5, -1, controldevice_joystick);\n'
            '    ud.config.UseJoystick = 1;\n'
            '    g_myAimMode = g_player[0].ps->aim_mode = 1;  // mouse-style aiming\n'
            '#endif\n\n'
            '    '
        )

        content = content[:vm_idx] + psp2_block + content[vm_idx:]
        changes += 1
        print("    [OK] PSP2 axis mapping override inserted in CONFIG_SetDefaults")
    else:
        # Fallback: try to find the end of the joystick axis loop
        loop_end_patterns = [
            'CONTROL_MapAnalogAxis(i, ud.config.JoystickAnalogueAxes[i], controldevice_joystick);',
        ]
        for pat in loop_end_patterns:
            idx = content.find(pat)
            if idx != -1:
                # Find the closing } of the for loop
                brace = content.find('}', idx)
                if brace != -1:
                    insert_pos = brace + 1
                    psp2_block = (
                        '\n#ifdef __PSP2__\n'
                        '    // DNF_VITA_FORCE_CONTROLS: Override for FPS layout\n'
                        '    CONTROL_MapAnalogAxis(0, analog_strafing, controldevice_joystick);\n'
                        '    CONTROL_MapAnalogAxis(1, analog_moving, controldevice_joystick);\n'
                        '    CONTROL_MapAnalogAxis(2, analog_turning, controldevice_joystick);\n'
                        '    CONTROL_MapAnalogAxis(3, analog_lookingupanddown, controldevice_joystick);\n'
                        '#endif\n'
                    )
                    content = content[:insert_pos] + psp2_block + content[insert_pos:]
                    changes += 1
                    print("    [OK] PSP2 axis override inserted after joystick setup loop")
                    break

    if changes == 0:
        print(f"  WARNING: Could not find CONFIG_SetDefaults joystick setup in {filepath}")
    else:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  config.cpp patched: {changes} changes")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <path_to/_functio.h> <path_to/config.cpp>")
        sys.exit(1)
    patch_functio_h(sys.argv[1])
    patch_config_cpp(sys.argv[2])
