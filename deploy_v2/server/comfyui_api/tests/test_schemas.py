import unittest

from pydantic import ValidationError

from app.schemas import MiniMaxH3Ref2VARequest, QwenImageEditRequest, QwenImageRequest


class MiniMaxH3SchemaTest(unittest.TestCase):
    def request(self, **changes):
        data = {
            "prompt": "Use <Picture 1> as the character reference.",
            "images": ["aW1hZ2U="],
        }
        data.update(changes)
        return MiniMaxH3Ref2VARequest(**data)

    def test_accepts_supported_model_choices(self):
        request = self.request(
            diffusion_model="minimax_h3_ref2va_int8_convrot.safetensors",
            text_encoder="qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
        )
        self.assertEqual(
            request.diffusion_model,
            "minimax_h3_ref2va_int8_convrot.safetensors",
        )

    def test_rejects_unknown_model(self):
        with self.assertRaises(ValidationError):
            self.request(diffusion_model="unknown.safetensors")

    def test_accepts_each_reference_kind_and_requires_one(self):
        self.request(images=[], videos=["dmlkZW8="])
        self.request(images=[], audios=["YXVkaW8="])
        with self.assertRaises(ValidationError):
            self.request(images=[], videos=[], audios=[])

    def test_enforces_official_reference_limits(self):
        with self.assertRaises(ValidationError):
            self.request(images=["a"] * 10)
        with self.assertRaises(ValidationError):
            self.request(videos=["a"] * 4)
        with self.assertRaises(ValidationError):
            self.request(audios=["a"] * 4)

    def test_lora_forces_four_steps_but_full_mode_keeps_requested_steps(self):
        self.assertEqual(self.request(enable_lora=True, steps=31).effective_steps(), 4)
        self.assertEqual(self.request(enable_lora=False, steps=31).effective_steps(), 31)
        self.assertEqual(self.request(enable_lora=False).effective_steps(), 20)

    def test_dimensions_must_be_multiples_of_32(self):
        with self.assertRaises(ValidationError):
            self.request(width=1000)
        self.request(width=1024, height=576)


class QwenSchemaTest(unittest.TestCase):
    def test_qwen_image_uses_official_full_quality_defaults(self):
        request = QwenImageRequest(prompt="A portrait")
        self.assertEqual((request.width, request.height), (1328, 1328))
        self.assertEqual((request.steps, request.cfg), (50, 4.0))

    def test_qwen_edit_accepts_one_to_three_images_and_target_size(self):
        request = QwenImageEditRequest(
            images=["one", "two", "three"],
            prompt="Combine the references",
            width=1024,
            height=768,
        )
        self.assertEqual(len(request.images), 3)
        self.assertEqual((request.width, request.height), (1024, 768))
        with self.assertRaises(ValidationError):
            QwenImageEditRequest(images=[], prompt="Edit")
        with self.assertRaises(ValidationError):
            QwenImageEditRequest(images=["x"] * 4, prompt="Edit")


if __name__ == "__main__":
    unittest.main()
