import argparse
import base64

import requests


BASE_URL = "http://127.0.0.1:8000"


def save_video(video_base64: str, output_path: str):
    video_bytes = base64.b64decode(video_base64)

    with open(output_path, "wb") as f:
        f.write(video_bytes)

    print(f"视频生成完成: {output_path}")


def test_t2v():
    url = f"{BASE_URL}/v1/videos/ltx-2.3/generate"

    data = {
        "prompt": (
            "A cinematic shot of a young woman walking "
            "through Tokyo at night. Neon lights reflect "
            "on the wet street. The camera slowly follows "
            "her from behind."
        ),
        "width": 960,
        "height": 544,
        "frames": 121,
        "fps": 24,
    }

    response = requests.post(
        url,
        json=data,
        timeout=None,
    )

    if not response.ok:
        print("状态码:", response.status_code)
        print("服务端返回:", response.text)
        raise RuntimeError("LTX-2.3 请求失败")

    result = response.json()

    print("model:", result["model"])

    if not result["videos"]:
        raise RuntimeError("没有获取到视频")

    save_video(
        result["videos"][0],
        "ltx-2.3-t2v.mp4",
    )


def test_i2v(input_path: str):
    with open(input_path, "rb") as f:
        image_base64 = base64.b64encode(
            f.read()
        ).decode("utf-8")

    url = f"{BASE_URL}/v1/videos/ltx-2.3/generate"

    data = {
        "image": image_base64,
        "prompt": (
            "The woman slowly walks forward. "
            "Her hair moves gently in the wind. "
            "The camera slowly pushes in. "
            "Cinematic lighting and natural motion."
        ),
        "width": 960,
        "height": 544,
        "frames": 121,
        "fps": 24,
    }

    response = requests.post(
        url,
        json=data,
        timeout=None,
    )

    response.raise_for_status()

    result = response.json()

    print("model:", result["model"])

    if not result["videos"]:
        raise RuntimeError("没有获取到视频")

    save_video(
        result["videos"][0],
        "ltx-2.3-i2v.mp4",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "mode",
        choices=[
            "t2v",
            "i2v",
        ],
    )

    parser.add_argument(
        "--input",
        default="input.png",
        help="LTX-2.3 I2V 输入图片路径",
    )

    args = parser.parse_args()

    if args.mode == "t2v":
        test_t2v()

    elif args.mode == "i2v":
        test_i2v(args.input)
