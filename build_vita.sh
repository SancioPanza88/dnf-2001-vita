#!/bin/bash
set -e

###############################################################################
# DNF 2001 - PS Vita Standalone Build Script
# 
# This script:
# 1. Clones EDuke32-Vita by Rinnegatamante
# 2. Patches the source for standalone DNF 2001 mod loading
# 3. Builds the VPK using VitaSDK
#
# Requirements: VitaSDK installed with $VITASDK set
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build_eduke32"
EDUKE32_REPO="https://github.com/Rinnegatamante/EDuke32-Vita.git"

TITLE_ID="DNF200100"
APP_TITLE="DNF 2001 Vita"
APP_VER="01.00"

echo "============================================="
echo "  DNF 2001 - PS Vita Standalone Build"
echo "============================================="

# ── Step 1: Clone EDuke32-Vita ──────────────────────────────────────────────
if [ ! -d "${BUILD_DIR}" ]; then
    echo "[1/5] Cloning EDuke32-Vita..."
    git clone --depth 1 "${EDUKE32_REPO}" "${BUILD_DIR}"
else
    echo "[1/5] EDuke32-Vita already cloned, using existing..."
fi

cd "${BUILD_DIR}"

# ── Step 2: Patch the source for standalone DNF loading ─────────────────────
echo "[2/5] Patching source for standalone DNF 2001..."

# ── Patch sdlayer.cpp: Replace psp2_main to skip launcher UI ────────────────
SDLAYER_FILE="source/build/src/sdlayer.cpp"

if ! grep -q "DNF_VITA_STANDALONE" "${SDLAYER_FILE}"; then
    echo "  Patching ${SDLAYER_FILE}..."
    # Use the canonical patcher that preserves vita2d initialization
    python3 "${SCRIPT_DIR}/scripts/patch_sdlayer.py" "${SDLAYER_FILE}"
fi

# ── Patch game.cpp: Change log path and data directory ──────────────────────
GAME_FILE="source/duke3d/src/game.cpp"

if ! grep -q "DNF_VITA_STANDALONE" "${GAME_FILE}"; then
    echo "  Patching ${GAME_FILE}..."
    
    # Change the log file path
    sed -i 's|OSD_SetLogFile("ux0:data/EDuke32/eduke32.log");|OSD_SetLogFile("ux0:data/DNF/dnf2001.log"); // DNF_VITA_STANDALONE|g' "${GAME_FILE}"
    
    echo "  game.cpp patched successfully"
fi

# ── Patch common.cpp: Change default search paths ──────────────────────────
COMMON_FILE="source/duke3d/src/common.cpp"

if [ -f "${COMMON_FILE}" ] && ! grep -q "DNF_VITA_STANDALONE" "${COMMON_FILE}"; then
    echo "  Patching ${COMMON_FILE}..."
    
    # Replace EDuke32 data path with DNF data path
    sed -i 's|ux0:data/EDuke32|ux0:data/DNF|g' "${COMMON_FILE}"
    # Add marker
    sed -i '1s/^/\/\/ DNF_VITA_STANDALONE patched\n/' "${COMMON_FILE}"
    
    echo "  common.cpp patched successfully"
fi

# ── Also patch any other files that reference the EDuke32 data path ─────────
echo "  Patching remaining data path references..."
find source/ -name "*.cpp" -o -name "*.c" -o -name "*.h" | while read f; do
    if grep -q "ux0:data/EDuke32" "$f" && ! grep -q "DNF_VITA_STANDALONE" "$f"; then
        sed -i 's|ux0:data/EDuke32|ux0:data/DNF|g' "$f"
    fi
done

# ── Patch the thread name ───────────────────────────────────────────────────
sed -i 's|sceKernelCreateThread("EDuke32"|sceKernelCreateThread("DNF2001"|g' "${SDLAYER_FILE}"

# ── Apply performance optimizations ────────────────────────────────────────
echo "  Applying performance optimizations..."
python3 "${SCRIPT_DIR}/scripts/patch_performance.py" "${SDLAYER_FILE}"

# Also patch videoSetMode for correct resolution
python3 "${SCRIPT_DIR}/scripts/patch_videomode.py" "${SDLAYER_FILE}" "${BUILD_DIR}/source/build/src/sdlayer12.cpp" "${BUILD_DIR}/source/duke3d/src/config.cpp"

# DNF_VITA_60FPS: vsync pacing (vblank wait) + best-effort 500MHz clocks
python3 "${SCRIPT_DIR}/scripts/patch_framerate.py" "${SDLAYER_FILE}"

# DNF_VITA_AUDIO: 22050Hz / 32 voices engine defaults (4x less mixing work)
python3 "${SCRIPT_DIR}/scripts/patch_audio_defaults.py" "${BUILD_DIR}/source/duke3d/src/config.cpp"

# Patch controls for FPS layout (config-level axis mapping)
echo "  Patching controls..."
python3 "${SCRIPT_DIR}/scripts/patch_controls.py" "${BUILD_DIR}/source/duke3d/src/_functio.h" "${BUILD_DIR}/source/duke3d/src/config.cpp"

# ── Step 3: Copy custom LiveArea assets ─────────────────────────────────────
echo "[3/5] Setting up VPK assets..."

# Create/copy icon and LiveArea if they exist in our project
if [ -d "${SCRIPT_DIR}/vita_assets" ]; then
    echo "  Copying custom vita_assets..."
    if [ -f "${SCRIPT_DIR}/vita_assets/icon0.png" ]; then
        # Find where the original icon is and replace it
        find . -name "icon0.png" -exec cp "${SCRIPT_DIR}/vita_assets/icon0.png" {} \;
    fi
    if [ -d "${SCRIPT_DIR}/vita_assets/livearea" ]; then
        find . -path "*/livearea/contents" -type d -exec cp -r "${SCRIPT_DIR}/vita_assets/livearea/contents/"* {} \;
    fi
fi

# ── Step 4: Build ───────────────────────────────────────────────────────────
echo "[4/5] Building EDuke32 for PS Vita (PLATFORM=PSP2)..."

# Clean previous build
make clean PLATFORM=PSP2 2>/dev/null || true

# DNF_VITA_PERFORMANCE: Remove debug symbols for release performance
sed -i 's/-mcpu=cortex-a9 -g -ffast-math/-mcpu=cortex-a9 -ffast-math/g' Common.mak

# DNF: Fix static linking order (SDL_mixer dependencies must come after SDL_mixer)
sed -i 's|-lSDL_mixer -lSDL -lmikmod -lspeexdsp|-lSDL_mixer -lFLAC -lvorbisfile -lvorbis -logg -lSDL -lmikmod -lspeexdsp|g' GNUmakefile

# DNF_VITA_PERFORMANCE: Ensure -O3 is actually used in the Makefile
# OPTLEVEL=3 passed to make may be ignored if Common.mak hardcodes -O0/-O2.
# Replace any hardcoded lower optimization levels with -O3.
sed -i 's/-O0\b/-O3/g; s/-O1\b/-O3/g; s/-O2\b/-O3/g' Common.mak
# Also add -O3 to CFLAGS if it does not already set an optimization level
if ! grep -q '\-O[0-3]' Common.mak; then
    sed -i 's/^CFLAGS\s*=/CFLAGS = -O3/' Common.mak
fi

# Build with PSP2 target (OPTLEVEL=3 for max optimization)
make -j$(nproc) PLATFORM=PSP2 RELEASE=1 USE_OPENGL=0 POLYMER=0 NETCODE=0 HAVE_GTK2=0 \
    STARTUP_WINDOW=0 USE_LIBVPX=0 LUNATIC=0 SIMPLE_MENU=1 \
    OPTLEVEL=3

echo "  Build completed!"

# ── Step 5: Package VPK ─────────────────────────────────────────────────────
echo "[5/5] Packaging VPK..."

ELF_FILE=""
# Find the built ELF file
for f in eduke32.elf duke3d.elf *.elf; do
    if [ -f "$f" ]; then
        ELF_FILE="$f"
        break
    fi
done

if [ -z "${ELF_FILE}" ]; then
    echo "ERROR: No ELF file found! Build may have failed."
    exit 1
fi

echo "  Found ELF: ${ELF_FILE}"

# Create VELF
vita-elf-create "${ELF_FILE}" dnf2001.velf

# Create EBOOT
vita-make-fself -s dnf2001.velf eboot.bin

# Create param.sfo
vita-mksfoex -s TITLE_ID="${TITLE_ID}" -d ATTRIBUTE2=12 "${APP_TITLE}" param.sfo

# Prepare VPK directory structure
VPK_DIR="${SCRIPT_DIR}/vpk_contents"
rm -rf "${VPK_DIR}"
mkdir -p "${VPK_DIR}/sce_sys/livearea/contents"

cp eboot.bin "${VPK_DIR}/eboot.bin"
cp param.sfo "${VPK_DIR}/sce_sys/param.sfo"

# Copy LiveArea assets
if [ -f "${SCRIPT_DIR}/vita_assets/icon0.png" ]; then
    cp "${SCRIPT_DIR}/vita_assets/icon0.png" "${VPK_DIR}/sce_sys/icon0.png"
elif [ -f "sce_sys/icon0.png" ]; then
    cp "sce_sys/icon0.png" "${VPK_DIR}/sce_sys/icon0.png"
else
    # Generate a simple icon using ImageMagick if available
    if command -v convert &> /dev/null; then
        convert -size 128x128 xc:'#1a1a2e' \
            -fill '#e94560' -font Helvetica-Bold -pointsize 20 \
            -gravity center -annotate 0 "DNF\n2001" \
            "${VPK_DIR}/sce_sys/icon0.png"
    else
        echo "  WARNING: No icon0.png found and ImageMagick not available."
        echo "  Creating minimal placeholder icon..."
        python3 "${SCRIPT_DIR}/scripts/gen_icon.py" "${VPK_DIR}/sce_sys/icon0.png"
    fi
fi

if [ -f "${SCRIPT_DIR}/vita_assets/livearea/contents/template.xml" ]; then
    cp "${SCRIPT_DIR}/vita_assets/livearea/contents/template.xml" "${VPK_DIR}/sce_sys/livearea/contents/"
else
    cp "${SCRIPT_DIR}/vita_livearea/template.xml" "${VPK_DIR}/sce_sys/livearea/contents/" 2>/dev/null || true
fi

if [ -f "${SCRIPT_DIR}/vita_assets/livearea/contents/bg.png" ]; then
    cp "${SCRIPT_DIR}/vita_assets/livearea/contents/bg.png" "${VPK_DIR}/sce_sys/livearea/contents/"
fi
if [ -f "${SCRIPT_DIR}/vita_assets/livearea/contents/startup.png" ]; then
    cp "${SCRIPT_DIR}/vita_assets/livearea/contents/startup.png" "${VPK_DIR}/sce_sys/livearea/contents/"
fi

# Pack VPK
cd "${VPK_DIR}"
vita-pack-vpk -s sce_sys/param.sfo -b eboot.bin \
    -a sce_sys/icon0.png=sce_sys/icon0.png \
    -a sce_sys/livearea/contents/template.xml=sce_sys/livearea/contents/template.xml \
    -a sce_sys/livearea/contents/bg.png=sce_sys/livearea/contents/bg.png \
    -a sce_sys/livearea/contents/startup.png=sce_sys/livearea/contents/startup.png \
    "${SCRIPT_DIR}/DNF2001_Vita.vpk" 2>/dev/null || \
vita-pack-vpk -s sce_sys/param.sfo -b eboot.bin \
    "${SCRIPT_DIR}/DNF2001_Vita.vpk"

# ── Step 6 (optional): EXPERIMENTAL vitaGL renderer build ────────────────────
# Set BUILD_GL=1 to also produce DNF2001_Vita_GL.vpk (GPU renderer, needs
# hardware testing - see README "Renderer GPU"). Requires vitaGL installed
# (vdpm vitagl) and $VITASDK set. Uses a separate build dir so the stable
# build above is never touched.
if [ "${BUILD_GL:-0}" = "1" ]; then
    echo ""
    echo "============================================="
    echo "  EXPERIMENTAL vitaGL renderer build"
    echo "============================================="

    GL_BUILD_DIR="${SCRIPT_DIR}/build_eduke32_gl"
    GL_TITLE_ID="DNF2001GL"
    GL_APP_TITLE="DNF 2001 GL"

    if [ -z "${VITASDK:-}" ]; then
        echo "ERROR: \$VITASDK not set (needed for vitaGL headers)."
        exit 1
    fi
    if [ ! -d "${VITASDK}/arm-vita-eabi/include/GL" ]; then
        echo "ERROR: vitaGL headers not found. Install with: vdpm vitagl"
        exit 1
    fi

    if [ ! -d "${GL_BUILD_DIR}" ]; then
        echo "[GL 1/4] Cloning EDuke32-Vita (GL build dir)..."
        git clone --depth 1 "${EDUKE32_REPO}" "${GL_BUILD_DIR}"
    else
        echo "[GL 1/4] EDuke32-Vita GL dir exists, reusing..."
    fi
    cd "${GL_BUILD_DIR}"

    echo "[GL 2/4] Patching (stable patches + GL renderer)..."
    GL_SDLAYER="source/build/src/sdlayer.cpp"
    if ! grep -q "DNF_VITA_STANDALONE" "${GL_SDLAYER}"; then
        python3 "${SCRIPT_DIR}/scripts/patch_sdlayer.py" "${GL_SDLAYER}"
    fi
    GL_GAME="source/duke3d/src/game.cpp"
    if ! grep -q "DNF_VITA_STANDALONE" "${GL_GAME}"; then
        sed -i 's|OSD_SetLogFile("ux0:data/EDuke32/eduke32.log");|OSD_SetLogFile("ux0:data/DNF/dnf2001_gl.log"); // DNF_VITA_STANDALONE|g' "${GL_GAME}"
    fi
    GL_COMMON="source/duke3d/src/common.cpp"
    if [ -f "${GL_COMMON}" ] && ! grep -q "DNF_VITA_STANDALONE" "${GL_COMMON}"; then
        sed -i 's|ux0:data/EDuke32|ux0:data/DNF|g' "${GL_COMMON}"
        sed -i '1s/^/\/\/ DNF_VITA_STANDALONE patched\n/' "${GL_COMMON}"
    fi
    find source/ -name "*.cpp" -o -name "*.c" -o -name "*.h" | while read f; do
        if grep -q "ux0:data/EDuke32" "$f" && ! grep -q "DNF_VITA_STANDALONE" "$f"; then
            sed -i 's|ux0:data/EDuke32|ux0:data/DNF|g' "$f"
        fi
    done
    sed -i 's|sceKernelCreateThread("EDuke32"|sceKernelCreateThread("DNF2001"|g' "${GL_SDLAYER}"
    python3 "${SCRIPT_DIR}/scripts/patch_performance.py" "${GL_SDLAYER}"
    python3 "${SCRIPT_DIR}/scripts/patch_videomode.py" "${GL_SDLAYER}" "${GL_BUILD_DIR}/source/build/src/sdlayer12.cpp" "${GL_BUILD_DIR}/source/duke3d/src/config.cpp"
    python3 "${SCRIPT_DIR}/scripts/patch_framerate.py" "${GL_SDLAYER}"
    python3 "${SCRIPT_DIR}/scripts/patch_audio_defaults.py" "${GL_BUILD_DIR}/source/duke3d/src/config.cpp"
    python3 "${SCRIPT_DIR}/scripts/patch_controls.py" "${GL_BUILD_DIR}/source/duke3d/src/_functio.h" "${GL_BUILD_DIR}/source/duke3d/src/config.cpp"
    python3 "${SCRIPT_DIR}/scripts/patch_glrenderer.py" "${GL_BUILD_DIR}"
    python3 "${SCRIPT_DIR}/scripts/gen_gl_procaddr.py" \
        "${VITASDK}/arm-vita-eabi/include/GL" \
        "${GL_BUILD_DIR}/source/build/src"

    echo "[GL 3/4] Building (USE_OPENGL via DNF_VITA_GL=1)..."
    sed -i 's/-mcpu=cortex-a9 -g -ffast-math/-mcpu=cortex-a9 -ffast-math/g' Common.mak
    sed -i 's|-lSDL_mixer -lSDL -lmikmod -lspeexdsp|-lSDL_mixer -lFLAC -lvorbisfile -lvorbis -logg -lSDL -lmikmod -lspeexdsp|g' GNUmakefile
    sed -i 's/-O0\b/-O3/g; s/-O1\b/-O3/g; s/-O2\b/-O3/g' Common.mak
    if ! grep -q '\-O[0-3]' Common.mak; then
        sed -i 's/^CFLAGS\s*=/CFLAGS = -O3/' Common.mak
    fi
    DNF_VITA_GL=1 make -j$(nproc) PLATFORM=PSP2 RELEASE=1 USE_OPENGL=0 POLYMER=0 NETCODE=0 HAVE_GTK2=0 \
        STARTUP_WINDOW=0 USE_LIBVPX=0 LUNATIC=0 SIMPLE_MENU=1 \
        OPTLEVEL=3
    # NOTE: USE_OPENGL=0 on the command line is overridden by Common.mak, which
    # flips it to 1 when DNF_VITA_GL=1 is in the environment (see patch_glrenderer.py).

    echo "[GL 4/4] Packaging experimental VPK..."
    GL_ELF=""
    for f in eduke32.elf duke3d.elf *.elf; do
        if [ -f "$f" ]; then GL_ELF="$f"; break; fi
    done
    if [ -z "${GL_ELF}" ]; then
        echo "ERROR: No GL ELF file found! Experimental build failed."
        exit 1
    fi
    vita-elf-create "${GL_ELF}" dnf2001gl.velf
    vita-make-fself -s dnf2001gl.velf eboot.bin
    vita-mksfoex -s TITLE_ID="${GL_TITLE_ID}" -d ATTRIBUTE2=12 "${GL_APP_TITLE}" param.sfo
    GL_VPK_DIR="${SCRIPT_DIR}/vpk_contents_gl"
    rm -rf "${GL_VPK_DIR}"
    mkdir -p "${GL_VPK_DIR}/sce_sys/livearea/contents"
    cp eboot.bin param.sfo "${GL_VPK_DIR}/" 2>/dev/null || cp eboot.bin "${GL_VPK_DIR}/eboot.bin"
    cp param.sfo "${GL_VPK_DIR}/sce_sys/param.sfo"
    cp "${VPK_DIR}/sce_sys/icon0.png" "${GL_VPK_DIR}/sce_sys/icon0.png" 2>/dev/null || true
    cp "${VPK_DIR}/sce_sys/livearea/contents/"* "${GL_VPK_DIR}/sce_sys/livearea/contents/" 2>/dev/null || true
    cd "${GL_VPK_DIR}"
    vita-pack-vpk -s sce_sys/param.sfo -b eboot.bin \
        "${SCRIPT_DIR}/DNF2001_Vita_GL.vpk"

    echo ""
    echo "============================================="
    echo "  EXPERIMENTAL GL BUILD COMPLETE!"
    echo "  VPK: ${SCRIPT_DIR}/DNF2001_Vita_GL.vpk"
    echo "  Install NEXT TO the stable build and report results (see README)."
    echo "============================================="
fi

echo ""
echo "============================================="
echo "  BUILD COMPLETE!"
echo "  VPK: ${SCRIPT_DIR}/DNF2001_Vita.vpk"
echo "============================================="
echo ""
echo "Installation:"
echo "  1. Transfer DNF2001_Vita.vpk to your Vita and install"
echo "  2. Copy the following files to ux0:data/DNF/ on your Vita:"
echo "     - DUKE3D.GRP (from original Duke Nukem 3D)"
echo "     - DNF.GRP"
echo "     - DNFGAME.CON"
echo "     - DNF.CON"
echo "     - DEFS.CON"
echo "     - USER.CON"
echo "     - EBIKE.CON"
echo "     - All .CFG and .MAP files"
echo "============================================="
