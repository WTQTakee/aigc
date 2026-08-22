import asyncio
import base64
import unittest

import httpx

from app.comfyui import ComfyUIClient


class ComfyUIClientTest(unittest.TestCase):
    def test_upload_media_accepts_data_url(self):
        async def run():
            async def handler(request):
                self.assertEqual(request.url.path, "/upload/image")
                self.assertIn("multipart/form-data", request.headers["content-type"])
                return httpx.Response(200, json={"name": "uploaded.png"})

            client = ComfyUIClient("http://comfy")
            await client.http.aclose()
            client.http = httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
            )
            encoded = "data:image/png;base64," + base64.b64encode(
                b"image"
            ).decode()
            self.assertEqual(
                await client.upload_media(encoded, "image"),
                "uploaded.png",
            )
            await client.close()

        asyncio.run(run())

    def test_upload_media_rejects_invalid_base64(self):
        async def run():
            client = ComfyUIClient("http://comfy")
            with self.assertRaisesRegex(ValueError, "Base64"):
                await client.upload_media("not-base64", "image")
            await client.close()

        asyncio.run(run())

    def test_run_workflow_returns_downloaded_video(self):
        async def run():
            history_calls = 0

            async def handler(request):
                nonlocal history_calls
                if request.url.path == "/prompt":
                    return httpx.Response(200, json={"prompt_id": "job-1"})
                if request.url.path == "/history/job-1":
                    history_calls += 1
                    return httpx.Response(
                        200,
                        json={
                            "job-1": {
                                "status": {"status_str": "success"},
                                "outputs": {
                                    "92": {
                                        "videos": [
                                            {
                                                "filename": "out.mp4",
                                                "subfolder": "video",
                                                "type": "output",
                                            }
                                        ]
                                    }
                                },
                            }
                        },
                    )
                if request.url.path == "/view":
                    return httpx.Response(200, content=b"mp4")
                return httpx.Response(404)

            client = ComfyUIClient("http://comfy", poll_interval=0)
            await client.http.aclose()
            client.http = httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
            )
            files = await client.run_workflow({"92": {}})
            self.assertEqual(history_calls, 1)
            self.assertEqual(files[0]["node_id"], "92")
            self.assertEqual(files[0]["type"], "video")
            self.assertEqual(files[0]["base64"], "bXA0")
            await client.close()

        asyncio.run(run())
