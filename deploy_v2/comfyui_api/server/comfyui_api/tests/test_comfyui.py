import asyncio
import base64
import unittest

import httpx

from app.comfyui import ComfyUIClient


class ComfyUIClientTest(unittest.TestCase):
    def test_upload_audio_accepts_data_url(self):
        async def run():
            async def handler(request):
                self.assertEqual(request.url.path, "/upload/image")
                self.assertIn("multipart/form-data", request.headers["content-type"])
                return httpx.Response(200, json={"name": "voice.wav"})

            client = ComfyUIClient("http://comfy")
            await client.http.aclose()
            client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            value = "data:audio/wav;base64," + base64.b64encode(b"audio").decode()
            self.assertEqual(await client.upload_audio(value), "voice.wav")
            await client.close()

        asyncio.run(run())

    def test_upload_rejects_invalid_base64(self):
        async def run():
            client = ComfyUIClient("http://comfy")
            with self.assertRaisesRegex(ValueError, "Base64"):
                await client.upload_video("not-base64")
            await client.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
