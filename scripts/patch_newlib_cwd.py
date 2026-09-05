"""
Remove PSP2 stubs for getcwd/chdir from EDuke32 sdlayer.cpp.

Recent vitasdk/newlib provides these symbols in libc; keeping the stubs causes
multiple definition errors at link time (e.g. with GCC 15).
"""
import sys


def patch(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if "DNF_VITA_NEWLIB_CWD" in content:
        print(f"  {filepath} already patched for newlib cwd, skipping.")
        return

    key = "#define MAX_CURDIR_PATH"
    start = content.find(key)
    if start == -1:
        print(f"  WARNING: {key!r} not found in {filepath}, skipping newlib cwd patch.")
        return

    sig = "int chdir(const char *path)"
    chdir_pos = content.find(sig, start)
    if chdir_pos == -1:
        print(f"  WARNING: chdir stub not found in {filepath}, skipping.")
        return

    brace_open = content.find("{", chdir_pos)
    if brace_open == -1:
        print(f"  ERROR: could not find opening brace for chdir in {filepath}")
        sys.exit(1)

    depth = 0
    i = brace_open
    while i < len(content):
        c = content[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(content) and content[end] == "\n":
                    end += 1
                insert = (
                    "int can_use_IME_keyboard = 1;\n"
                    "// DNF_VITA_NEWLIB_CWD: getcwd/chdir stubs removed; "
                    "provided by Vita newlib (avoids duplicate symbols with libc).\n"
                )
                content = content[:start] + insert + content[end:]
                with open(filepath, "w", encoding="utf-8", newline="\n") as f:
                    f.write(content)
                print(f"  {filepath}: removed getcwd/chdir stubs for newlib compatibility")
                return
        i += 1

    print(f"  ERROR: unbalanced braces in chdir stub ({filepath})")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_sdlayer.cpp>")
        sys.exit(1)
    patch(sys.argv[1])
