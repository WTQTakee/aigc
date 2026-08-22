import base64
import unittest
from types import SimpleNamespace

from app.main import generate
from app.schemas import MiniMaxH3Request


class FakeComfyUI:
    def __init__(self):
        self.kinds = []
        self.workflow = None

    async def upload_media(self, encoded, kind):
        self.kinds.append(kind)
        return f"{kind}-{len(self.kinds)}"

    async def run_workflow(self, workflow):
        self.workflow = workflow
        return [{"node_id": "92", "type": "video", "base64": "bXA0"}]


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_generate_uploads_all_media_and_returns_metadata(self):
        fake = FakeComfyUI()
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(comfyui=fake),
            )
        )
        body = MiniMaxH3Request(
            prompt="Use all references.",
            images=[base64.b64encode(b"image").decode()],
            videos=[base64.b64encode(b"video").decode()],
            audios=[base64.b64encode(b"audio").decode()],
            seed=42,
        )
        result = await generate(body, request)
        self.assertEqual(fake.kinds, ["image", "video", "audio"])
        self.assertEqual(result["videos"], ["bXA0"])
        self.assertEqual(result["frames"], 124)
        self.assertEqual(result["seed"], 42)
        self.assertEqual(result["input_count"], {
            "images": 1,
            "videos": 1,
            "audios": 1,
        })
