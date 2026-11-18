"""Bounded parallelism, unchanged font geometry and process accounting."""
import math
import unittest
from unittest.mock import patch
from PIL import ImageFont
from app.pipeline import hyperframes as hf, hyperframes_layout as layout
from scripts.profile_hyperframes import summarize_processes


class CaptureSettingsTests(unittest.TestCase):
    def test_existing_callers_remain_one_worker_without_new_settings(self):
        self.assertEqual(hf.render_workers({}),1)
        self.assertEqual(hf.render_workers({'workers':2}),2)

    def test_invalid_or_excessive_parallelism_is_rejected_before_execution(self):
        for value in [0,3,20,-1,True,1.0,'2',None]:
            with self.subTest(value=value),self.assertRaises(hf.AdapterValidationError):hf.render_workers({'workers':value})

    def test_low_memory_explicitly_pins_parallel_capture_to_one(self):
        self.assertEqual(hf.render_workers({'workers':2,'low_memory':True}),1)


class FontReuseTests(unittest.TestCase):
    def tearDown(self):layout.font.cache_clear()

    def test_repeated_caption_measurement_does_not_reload_font(self):
        layout.font.cache_clear()
        with patch.object(layout.ImageFont,'truetype',wraps=ImageFont.truetype) as load:
            hf._font_size(['한국어 자막'],58,810)
            hf._font_size(['다음 단어도 보존해요'],58,810)
        self.assertEqual(load.call_count,1)

    def test_cached_metrics_match_original_700_weight_geometry(self):
        original=ImageFont.truetype(str(hf.FONT),58);original.set_variation_by_axes([700])
        for text in ['한글 가독성과 단어 경계','Original caption & source','아주긴한국어단어도그대로유지합니다']:
            expected=min(58,math.floor(58*810/max(1,original.getlength(text))))
            self.assertEqual(hf._font_size([text],58,810),expected)


class ResourceAccountingTests(unittest.TestCase):
    def item(self,created,cpu,read):
        return {'pid':42,'created':created,'name':'ffmpeg.exe','parent':1,'cpu':cpu,'working':100,'private':80,'io':{'read_bytes':read}}

    def test_repeated_samples_keep_cumulative_cpu_and_io_maxima(self):
        got=summarize_processes([{'elapsed_seconds':1,'instances':[self.item(100,1,50)]},
                                {'elapsed_seconds':2,'instances':[self.item(100,2,90)]}])
        self.assertEqual(len(got),1);self.assertEqual(got[0]['cpu_seconds'],2)
        self.assertEqual(got[0]['io']['read_bytes'],90)

    def test_reused_pid_is_a_separate_process_instance(self):
        got=summarize_processes([{'elapsed_seconds':1,'instances':[self.item(100,1,50)]},
                                {'elapsed_seconds':2,'instances':[self.item(200,.5,20)]}])
        self.assertEqual(len(got),2);self.assertEqual(sum(x['cpu_seconds'] for x in got),1.5)
