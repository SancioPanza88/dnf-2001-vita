"""
Patch sdlayer.cpp AND sdlayer12.cpp to bypass videoSetMode on PSP2.

ARCHITECTURE:
  EDuke32-Vita uses SDL1 on Vita. sdlayer.cpp includes sdlayer12.cpp at the bottom
  via #include "sdlayer12.cpp" (only for SDL_MAJOR_VERSION == 1).
  sdlayer12.cpp defines its OWN videoSetMode() which OVERRIDES the one in sdlayer.cpp.
  So we must patch BOTH files.

ROOT CAUSE OF "Unable to set video mode!" LOOP:
  videoSetMode in sdlayer12.cpp calls SDL_SetVideoMode which always fails on Vita's
  SDL1 vita driver. The game loops through 5 fallback resolutions and crashes.

SOLUTION:
  Insert a #ifdef __PSP2__ early-return as the VERY FIRST statement in videoSetMode()
  in both sdlayer.cpp and sdlayer12.cpp.
  Sets all engine globals (xres/yres/xdim/ydim/bpp/etc.) directly, returns 0.
"""
import sys
import re


PSP2_BLOCK = (
    '#ifdef __PSP2__\n'
    '    // DNF_VITA_SKIP_SDL_SETVIDEOMODE: bypass ALL SDL/OpenGL video init on Vita.\n'
    '    // SDL_SetVideoMode is not supported by the Vita SDL1 driver and always fails.\n'
    '    // Render at 320x200 (Duke3D native), upscale to 960x544 in videoShowFrame.\n'
    '    initprintf("DNF: videoSetMode PSP2 bypass %dx%d bpp=%d\\n", x, y, c);\n'
    '    xres  = 320;\n'
    '    yres  = 200;\n'
    '    xdim  = 320;\n'
    '    ydim  = 200;\n'
    '    bpp   = c;\n'
    '    fullscreen = fs;\n'
    '    bytesperline = 320;\n'
    '    numpages   = 1;\n'
    '    lockcount  = 0;\n'
    '    modechange = 1;\n'
    '    videomodereset = 0;\n'
    '    return 0;\n'
    '#endif\n'
)


def patch_file(filepath, guard_string):
    with open(filepath, 'r') as f:
        content = f.read()

    if guard_string in content:
        print(f"  {filepath} videoSetMode already patched, skipping.")
        return

    # sdlayer.cpp: exact known signature (CRLF-safe)
    # sdlayer12.cpp: same function but different surrounding code
    # Both use:  int32_t videoSetMode(int32_t x, int32_t y, int32_t c, int32_t fs)
    # Followed by opening brace and first local variable declaration.

    # Strategy 1: exact match (handles both LF and CRLF)
    patterns = [
        ('int32_t videoSetMode(int32_t x, int32_t y, int32_t c, int32_t fs)\n'
         '{\n'
         '    int32_t regrab = 0, ret;\n'),
        ('int32_t videoSetMode(int32_t x, int32_t y, int32_t c, int32_t fs)\r\n'
         '{\r\n'
         '    int32_t regrab = 0, ret;\r\n'),
        # sdlayer12 may have slightly different first local var
        ('int32_t videoSetMode(int32_t x, int32_t y, int32_t c, int32_t fs)\n'
         '{\n'),
        ('int32_t videoSetMode(int32_t x, int32_t y, int32_t c, int32_t fs)\r\n'
         '{\r\n'),
    ]

    for pat in patterns:
        if pat in content:
            # Insert PSP2 block right after the opening brace line
            brace_end = content.find('\n', content.find(pat) + content.find('{\n', content.find(pat)) - content.find(pat))
            # More precise: find the { in this pattern and insert after the \n following it
            pat_pos = content.find(pat)
            brace_in_pat = pat.find('{\n')
            if brace_in_pat == -1:
                brace_in_pat = pat.find('{\r\n')
            insert_offset = pat_pos + brace_in_pat + pat[brace_in_pat:].index('\n') + 1
            content = content[:insert_offset] + PSP2_BLOCK + content[insert_offset:]
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"  {filepath} videoSetMode patched (PSP2 early-return, no SDL called)")
            return

    # Strategy 2: regex
    m = re.search(r'int32_t\s+videoSetMode\s*\(int32_t\s+x,\s*int32_t\s+y,\s*int32_t\s+c,\s*int32_t\s+fs\s*\)\s*\n\{', content)
    if m:
        insert_pos = m.end()  # right after the {
        # skip past the newline after {
        if content[insert_pos] == '\n':
            insert_pos += 1
        content = content[:insert_pos] + PSP2_BLOCK + content[insert_pos:]
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  {filepath} videoSetMode patched (regex match)")
        return

    print(f"  ERROR: Could not find videoSetMode signature in {filepath}")
    # Print context for debugging
    for i, line in enumerate(content.split('\n')[315:345], 316):
        print(f"    {i}: {line}")
    sys.exit(1)



def patch_config(filepath):
    """Patch config.cpp: force 640x400 as default resolution.
    SDL_GetDesktopDisplayMode returns 1280x720 on Vita causing buffer overflow."""
    with open(filepath, 'r') as f:
        src = f.read()

    if 'DNF_VITA_RES_PATCH' in src:
        print(f"  {filepath} already patched, skipping.")
        return

    changes = 0

    # Strategy 1: exact string replacements
    replacements = [
        ('ud.config.ScreenWidth = dm.w;',  'ud.config.ScreenWidth = 320; // DNF_VITA_RES_PATCH'),
        ('ud.config.ScreenHeight = dm.h;', 'ud.config.ScreenHeight = 200; // DNF_VITA_RES_PATCH'),
        ('ud.config.ScreenWidth = 1024;',  'ud.config.ScreenWidth = 320; // DNF_VITA_RES_PATCH'),
        ('ud.config.ScreenHeight = 768;',  'ud.config.ScreenHeight = 200; // DNF_VITA_RES_PATCH'),
    ]
    for old, new in replacements:
        if old in src:
            src = src.replace(old, new, 1)
            changes += 1
            print(f"    [OK] {old.split('=')[1].strip()} -> replaced")

    # Strategy 2: regex fallback for any ScreenWidth/Height assignment
    if changes == 0:
        print("    Exact matches failed, trying regex...")
        width_pat = r'(ud\.config\.ScreenWidth\s*=\s*)\w+(\.\w+)?;'
        height_pat = r'(ud\.config\.ScreenHeight\s*=\s*)\w+(\.\w+)?;'
        new_src = re.sub(width_pat, r'\g<1>320; // DNF_VITA_RES_PATCH', src)
        new_src = re.sub(height_pat, r'\g<1>200; // DNF_VITA_RES_PATCH', new_src)
        if new_src != src:
            src = new_src
            changes += 1
            print("    [OK] Regex replacement applied")

    # Strategy 3: inject PSP2 ifdef block after SDL_GetDesktopDisplayMode
    sdl_dm = 'SDL_GetDesktopDisplayMode'
    if sdl_dm in src:
        # Find the closing semicolon of the block containing SDL_GetDesktopDisplayMode
        dm_pos = src.find(sdl_dm)
        # Find next } or ; after this
        inject_pos = src.find(';', dm_pos)
        if inject_pos != -1:
            inject_pos += 1
            psp2_block = (
                '\n#ifdef __PSP2__\n'
                '    // DNF_VITA_RES_PATCH: Force 320x200 on Vita\n'
                '    ud.config.ScreenWidth = 320;\n'
                '    ud.config.ScreenHeight = 200;\n'
                '#endif\n'
            )
            src = src[:inject_pos] + psp2_block + src[inject_pos:]
            changes += 1
            print("    [OK] PSP2 ifdef block injected after SDL_GetDesktopDisplayMode")

    with open(filepath, 'w') as f:
        f.write(src)
    print(f"  {filepath} patched ({changes} changes)")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <sdlayer.cpp> <sdlayer12.cpp> [config.cpp]")
        sys.exit(1)

    patch_file(sys.argv[1], 'DNF_VITA_SKIP_SDL_SETVIDEOMODE')
    patch_file(sys.argv[2], 'DNF_VITA_SKIP_SDL_SETVIDEOMODE')
    if len(sys.argv) > 3:
        patch_config(sys.argv[3])
