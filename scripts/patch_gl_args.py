"""
Patch the standalone DNF argv (GL build dir only) to load dnf_gl.cfg.

Appends "-cfg ux0:data/DNF/dnf_gl.cfg" to the dnf_argv array injected by
patch_sdlayer.py and bumps the app_main() argc 6 -> 8. GL build dir only;
the stable build keeps its argv untouched.
"""
import sys


def patch_gl_args(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    if 'dnf_gl.cfg' in content:
        print("  dnf_gl.cfg argv already present - nothing to do.")
        return

    old_argv = ('        "-noautoload"          // Skip autoload for faster startup\n'
                '    };\n')
    new_argv = ('        "-noautoload",         // Skip autoload for faster startup\n'
                '        "-cfg",                // GL perf config (see dnf_gl.cfg)\n'
                '        "ux0:data/DNF/dnf_gl.cfg",\n'
                '    };\n')
    if old_argv not in content:
        print("    [FAIL] dnf_argv block not found!")
        sys.exit(1)
    content = content.replace(old_argv, new_argv, 1)
    print("    [OK] dnf_argv: +dnf_gl.cfg")

    old_main = '    return app_main(6, dnf_argv);\n'
    new_main = '    return app_main(8, dnf_argv);\n'
    if old_main not in content:
        print("    [FAIL] app_main(6, dnf_argv) not found!")
        sys.exit(1)
    content = content.replace(old_main, new_main, 1)
    print("    [OK] app_main argc 6 -> 8")

    with open(filepath, 'w') as f:
        f.write(content)

    print("\n  Patched: GL argv loads dnf_gl.cfg")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_sdlayer.cpp>")
        sys.exit(1)

    patch_gl_args(sys.argv[1])
