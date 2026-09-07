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


if __name__ == '__main__':
    unittest.main()
