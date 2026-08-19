import argparse
import base64
from pathlib import Path

import requests


def image_base64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def request_and_save(url: str, payload: dict, result_key: str, output: str) -> None:
    response = requests.post(url, json=payload, timeout=None)
    response.raise_for_status()
    values = response.json().get(result_key, [])
    if not values:
        raise RuntimeError(f"服务端未返回 {result_key}")
    Path(output).write_bytes(base64.b64decode(values[0]))
    print(f"生成完成: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AIGC API 调用示例")
    parser.add_argument("command", choices=("text-to-image", "edit-image", "text-to-video", "image-to-video"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--input", help="图片编辑或图生视频的输入图片")
    parser.add_argument("--output")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    if args.command == "text-to-image":
        request_and_save(
            f"{base_url}/v1/images/qwen-image-2512/generate",
            {"prompt": args.prompt},
            "images",
            args.output or "qwen-image.png",
        )
    elif args.command == "edit-image":
        if not args.input:
            parser.error("edit-image 需要 --input")
        request_and_save(
            f"{base_url}/v1/images/qwen-image-edit-2511/edit",
            {"image": image_base64(args.input), "prompt": args.prompt},
            "images",
            args.output or "qwen-image-edit.png",
        )
    else:
        payload = {"prompt": args.prompt}
        if args.command == "image-to-video":
            if not args.input:
                parser.error("image-to-video 需要 --input")
            payload["image"] = image_base64(args.input)
        request_and_save(
            f"{base_url}/v1/videos/ltx_2d3_t2v_i2v_two_stage_distilled",
            payload,
            "videos",
            args.output or f"ltx-{args.command}.mp4",
        )


if __name__ == "__main__":
    main()
