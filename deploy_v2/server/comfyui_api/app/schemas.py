from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class QwenImageRequest(BaseModel):
    prompt: str = Field(min_length=1)
    negative_prompt: str = (
        "low resolution, low quality, bad anatomy, extra digits, "
        "missing digits, extra limbs, missing limbs"
    )
    width: int = Field(default=1328, ge=32, le=4096, multiple_of=32)
    height: int = Field(default=1328, ge=32, le=4096, multiple_of=32)
    steps: int = Field(default=50, ge=1, le=100)
    cfg: float = Field(default=4.0, ge=0)
    seed: int | None = Field(default=None, ge=0, lt=2**63)


class QwenImageEditRequest(BaseModel):
    images: list[str] = Field(min_length=1, max_length=3)
    prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    width: int = Field(default=1024, ge=32, le=4096, multiple_of=32)
    height: int = Field(default=1024, ge=32, le=4096, multiple_of=32)
    steps: int = Field(default=40, ge=1, le=100)
    cfg: float = Field(default=4.0, ge=0)
    seed: int | None = Field(default=None, ge=0, lt=2**63)


class MiniMaxH3Ref2VARequest(BaseModel):
    images: list[str] = Field(default_factory=list, max_length=9)
    videos: list[str] = Field(default_factory=list, max_length=3)
    audios: list[str] = Field(default_factory=list, max_length=3)
    prompt: str = Field(min_length=1)
    diffusion_model: DiffusionModel = (
        "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
    )
    text_encoder: TextEncoder = (
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
    )
    enable_lora: bool = False
    duration: float = Field(default=5.0, ge=5.0, le=15.0)
    width: int = Field(default=1344, ge=32, le=2048, multiple_of=32)
    height: int = Field(default=768, ge=32, le=2048, multiple_of=32)
    steps: int = Field(default=20, ge=1, le=100)
    seed: int | None = Field(default=None, ge=0, lt=2**63)

    @model_validator(mode="after")
    def require_reference(self):
        if not (self.images or self.videos or self.audios):
            raise ValueError("至少需要一个参考图片、视频或音频")
        return self

    def effective_steps(self) -> int:
        return 4 if self.enable_lora else self.steps
