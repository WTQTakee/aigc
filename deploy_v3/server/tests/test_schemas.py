import unittest

from pydantic import ValidationError

from app.schemas import MiniMaxH3Request


class MiniMaxH3RequestTest(unittest.TestCase):
    def valid(self, **changes):
        data = {
            "prompt": "Use <Picture 1> as the character reference.",
            "images": ["aW1hZ2U="],
            "diffusion_model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            "text_encoder": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        }
        data.update(changes)
        return MiniMaxH3Request(**data)

    def test_accepts_each_supported_model(self):
        self.valid(diffusion_model="minimax_h3_ref2va_bf16.safetensors")
        self.valid(text_encoder="qwen3vl_32b_minimax_h3_bf16.safetensors")

    def test_rejects_unknown_model(self):
        with self.assertRaises(ValidationError):
            self.valid(diffusion_model="other.safetensors")

    def test_requires_at_least_one_reference(self):
        with self.assertRaises(ValidationError):
            self.valid(images=[], videos=[], audios=[])

    def test_enforces_reference_limits(self):
        with self.assertRaises(ValidationError):
            self.valid(images=["a"] * 10)
        with self.assertRaises(ValidationError):
            self.valid(videos=["a"] * 4)
        with self.assertRaises(ValidationError):
            self.valid(audios=["a"] * 4)

    def test_enforces_canvas_constraints(self):
        with self.assertRaises(ValidationError):
            self.valid(width=1000)
        with self.assertRaises(ValidationError):
            self.valid(width=1344, height=800)

    def test_lora_forces_four_steps(self):
        self.assertEqual(
            self.valid(enable_lora=True, steps=20).effective_steps(),
            4,
        )
        self.assertEqual(
            self.valid(enable_lora=False, steps=18).effective_steps(),
            18,
        )
