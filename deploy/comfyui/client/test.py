import argparse
import base64

import requests


BASE_URL = "http://127.0.0.1:8000"


def save_image(image_base64: str, output_path: str):
    image_bytes = base64.b64decode(image_base64)

    with open(output_path, "wb") as f:
        f.write(image_bytes)

    print(f"生成完成: {output_path}")


def test_qwen_image_2512():
    url = f"{BASE_URL}/v1/images/qwen-image-2512/generate"

    data = {
        "prompt": (
            "A cinematic portrait of a beautiful young woman "
            "standing in Tokyo at night"
        ),
        "width": 720,
        "height": 1280,
        "steps": 8,
        "cfg": 1,
    }

    response = requests.post(
        url,
        json=data,
        timeout=None,
    )

    response.raise_for_status()

    result = response.json()

    print("model:", result["model"])

    if not result["images"]:
        raise RuntimeError("没有获取到图片")

    save_image(
        result["images"][0],
        "qwen-image-2512.png",
    )


def test_qwen_image_edit_2511(input_path: str):
    with open(input_path, "rb") as f:
        image_base64 = base64.b64encode(
            f.read()
        ).decode("utf-8")

    url = f"{BASE_URL}/v1/images/qwen-image-edit-2511/edit"

    data = {
        "image": image_base64,
        "prompt": (
            "Change the background to a cinematic "
            "Tokyo street at night"
        ),
        "width": 864,
        "height": 1536,
        "steps": 4,
    }

    response = requests.post(
        url,
        json=data,
        timeout=None,
    )

    response.raise_for_status()

    result = response.json()

    print("model:", result["model"])

    if not result["images"]:
        raise RuntimeError("没有获取到图片")

    save_image(
        result["images"][0],
        "qwen-image-edit-2511.png",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "model",
        choices=[
            "qwen-image-2512",
            "qwen-image-edit-2511",
        ],
    )

    parser.add_argument(
        "--input",
        default="input.png",
        help="qwen-image-edit-2511 输入图片路径",
    )

    args = parser.parse_args()

    if args.model == "qwen-image-2512":
        test_qwen_image_2512()

    elif args.model == "qwen-image-edit-2511":
        test_qwen_image_edit_2511(args.input)