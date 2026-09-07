"""
Patch sdlayer.cpp for PS Vita DNF 2001 port - Performance optimizations.

STRATEGY:
  - Resize fb_texture and gpu_texture to 320x200 (Duke3D native resolution)
  - Engine renders at 320x200 directly into fb_texture
  - videoShowFrame uses vita2d_draw_texture_scale(3.0, 2.72) to fill 960x544
  - LINEAR filter already set on gpu_texture for smooth upscale

Goal is smoother, more consistent performance (fewer pixels for the software renderer),
not a fixed FPS target; no artificial frame cap.

WHY 320x200:
  - Duke3D native resolution, fewer pixels than 480x272 / 640x400
  - 960/320 = 3.0x, 544/200 = 2.72x clean GPU upscale

INDENTATION: Upstream EDuke32-Vita uses spaces in videoBeginDrawing/videoShowFrame and
psp2_main texture creation (not tabs / not 4 spaces). Older patch strings failed silently
or skipped blocks, leaving the engine at 480x272 — double the pixel work vs 320x200.
"""
import sys


def _try_replace_first(content, candidates, label):
    for old, new in candidates:
        if old in content:
            content = content.replace(old, new, 1)
            print(f"    [OK] {label}")
            return content, True
    print(f"    [FAIL] {label}: no matching pattern")
    return content, False


def patch_performance(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    changes = 0
    changes_main = 0
    main_needed = "DNF_PERF_PATCH_APPLIED" not in content

    if not main_needed:
        print("  DNF_PERF_PATCH_APPLIED already set - nothing to do.")
        return

    # =========================================================================
    # PATCH 1: Guard marker
    # =========================================================================
    old = 'vita2d_texture *fb_texture, *gpu_texture;'
    new = 'vita2d_texture *fb_texture, *gpu_texture; // DNF_PERF_PATCH_APPLIED'
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        changes_main += 1
        print("    [OK] Guard marker added")
    else:
        print("    [FAIL] vita2d globals line not found!")

    # =========================================================================
    # PATCH 2+3: Resize gpu_texture / fb_texture from 960x544 to 320x200
    # =========================================================================
    gpu_patterns = [
        (
            ' gpu_texture = vita2d_create_empty_texture_format(960, 544, SCE_GXM_TEXTURE_FORMAT_P8_1BGR);\n',
            ' gpu_texture = vita2d_create_empty_texture_format(320, 200, SCE_GXM_TEXTURE_FORMAT_P8_1BGR); // DNF: 320x200\n',
        ),
        (
            '    gpu_texture = vita2d_create_empty_texture_format(960, 544, SCE_GXM_TEXTURE_FORMAT_P8_1BGR);\n',
            '    gpu_texture = vita2d_create_empty_texture_format(320, 200, SCE_GXM_TEXTURE_FORMAT_P8_1BGR); // DNF: 320x200\n',
        ),
    ]
    content, ok = _try_replace_first(content, gpu_patterns, "gpu_texture resized to 320x200")
    if ok:
        changes += 1
        changes_main += 1

    fb_patterns = [
        (
            ' fb_texture = vita2d_create_empty_texture_format(960, 544, SCE_GXM_TEXTURE_FORMAT_P8_1BGR);\n',
            ' fb_texture = vita2d_create_empty_texture_format(320, 200, SCE_GXM_TEXTURE_FORMAT_P8_1BGR); // DNF: 320x200\n',
        ),
        (
            '    fb_texture = vita2d_create_empty_texture_format(960, 544, SCE_GXM_TEXTURE_FORMAT_P8_1BGR);\n',
            '    fb_texture = vita2d_create_empty_texture_format(320, 200, SCE_GXM_TEXTURE_FORMAT_P8_1BGR); // DNF: 320x200\n',
        ),
    ]
    content, ok = _try_replace_first(content, fb_patterns, "fb_texture resized to 320x200")
    if ok:
        changes += 1
        changes_main += 1

    # =========================================================================
    # PATCH 4: Replace videoShowFrame draw with scaled upsample
    # =========================================================================
    show_old_new = [
        (
            (
                ' memcpy(vita2d_texture_get_datap(gpu_texture),vita2d_texture_get_datap(fb_texture),'
                'vita2d_texture_get_stride(gpu_texture)*vita2d_texture_get_height(gpu_texture));\n'
                ' vita2d_start_drawing();\n'
                ' vita2d_draw_texture(gpu_texture, 0, 0);\n'
                ' vita2d_end_drawing();\n'
                ' vita2d_wait_rendering_done();\n'
                ' vita2d_swap_buffers();'
            ),
            (
                ' memcpy(vita2d_texture_get_datap(gpu_texture),vita2d_texture_get_datap(fb_texture),'
                'vita2d_texture_get_stride(gpu_texture)*vita2d_texture_get_height(gpu_texture));\n'
                ' vita2d_start_drawing();\n'
                ' vita2d_draw_texture_scale(gpu_texture, 0, 0, 3.0f, 2.72f); // DNF: 320x200 -> 960x544\n'
                ' vita2d_end_drawing();\n'
                ' vita2d_wait_rendering_done();\n'
                ' vita2d_swap_buffers();'
            ),
        ),
        (
            (
                '    memcpy(vita2d_texture_get_datap(gpu_texture),'
                'vita2d_texture_get_datap(fb_texture),'
                'vita2d_texture_get_stride(gpu_texture)*vita2d_texture_get_height(gpu_texture));\n'
                '    vita2d_start_drawing();\n'
                '    vita2d_draw_texture(gpu_texture, 0, 0);\n'
                '    vita2d_end_drawing();\n'
                '    vita2d_wait_rendering_done();\n'
                '    vita2d_swap_buffers();'
            ),
            (
                '    memcpy(vita2d_texture_get_datap(gpu_texture),'
                'vita2d_texture_get_datap(fb_texture),'
                'vita2d_texture_get_stride(gpu_texture)*vita2d_texture_get_height(gpu_texture));\n'
                '    vita2d_start_drawing();\n'
                '    vita2d_draw_texture_scale(gpu_texture, 0, 0, 3.0f, 2.72f); // DNF: 320x200 -> 960x544\n'
                '    vita2d_end_drawing();\n'
                '    vita2d_wait_rendering_done();\n'
                '    vita2d_swap_buffers();'
            ),
        ),
    ]
    ok_show = False
    for old, new in show_old_new:
        if old in content:
            content = content.replace(old, new, 1)
            ok_show = True
            print("    [OK] videoShowFrame: scaled 320x200 -> 960x544")
            changes += 1
            changes_main += 1
            break
    if not ok_show:
        print("    [SKIP] videoShowFrame pattern not found (non-fatal)")

    # =========================================================================
    # PATCH 5: Force internal res every frame + trigger ylookup refresh
    # =========================================================================
    # Forcing modechange=1 every frame re-ran calc_ylookup() each videoBeginDrawing() and
    # crushed FPS. Only request modechange when we actually correct a drift away from 320x200.
    # Classic 8-bit only (bpp == 8): the experimental vitaGL renderer (32-bit)
    # manages its own viewport - never force 320x200 under it.
    guard = (
        '\n#ifdef __PSP2__\n'
        ' // DNF_VITA_RESOLUTION_GUARD (see patch_performance.py)\n'
        ' if (bpp == 8) {\n'
        ' const int32_t dnf_w = 320, dnf_h = 200;\n'
        ' const int need_lookup = (xres != dnf_w || yres != dnf_h);\n'
        ' xres = dnf_w; yres = dnf_h; xdim = dnf_w; ydim = dnf_h;\n'
        ' if (need_lookup) modechange = 1;\n'
        ' }\n'
        '#endif'
    )

    frameplace_patterns = [
        ' frameplace = (intptr_t)framebuffer;',
        '    frameplace = (intptr_t)framebuffer;',
        '\tframeplace = (intptr_t)framebuffer;',
    ]

    ok_guard = False
    for fp_line in frameplace_patterns:
        if fp_line in content:
            content = content.replace(fp_line, fp_line + guard, 1)
            ok_guard = True
            print("    [OK] videoBeginDrawing: resolution guard (320x200 + modechange)")
            changes += 1
            changes_main += 1
            break
    if not ok_guard:
        print("    [FAIL] videoBeginDrawing: frameplace line not found")

    if changes_main < 3:
        print(f"  ERROR: Only {changes_main} main perf changes applied (need >= 3)!")
        sys.exit(1)

    with open(filepath, 'w') as f:
        f.write(content)

    print(f"\n  Patched: {changes} changes applied")
    print(f"    fb/gpu textures: 320x200")
    print(f"    Engine renders at 320x200, scales 3.0x/2.72x to fill 960x544")
    print("    No fixed FPS cap; stability from lower internal resolution + build opts")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_sdlayer.cpp>")
        sys.exit(1)

    patch_performance(sys.argv[1])
