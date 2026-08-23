import argparse
import base64
from pathlib import Path

import requests


def file_base64(path: str) -> str:
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
    parser.add_argument("command", choices=("qwen-generate", "qwen-edit", "minimax-h3"))
    parser.add_argument(
        "--base-url",
        default="https://u743245-6dat-d16e8d25.bjb1.seetacloud.com:8443",
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--video", action="append", default=[])
    parser.add_argument("--audio", action="append", default=[])
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--enable-lora", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    common = {"prompt": args.prompt}
    for name in ("width", "height", "steps", "seed"):
        value = getattr(args, name)
        if value is not None:
            common[name] = value

    if args.command == "qwen-generate":
        request_and_save(
            f"{base_url}/v1/images/qwen-image-2512/generate",
            common,
            "images",
            args.output or "qwen-image.png",
        )
    elif args.command == "qwen-edit":
        if not args.image:
            parser.error("qwen-edit 至少需要一个 --image")
        common["images"] = [file_base64(path) for path in args.image]
        request_and_save(
            f"{base_url}/v1/images/qwen-image-edit-2511/edit",
            common,
            "images",
            args.output or "qwen-image-edit.png",
        )
    else:
        if not (args.image or args.video or args.audio):
            parser.error("minimax-h3 至少需要一个参考媒体")
        common.update(
            images=[file_base64(path) for path in args.image],
            videos=[file_base64(path) for path in args.video],
            audios=[file_base64(path) for path in args.audio],
            enable_lora=args.enable_lora,
        )
        request_and_save(
            f"{base_url}/v1/videos/minimax-h3-ref2va/generate",
            common,
            "videos",
            args.output or "minimax-h3.mp4",
        )


if __name__ == "__main__":
    main()
