import unittest

from app.schemas import MiniMaxH3Ref2VARequest, QwenImageEditRequest, QwenImageRequest
from app.workflow import (
    build_minimax_workflow,
    build_qwen_edit_workflow,
    build_qwen_image_workflow,
    minimax_frame_count,
)


class MiniMaxWorkflowTest(unittest.TestCase):
    def request(self, **changes):
        data = {
            "prompt": "Use all references.",
            "images": ["image"],
            "seed": 42,
        }
        data.update(changes)
        return MiniMaxH3Ref2VARequest(**data)

    def test_duration_is_aligned_to_official_frame_grid(self):
        self.assertEqual(minimax_frame_count(5), 124)
        self.assertEqual(minimax_frame_count(15), 362)

    def test_builds_dynamic_image_video_audio_nodes(self):
        request = self.request(
            images=["a", "b"],
            videos=["c"],
            audios=["d"],
        )
        workflow, seed, frames = build_minimax_workflow(
            request,
            ["one.png", "two.png"],
            ["clip.mp4"],
            ["voice.wav"],
        )
        inputs = workflow["136"]["inputs"]
        self.assertEqual(inputs["ref_images.ref_image_0"], ["1000", 0])
        self.assertEqual(inputs["ref_images.ref_image_1"], ["1001", 0])
        self.assertEqual(inputs["ref_videos.ref_video_0"], ["1200", 0])
        self.assertEqual(
            inputs["ref_video_audios.ref_video_audio_0"],
            ["1200", 1],
        )
        self.assertEqual(inputs["ref_audios.ref_audio_0"], ["1300", 0])
        self.assertEqual(workflow["1100"]["inputs"], {"file": "clip.mp4"})
        self.assertEqual(workflow["1200"]["class_type"], "GetVideoComponents")
        self.assertEqual((seed, frames), (42, 124))

    def test_selects_requested_models_and_fixed_vaes(self):
        request = self.request(
            diffusion_model="minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
            text_encoder="qwen3vl_32b_minimax_h3_bf16.safetensors",
        )
        workflow, _, _ = build_minimax_workflow(request, ["one.png"], [], [])
        self.assertEqual(workflow["127"]["inputs"]["unet_name"], request.diffusion_model)
        self.assertEqual(workflow["128"]["inputs"]["clip_name"], request.text_encoder)
        self.assertEqual(
            workflow["119"]["inputs"]["vae_name"],
            "minimax_h3_video_vae_fp16.safetensors",
        )
        self.assertEqual(
            workflow["120"]["inputs"]["vae_name"],
            "minimax_h3_audio_vae_fp32.safetensors",
        )

    def test_lora_switches_model_and_forces_four_steps(self):
        workflow, _, _ = build_minimax_workflow(
            self.request(enable_lora=True, steps=31),
            ["one.png"],
            [],
            [],
        )
        self.assertEqual(
            workflow["145"]["inputs"]["lora_name"],
            "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
        )
        self.assertEqual(workflow["124"]["inputs"]["model"], ["145", 0])
        self.assertEqual(workflow["126"]["inputs"]["model"], ["145", 0])
        self.assertEqual(workflow["124"]["inputs"]["steps"], 4)

    def test_full_mode_removes_lora_and_keeps_requested_steps(self):
        workflow, _, _ = build_minimax_workflow(
            self.request(enable_lora=False, steps=31),
            ["one.png"],
            [],
            [],
        )
        self.assertNotIn("145", workflow)
        self.assertEqual(workflow["124"]["inputs"]["model"], ["127", 0])
        self.assertEqual(workflow["126"]["inputs"]["model"], ["127", 0])
        self.assertEqual(workflow["124"]["inputs"]["steps"], 31)


class QwenWorkflowTest(unittest.TestCase):
    def test_qwen_image_uses_fixed_models_and_request_parameters(self):
        request = QwenImageRequest(
            prompt="A red boat",
            negative_prompt="blurry",
            width=1024,
            height=768,
            steps=37,
            cfg=3.5,
            seed=7,
        )
        workflow, seed = build_qwen_image_workflow(request)
        self.assertEqual(workflow["66"]["inputs"]["unet_name"], "qwen_image_2512_bf16.safetensors")
        self.assertEqual(workflow["62"]["inputs"]["clip_name"], "qwen_2.5_vl_7b_fp8_scaled.safetensors")
        self.assertEqual(workflow["63"]["inputs"]["vae_name"], "qwen_image_vae.safetensors")
        self.assertEqual(workflow["67"]["inputs"]["text"], "A red boat")
        self.assertEqual(workflow["68"]["inputs"]["width"], 1024)
        self.assertEqual(workflow["70"]["inputs"]["steps"], 37)
        self.assertEqual(seed, 7)
        self.assertNotIn("PreviewImage", {node["class_type"] for node in workflow.values()})
        self.assertNotIn("LoraLoaderModelOnly", {node["class_type"] for node in workflow.values()})

    def test_qwen_edit_builds_one_to_three_images_at_target_size(self):
        request = QwenImageEditRequest(
            images=["a", "b"],
            prompt="Use both references",
            width=1024,
            height=768,
            seed=9,
        )
        workflow, seed = build_qwen_edit_workflow(request, ["one.png", "two.png"])
        self.assertEqual(workflow["6"]["inputs"]["image"], "one.png")
        self.assertEqual(workflow["16"]["inputs"]["image"], "two.png")
        self.assertNotIn("17", workflow)
        self.assertNotIn("image3", workflow["8"]["inputs"])
        self.assertEqual(workflow["7"]["class_type"], "ImageScale")
        self.assertEqual(workflow["7"]["inputs"]["width"], 1024)
        self.assertEqual(workflow["7"]["inputs"]["height"], 768)
        self.assertEqual(workflow["13"]["inputs"]["seed"], 9)
        self.assertEqual(seed, 9)
        self.assertNotIn("LoraLoaderModelOnly", {node["class_type"] for node in workflow.values()})


if __name__ == "__main__":
    unittest.main()
