import unittest

from app.schemas import MiniMaxH3Request
from app.workflow import build_workflow, frame_count


class WorkflowTest(unittest.TestCase):
    def request(self, **changes):
        data = {
            "prompt": "Use all references.",
            "images": ["a"],
            "diffusion_model": (
                "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
            ),
            "text_encoder": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            "seed": 42,
        }
        data.update(changes)
        return MiniMaxH3Request(**data)

    def test_frame_count_uses_official_grid(self):
        self.assertEqual(frame_count(5), 124)
        self.assertEqual(frame_count(15), 362)

    def test_builds_dynamic_image_video_audio_nodes(self):
        req = self.request(
            images=["a", "b"],
            videos=["c"],
            audios=["d"],
        )
        graph, seed, frames = build_workflow(
            req,
            ["one.png", "two.png"],
            ["clip.mp4"],
            ["voice.wav"],
        )
        conditioning = graph["136"]["inputs"]
        self.assertEqual(conditioning["ref_images.ref_image_0"], ["1000", 0])
        self.assertEqual(conditioning["ref_images.ref_image_1"], ["1001", 0])
        self.assertEqual(conditioning["ref_videos.ref_video_0"], ["1200", 0])
        self.assertEqual(
            conditioning["ref_video_audios.ref_video_audio_0"],
            ["1200", 1],
        )
        self.assertEqual(conditioning["ref_audios.ref_audio_0"], ["1300", 0])
        self.assertEqual(graph["1100"]["class_type"], "LoadVideo")
        self.assertEqual(graph["1200"]["class_type"], "GetVideoComponents")
        self.assertEqual((seed, frames), (42, 124))

    def test_selects_models_and_fixed_vaes(self):
        req = self.request()
        graph, _, _ = build_workflow(req, ["one.png"], [], [])
        self.assertEqual(graph["127"]["inputs"]["unet_name"], req.diffusion_model)
        self.assertEqual(graph["128"]["inputs"]["clip_name"], req.text_encoder)
        self.assertEqual(
            graph["119"]["inputs"]["vae_name"],
            "minimax_h3_video_vae_fp16.safetensors",
        )
        self.assertEqual(
            graph["120"]["inputs"]["vae_name"],
            "minimax_h3_audio_vae_fp32.safetensors",
        )

    def test_lora_switches_model_and_steps(self):
        graph, _, _ = build_workflow(
            self.request(enable_lora=True, steps=20),
            ["one.png"],
            [],
            [],
        )
        self.assertEqual(graph["145"]["inputs"]["strength_model"], 1.0)
        self.assertEqual(graph["124"]["inputs"]["model"], ["145", 0])
        self.assertEqual(graph["126"]["inputs"]["model"], ["145", 0])
        self.assertEqual(graph["124"]["inputs"]["steps"], 4)

        graph, _, _ = build_workflow(
            self.request(enable_lora=False, steps=18),
            ["one.png"],
            [],
            [],
        )
        self.assertNotIn("145", graph)
        self.assertEqual(graph["124"]["inputs"]["model"], ["127", 0])
        self.assertEqual(graph["124"]["inputs"]["steps"], 18)

    def test_rejects_uploaded_filename_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "数量"):
            build_workflow(self.request(), [], [], [])
