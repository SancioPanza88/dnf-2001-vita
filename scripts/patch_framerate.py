"""
Patch sdlayer.cpp for PS Vita DNF 2001 port - stable 60fps frame pacing.

FIXES (all verified against upstream EDuke32-Vita source):
  1. vblank_wait(0) -> (1): upstream disables vblank wait, so the engine runs
     UNCAPPED (tearing + pacing jitter + CPU pegged at 100% presenting as fast
     as possible). Enabling vblank locks presentation to the 60Hz display.
  2. Best-effort 500MHz ARM with 444 fallback: upstream pins 444. 500 works on
     many units (oclock-style); scePowerSetArmClockFrequency returns != 0 when
     rejected, so the fallback keeps stock-max behavior - always safe.

Both patches are startup-time only (zero per-frame cost).
"""
import sys


def patch_framerate(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    if 'DNF_VITA_60FPS' in content:
        print("  DNF_VITA_60FPS already set - nothing to do.")
        return

    changes = 0

    # --- 1. vblank wait ON (upstream: vita2d_set_vblank_wait(0);) ---
    vblank_patterns = [
        ('    vita2d_set_vblank_wait(0); // DNF_VITA_60FPS: vsync ON, lock 60Hz display\n',
         None),  # already-patched shape guard (handled by marker check above)
        ('    vita2d_set_vblank_wait(0);',
         '    vita2d_set_vblank_wait(1); // DNF_VITA_60FPS: vsync ON, lock 60Hz display'),
        ('\tvita2d_set_vblank_wait(0);',
         '\tvita2d_set_vblank_wait(1); // DNF_VITA_60FPS: vsync ON, lock 60Hz display'),
        ('vita2d_set_vblank_wait(0);',
         'vita2d_set_vblank_wait(1); // DNF_VITA_60FPS: vsync ON, lock 60Hz display'),
    ]
    ok = False
    for old, new in vblank_patterns:
        if new is None:
            continue
        if old in content:
            content = content.replace(old, new, 1)
            ok = True
            print("    [OK] vblank wait ON (vsync, 60Hz pacing)")
            changes += 1
            break
    if not ok:
        print("    [FAIL] vita2d_set_vblank_wait(0) pattern not found!")
        sys.exit(1)

    # --- 2. upstream clock block -> try 500MHz, fallback 444 ---
    clock_old = (
        '    scePowerSetArmClockFrequency(444);\n'
        '    scePowerSetBusClockFrequency(222);\n'
        '    scePowerSetGpuClockFrequency(222);\n'
        '    scePowerSetGpuXbarClockFrequency(166);\n'
    )
    clock_new = (
        '    // DNF_VITA_60FPS: best-effort 500MHz ARM, fallback 444 (stock max)\n'
        '    if (scePowerSetArmClockFrequency(500) != 0) scePowerSetArmClockFrequency(444);\n'
        '    scePowerSetBusClockFrequency(222);\n'
        '    scePowerSetGpuClockFrequency(222);\n'
        '    scePowerSetGpuXbarClockFrequency(166);\n'
    )
    if clock_old in content:
        content = content.replace(clock_old, clock_new, 1)
        print("    [OK] clocks: try 500MHz ARM, fallback 444")
        changes += 1
    else:
        # Clock block may already be handled by patch_sdlayer.py standalone
        # replacement (which also tries 500 first) - non-fatal.
        print("    [SKIP] upstream clock block not found (standalone patch covers it)")

    # Marker comment so re-runs are idempotent
    content += '\n// DNF_VITA_60FPS applied\n'

    with open(filepath, 'w') as f:
        f.write(content)

    print(f"\n  Patched: {changes} changes applied (vblank vsync + clocks)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_sdlayer.cpp>")
        sys.exit(1)

    patch_framerate(sys.argv[1])
