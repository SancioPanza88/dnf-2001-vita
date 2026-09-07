"""
Patch config.cpp defaults for PS Vita DNF 2001 port - audio CPU cost.

ROOT CAUSE (verified against upstream EDuke32-Vita source):
  - config.cpp defaults on PSP2: MixRate = 48000, NumVoices = 64, stereo 16-bit.
  - sounds.cpp: FX_Init(NumVoices, NumChannels, MixRate) -> software mixing of
    64 voices x 48000 samples/s on a 444MHz Cortex-A9 every frame.
  - Cutting to 22050Hz / 32 voices ~= 4x less mixing work (~23% of original).

The same values are also forced at runtime via AUTOEXEC.CFG
(snd_mixrate / snd_numvoices cvars - both verified to exist in osdcmds.cpp);
this source patch is belt-and-suspenders so even a stale user config boots fast.
"""
import sys


def patch_audio_defaults(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    if 'DNF_VITA_AUDIO_DEFAULTS' in content:
        print("  DNF_VITA_AUDIO_DEFAULTS already set - nothing to do.")
        return

    # --- 1. MixRate 48000 -> 22050 on PSP2 ---
    mix_old = (
        '    ud.config.MixRate = droidinfo.audio_sample_rate;\n'
        '#else\n'
        '    ud.config.MixRate = 48000;\n'
    )
    mix_new = (
        '    ud.config.MixRate = droidinfo.audio_sample_rate;\n'
        '#elif defined __PSP2__\n'
        '    ud.config.MixRate = 22050; // DNF_VITA_AUDIO_DEFAULTS\n'
        '#else\n'
        '    ud.config.MixRate = 48000;\n'
    )
    if mix_old in content:
        content = content.replace(mix_old, mix_new, 1)
        print("    [OK] MixRate default 22050 on PSP2")
    else:
        print("    [FAIL] MixRate default block not found!")
        sys.exit(1)

    # --- 2. NumVoices 64 -> 32 on PSP2 ---
    vox_old = (
        '#if defined GEKKO || defined __OPENDINGUX__\n'
        '    ud.config.NumVoices = 32;\n'
        '#else\n'
        '    ud.config.NumVoices = 64;\n'
        '#endif\n'
    )
    vox_new = (
        '#if defined GEKKO || defined __OPENDINGUX__ || defined __PSP2__\n'
        '    ud.config.NumVoices = 32; // DNF_VITA_AUDIO_DEFAULTS\n'
        '#else\n'
        '    ud.config.NumVoices = 64;\n'
        '#endif\n'
    )
    if vox_old in content:
        content = content.replace(vox_old, vox_new, 1)
        print("    [OK] NumVoices default 32 on PSP2")
    else:
        print("    [FAIL] NumVoices default block not found!")
        sys.exit(1)

    with open(filepath, 'w') as f:
        f.write(content)

    print("\n  Patched: audio defaults (22050Hz, 32 voices on PSP2)")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path_to_config.cpp>")
        sys.exit(1)

    patch_audio_defaults(sys.argv[1])
