import asyncio
import unittest
from types import SimpleNamespace

from app.main import edit_qwen_image, generate_minimax_h3, generate_qwen_image
from app.schemas import MiniMaxH3Ref2VARequest, QwenImageEditRequest, QwenImageRequest


class FakeComfyUI:
    def __init__(self, output_type: str):
        self.output_type = output_type
        self.uploaded = []

    async def upload_image(self, value):
        self.uploaded.append(("image", value))
        return f"image-{len(self.uploaded)}.png"

    async def upload_video(self, value):
        self.uploaded.append(("video", value))
        return f"video-{len(self.uploaded)}.mp4"

    async def upload_audio(self, value):
        self.uploaded.append(("audio", value))
        return f"audio-{len(self.uploaded)}.wav"

    async def run_workflow(self, workflow):
        node_id = "92" if self.output_type == "video" else "15"
        return [
            {
                "type": self.output_type,
                "filename": f"result.{self.output_type}",
                "node_id": node_id,
                "base64": "cmVzdWx0",
            }
        ]


def request_with(client):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(comfyui=client)))


class ApiTest(unittest.TestCase):
    def test_minimax_uploads_all_media_and_returns_effective_steps(self):
        async def run():
            comfyui = FakeComfyUI("video")
            body = MiniMaxH3Ref2VARequest(
                prompt="Use all references",
                images=["image"],
                videos=["video"],
                audios=["audio"],
                enable_lora=False,
                steps=31,
                seed=42,
            )
            result = await generate_minimax_h3(body, request_with(comfyui))
            self.assertEqual(
                [kind for kind, _ in comfyui.uploaded],
                ["image", "video", "audio"],
            )
            self.assertEqual(result["steps"], 31)
            self.assertEqual(result["seed"], 42)
            self.assertEqual(result["videos"], ["cmVzdWx0"])

        asyncio.run(run())

    def test_qwen_endpoints_return_seed_and_images(self):
        async def run():
            generate_client = FakeComfyUI("image")
            generated = await generate_qwen_image(
                QwenImageRequest(prompt="A portrait", seed=5),
                request_with(generate_client),
            )
            self.assertEqual(generated["seed"], 5)
            self.assertEqual(generated["images"], ["cmVzdWx0"])

            edit_client = FakeComfyUI("image")
            edited = await edit_qwen_image(
                QwenImageEditRequest(images=["one", "two"], prompt="Edit", seed=6),
                request_with(edit_client),
            )
            self.assertEqual(len(edit_client.uploaded), 2)
            self.assertEqual(edited["input_count"], 2)
            self.assertEqual(edited["seed"], 6)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
