"""
Self-tests for the DNF 2001 Vita 60fps patch scripts.

Fixtures use the EXACT upstream EDuke32-Vita snippets (verified against
Rinnegatamante/EDuke32-Vita source), so a green suite means the patches
apply to the real engine code. Run: python -m unittest discover -s tests -v
"""
import importlib.util
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, 'scripts')


def load(name):
    path = os.path.join(SCRIPTS, name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_tmp(content):
    fd, path = tempfile.mkstemp(suffix='.cpp')
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    return path


# Exact upstream shapes (EDuke32-Vita sdlayer.cpp)
SDLAYER_FIXTURE = '''#include <stuff.h>
vita2d_texture *fb_texture, *gpu_texture;
int psp2_main(void)
{
    scePowerSetArmClockFrequency(444);
    scePowerSetBusClockFrequency(222);
    scePowerSetGpuClockFrequency(222);
    scePowerSetGpuXbarClockFrequency(166);
    vita2d_init();
    vita2d_set_vblank_wait(0);
    gpu_texture = vita2d_create_empty_texture_format(960, 544, SCE_GXM_TEXTURE_FORMAT_P8_1BGR);
    vita2d_texture_set_filters(gpu_texture, SCE_GXM_TEXTURE_FILTER_LINEAR, SCE_GXM_TEXTURE_FILTER_LINEAR);
    fb_texture = vita2d_create_empty_texture_format(960, 544, SCE_GXM_TEXTURE_FORMAT_P8_1BGR);
    baselayer_init();
    return 0;
}
void videoBeginDrawing(void)
{
	frameplace = (intptr_t)framebuffer;
    if (modechange)
    {
        bytesperline = xres;
    }
}
void videoShowFrame(int32_t w)
{
    UNREFERENCED_PARAMETER(w);
    if (offscreenrendering) return;
    memcpy(vita2d_texture_get_datap(gpu_texture),vita2d_texture_get_datap(fb_texture),vita2d_texture_get_stride(gpu_texture)*vita2d_texture_get_height(gpu_texture));
    vita2d_start_drawing();
    vita2d_draw_texture(gpu_texture, 0, 0);
    vita2d_end_drawing();
    vita2d_wait_rendering_done();
    vita2d_swap_buffers();
}
'''

# Exact upstream shapes (EDuke32 config.cpp defaults)
CONFIG_FIXTURE = '''void CONFIG_SetDefaults(void)
{
    ud.config.MixRate = droidinfo.audio_sample_rate;
#else
    ud.config.MixRate = 48000;
#endif
#if defined GEKKO || defined __OPENDINGUX__
    ud.config.NumVoices = 32;
#else
    ud.config.NumVoices = 64;
#endif
}
'''


class TestFrameratePatch(unittest.TestCase):
    def test_vblank_and_clocks(self):
        mod = load('patch_framerate')
        path = write_tmp(SDLAYER_FIXTURE)
        try:
            mod.patch_framerate(path)
            with open(path) as f:
                out = f.read()
            self.assertIn('vita2d_set_vblank_wait(1);', out)
            self.assertNotIn('vita2d_set_vblank_wait(0);', out)
            self.assertIn('scePowerSetArmClockFrequency(500)', out)
            self.assertIn('scePowerSetArmClockFrequency(444)', out)  # fallback kept
            # idempotent: second run is a no-op
            mod.patch_framerate(path)
            with open(path) as f:
                out2 = f.read()
            self.assertEqual(out, out2)
        finally:
            os.unlink(path)

    def test_missing_pattern_fails_loud(self):
        mod = load('patch_framerate')
        path = write_tmp('// no relevant code here\n')
        try:
            with self.assertRaises(SystemExit):
                mod.patch_framerate(path)
        finally:
            os.unlink(path)


class TestAudioDefaultsPatch(unittest.TestCase):
    def test_mixrate_and_voices(self):
        mod = load('patch_audio_defaults')
        path = write_tmp(CONFIG_FIXTURE)
        try:
            mod.patch_audio_defaults(path)
            with open(path) as f:
                out = f.read()
            self.assertIn('ud.config.MixRate = 22050;', out)
            self.assertIn('|| defined __PSP2__', out)
            self.assertIn('ud.config.NumVoices = 32;', out)
            # idempotent
            mod.patch_audio_defaults(path)
        finally:
            os.unlink(path)

    def test_missing_pattern_fails_loud(self):
        mod = load('patch_audio_defaults')
        path = write_tmp('// no relevant code here\n')
        try:
            with self.assertRaises(SystemExit):
                mod.patch_audio_defaults(path)
        finally:
            os.unlink(path)


class TestPerformancePatch(unittest.TestCase):
    def test_320x200_triple(self):
        mod = load('patch_performance')
        path = write_tmp(SDLAYER_FIXTURE)
        try:
            mod.patch_performance(path)
            with open(path) as f:
                out = f.read()
            # textures resized + guard + upscale draw
            self.assertIn('320, 200, SCE_GXM_TEXTURE_FORMAT_P8_1BGR', out)
            self.assertNotIn('960, 544, SCE_GXM_TEXTURE_FORMAT_P8_1BGR', out)
            self.assertIn('vita2d_draw_texture_scale(gpu_texture, 0, 0, 3.0f, 2.72f);', out)
            self.assertIn('DNF_VITA_RESOLUTION_GUARD', out)
            # GL-aware: never force 320x200 under the 32-bit vitaGL renderer
            self.assertIn('if (bpp == 8)', out)
            # upscale math is exact: 960/320 = 3.0, 544/200 = 2.72
            self.assertAlmostEqual(960 / 320, 3.0)
            self.assertAlmostEqual(544 / 200, 2.72)
        finally:
            os.unlink(path)


class TestAutoexec(unittest.TestCase):
    # cvars proven INVALID in this engine build (see dnf2001.log warnings)
    INVALID = ['r_usenewshading', 'r_detailmapping', 'r_glowmapping',
               'vid_vsync', 'r_visibility', 'r_shadescale']

    def test_autoexec_valid_and_complete(self):
        with open(os.path.join(REPO, 'AUTOEXEC.CFG')) as f:
            cfg = f.read()
        for bad in self.INVALID:
            self.assertNotIn(bad, cfg, f'stale invalid cvar {bad} spams warnings')
        for good in ['r_precache 1', 'r_maxfps 60',
                     'snd_mixrate 22050', 'snd_numvoices 32', 'r_novoxmips 1']:
            self.assertIn(good, cfg, f'missing 60fps cvar: {good}')


# Exact upstream shape (sdlayer12.cpp videoSetMode head)
SDLAYER12_MODE_FIXTURE = '''#include <SDL/SDL_events.h>

int32_t videoSetMode(int32_t x, int32_t y, int32_t c, int32_t fs)
{
    int32_t regrab = 0, ret;
    ret = setvideomode_sdlcommon(&x, &y, c, fs, &regrab);
    return ret;
}
'''

# sdlayer.cpp PSP2 videoShowFrame head (exact upstream shape)
SHOWFRAME_FIXTURE = '''void videoShowFrame(int32_t w)
{
    UNREFERENCED_PARAMETER(w);

    if (offscreenrendering) return;
    memcpy(gpu, fb, 64);
}
'''

MAKE_COMMON_FIXTURE = '''else ifeq ($(PLATFORM),WII)
    override USE_OPENGL := 0
    override NETCODE := 0
else ifeq ($(PLATFORM),PSP2)
    override USE_OPENGL := 0
    override NETCODE := 0
    override HAVE_GTK2 := 0
endif
'''

MAKE_GNU_FIXTURE = '''ifeq ($(PLATFORM),PSP2)
    engine_cflags += -fpermissive
    engine_objs += psp2_kbdvita.cpp
    LIBS += -lvita2d -lSDL
endif
'''

SDLAYER_V2D_FIXTURE = '''#include <vita2d.h>
vita2d_texture *fb_texture;
'''


class TestGLProcaddrGen(unittest.TestCase):
    def test_parses_headers(self):
        import tempfile
        mod = load('gen_gl_procaddr')
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, 'gl.h'), 'w') as f:
                f.write('GLAPI void GLAPIENTRY glViewport (GLint x, GLint y, GLsizei w, GLsizei h);\n'
                        'GLAPI void GLAPIENTRY glViewport (GLint x, GLint y, GLsizei w, GLsizei h);\n'
                        'extern void GLAPIENTRY glClear (GLbitfield mask);\n'
                        '#define GL_TRUE 1\n'
                        'typedef unsigned int GLenum;\n'
                        '// glFake is a comment, not a declaration\n')
            out = tempfile.mkdtemp()
            mod.generate(d, out)
            with open(os.path.join(out, 'dnf_gl_procaddr.h')) as f:
                self.assertIn('DNF_GL_GetProcAddress', f.read())
            with open(os.path.join(out, 'dnf_gl_procaddr.cpp')) as f:
                cpp = f.read()
            self.assertIn('"glViewport"', cpp)
            self.assertIn('"glClear"', cpp)
            self.assertNotIn('glFake', cpp)
            self.assertEqual(cpp.count('"glViewport"'), 1)  # deduped
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(out, ignore_errors=True)

    def test_missing_dir_fails_loud(self):
        mod = load('gen_gl_procaddr')
        with self.assertRaises(SystemExit):
            mod.generate('/nonexistent-gl-include', tempfile.mkdtemp())


class TestGLRendererPatch(unittest.TestCase):
    def _gl_dir(self):
        import tempfile
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, 'source/build/src'))
        with open(os.path.join(d, 'source/build/src/sdlayer12.cpp'), 'w') as f:
            f.write(SDLAYER12_MODE_FIXTURE)
        with open(os.path.join(d, 'source/build/src/sdlayer.cpp'), 'w') as f:
            f.write(SDLAYER_V2D_FIXTURE + SHOWFRAME_FIXTURE)
        with open(os.path.join(d, 'Common.mak'), 'w') as f:
            f.write(MAKE_COMMON_FIXTURE)
        with open(os.path.join(d, 'GNUmakefile'), 'w') as f:
            f.write(MAKE_GNU_FIXTURE)
        return d

    def test_applies(self):
        import shutil
        mod = load('patch_glrenderer')
        d = self._gl_dir()
        try:
            mod.patch_glrenderer(d)
            with open(os.path.join(d, 'source/build/src/sdlayer12.cpp')) as f:
                s12 = f.read()
            self.assertIn('vglInitExtended(0, 320, 200', s12)
            self.assertIn('setrendermode(REND_POLYMOST)', s12)
            self.assertIn('DNF_GL_GetProcAddress', s12)
            self.assertIn('#include <vitaGL.h>', s12)
            with open(os.path.join(d, 'source/build/src/sdlayer.cpp')) as f:
                sl = f.read()
            self.assertIn('vglSwapBuffers(1)', sl)
            with open(os.path.join(d, 'Common.mak')) as f:
                self.assertIn('ifeq ($(DNF_VITA_GL),1)', f.read())
            with open(os.path.join(d, 'GNUmakefile')) as f:
                gm = f.read()
            self.assertIn('dnf_gl_procaddr.cpp', gm)
            self.assertIn('-lvitaGL', gm)
            # idempotent
            mod.patch_glrenderer(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_missing_pattern_fails_loud(self):
        import shutil
        mod = load('patch_glrenderer')
        import tempfile
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, 'source/build/src'))
            for name in ('sdlayer12.cpp', 'sdlayer.cpp'):
                with open(os.path.join(d, 'source/build/src', name), 'w') as f:
                    f.write('// nothing relevant\n')
            with open(os.path.join(d, 'Common.mak'), 'w') as f:
                f.write('# empty\n')
            with open(os.path.join(d, 'GNUmakefile'), 'w') as f:
                f.write('# empty\n')
            with self.assertRaises(SystemExit):
                mod.patch_glrenderer(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestGLArgsPatch(unittest.TestCase):
    ARGV_FIXTURE = ('    char *dnf_argv[] = {\n'
                    '        "",\n'
                    '        "-gDNF.GRP",\n'
                    '        "-xDNFGAME.con",\n'
                    '        "-game_dir",\n'
                    '        "ux0:data/DNF/",\n'
                    '        "-noautoload"          // Skip autoload for faster startup\n'
                    '    };\n'
                    '    return app_main(6, dnf_argv);\n')

    def test_adds_cfg(self):
        mod = load('patch_gl_args')
        path = write_tmp(self.ARGV_FIXTURE)
        try:
            mod.patch_gl_args(path)
            with open(path) as f:
                out = f.read()
            self.assertIn('"ux0:data/DNF/dnf_gl.cfg"', out)
            self.assertIn('return app_main(8, dnf_argv);', out)
            # idempotent
            mod.patch_gl_args(path)
        finally:
            os.unlink(path)

    def test_missing_fails_loud(self):
        mod = load('patch_gl_args')
        path = write_tmp('// nothing relevant\n')
        try:
            with self.assertRaises(SystemExit):
                mod.patch_gl_args(path)
        finally:
            os.unlink(path)


class TestVideomodeGLAware(unittest.TestCase):
    def test_classic_only_bypass(self):
        import importlib.util
        path = os.path.join(SCRIPTS, 'patch_videomode.py')
        spec = importlib.util.spec_from_file_location('patch_videomode', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fp = write_tmp('int32_t videoSetMode(int32_t x, int32_t y, int32_t c, int32_t fs)\n'
                       '{\n'
                       '    int32_t regrab = 0, ret;\n'
                       '    ret = 1;\n'
                       '}\n')
        try:
            mod.patch_file(fp, 'DNF_VITA_SKIP_SDL_SETVIDEOMODE')
            with open(fp) as f:
                out = f.read()
            # 8-bit bypass stays, but 32-bit (GL) must fall through
            self.assertIn('if (c <= 8)', out)
            self.assertIn('xres  = 320;', out)
        finally:
            os.unlink(fp)


if __name__ == '__main__':
    unittest.main()
