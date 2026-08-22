from typing import Literal

from pydantic import BaseModel, Field, model_validator


DIFFUSION_MODELS = (
    "minimax_h3_ref2va_bf16.safetensors",
    "minimax_h3_ref2va_int8_convrot.safetensors",
    "minimax_h3_ref2va_pruned_bf16.safetensors",
    "minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
    "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
)
TEXT_ENCODERS = (
    "qwen3vl_32b_minimax_h3_bf16.safetensors",
    "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
)

DiffusionModel = Literal[
    "minimax_h3_ref2va_bf16.safetensors",
    "minimax_h3_ref2va_int8_convrot.safetensors",
    "minimax_h3_ref2va_pruned_bf16.safetensors",
    "minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
    "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
]
TextEncoder = Literal[
    "qwen3vl_32b_minimax_h3_bf16.safetensors",
    "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
]

DEFAULT_DIFFUSION_MODEL: DiffusionModel = (
    "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
)
DEFAULT_TEXT_ENCODER: TextEncoder = (
    "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
)
MAX_CANVAS_PIXELS = 768 * 1344


class MiniMaxH3Request(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=9)
    videos: list[str] = Field(default_factory=list, max_length=3)
    audios: list[str] = Field(default_factory=list, max_length=3)
    prompt: str = Field(min_length=1)
    diffusion_model: DiffusionModel = DEFAULT_DIFFUSION_MODEL
    text_encoder: TextEncoder = DEFAULT_TEXT_ENCODER
    enable_lora: bool = False
    duration: float = Field(default=5.0, ge=5.0, le=15.0)
    width: int = Field(default=1344, ge=32, multiple_of=32)
    height: int = Field(default=768, ge=32, multiple_of=32)
    seed: int | None = Field(default=None, ge=0, lt=2**63)
    steps: int = Field(default=20, ge=1, le=100)
    scheduler: Literal["simple", "normal", "beta"] = "simple"
    ref_image_size: Literal["match", "max"] = "match"

    @model_validator(mode="after")
    def validate_references_and_canvas(self):
        if not (self.images or self.videos or self.audios):
            raise ValueError("至少需要一个参考图片、视频或音频")
        if self.width * self.height > MAX_CANVAS_PIXELS:
            raise ValueError("输出总像素不能超过 768 * 1344")
        return self

    def effective_steps(self) -> int:
        return 4 if self.enable_lora else self.steps
