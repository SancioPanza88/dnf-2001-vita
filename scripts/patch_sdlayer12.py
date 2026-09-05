"""
Patch sdlayer12.cpp (SDL1 layer) for PSP2.

Instead of finding the function signature (which varies), we find the
SDL_SetVideoMode call and insert a PSP2 early-return BEFORE it.
This is guaranteed to work regardless of function name or signature formatting.
"""
import sys
import re


def patch_sdlayer12(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    if 'DNF_VITA_SKIP_SETGAMEMODE' in content:
        print(f"  {filepath} already patched, skipping.")
        return

    # Dump all lines containing function signatures for debugging
    print(f"  === sdlayer12.cpp function signatures ===")
    for i, line in enumerate(content.split('\n'), 1):
        stripped = line.strip()
        if re.match(r'(?:int32_t|int|static)\s+\w+\s*\(', stripped) and '{' not in stripped:
            print(f"    line {i}: {stripped}")
        elif re.match(r'(?:int32_t|int|static)\s+\w+\s*\([^;]+\)\s*\{', stripped):
            print(f"    line {i}: {stripped[:80]}")

    psp2_early_return = (
        '#ifdef __PSP2__\n'
        '    // DNF_VITA_SKIP_SETGAMEMODE: SDL_SetVideoMode not supported on Vita.\n'
        '    // Bypass entirely - set engine globals directly.\n'
        '    xres = xdim = 320;\n'
        '    yres = ydim = 200;\n'
        '    bpp  = dabpp;\n'
        '    fullscreen   = davidoption;\n'
        '    bytesperline = 320;\n'
        '    numpages     = 1;\n'
        '    lockcount    = 0;\n'
        '    modechange   = 1;\n'
        '    videomodereset = 0;\n'
        '    return 0;\n'
        '#endif\n'
        '    // DNF_VITA_SKIP_SETGAMEMODE\n'
    )

    # Strategy A: find SDL_SetVideoMode call and insert PSP2 block before it
    # Find the line with SDL_SetVideoMode
    lines = content.split('\n')
    sdl_line_idx = None
    for i, line in enumerate(lines):
        if 'SDL_SetVideoMode' in line and '#' not in line.split('SDL_SetVideoMode')[0]:
            sdl_line_idx = i
            print(f"  Found SDL_SetVideoMode at line {i+1}: {line.strip()}")
            break

    if sdl_line_idx is not None:
        # Get the indentation of that line
        indent = len(lines[sdl_line_idx]) - len(lines[sdl_line_idx].lstrip())
        # Insert PSP2 block before this line
        psp2_lines = psp2_early_return.split('\n')
        # Indent the block content (not the preprocessor directives)
        indented_block = []
        for pline in psp2_lines:
            if pline.startswith('#') or pline == '':
                indented_block.append(pline)
            else:
                indented_block.append(' ' * indent + pline.lstrip())
        lines[sdl_line_idx:sdl_line_idx] = indented_block
        content = '\n'.join(lines)
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  {filepath} patched: PSP2 block inserted before SDL_SetVideoMode")
        return

    # Strategy B: loose regex on function name
    m = re.search(r'videoSetGameMode\s*\([^)]*\)\s*\n?\{', content)
    if m:
        insert_pos = content.find('{', m.start()) + 1
        content = content[:insert_pos] + '\n' + psp2_early_return + content[insert_pos:]
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  {filepath} patched via function name regex")
        return

    # Nothing worked - dump first 120 lines
    print(f"  WARNING: Could not patch {filepath}!")
    print(f"  === First 120 lines of {filepath} ===")
    for i, line in enumerate(content.split('\n')[:120], 1):
        print(f"  {i:4d}: {line}")
    print(f"  WARNING: Build will fail at video mode init!")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_sdlayer12.cpp>")
        sys.exit(1)
    patch_sdlayer12(sys.argv[1])
