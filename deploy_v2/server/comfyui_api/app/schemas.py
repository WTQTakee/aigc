from typing import Literal

from pydantic import BaseModel, Field


class QwenImageRequest(BaseModel):
    prompt: str
    negative_prompt: str = (
        "low quality, bad anatomy, extra digits, missing digits, "
        "extra limbs, missing limbs"
    )
    width: int = Field(default=720, gt=0)
    height: int = Field(default=1280, gt=0)
    steps: int = Field(default=8, gt=0)
    cfg: float = Field(default=1.0, ge=0)
    seed: int | None = None


class QwenImageEditRequest(BaseModel):
    image: str
    prompt: str
    negative_prompt: str = ""
    steps: int = Field(default=40, gt=0)
    cfg: float = Field(default=4.0, ge=0)
    seed: int | None = None


class QwenImageEditLightningRequest(BaseModel):
    image: str
    prompt: str
    width: int = Field(default=864, gt=0)
    height: int = Field(default=1536, gt=0)
    seed: int | None = None


class QwenImageMultiEditRequest(BaseModel):
    images: list[str] = Field(min_length=1, max_length=3)
    prompt: str
    negative_prompt: str = ""
    steps: int = Field(default=40, gt=0)
    cfg: float = Field(default=4.0, ge=0)
    seed: int | None = None


class QwenImageMultiEditLightningRequest(BaseModel):
    images: list[str] = Field(min_length=1, max_length=3)
    prompt: str
    width: int = Field(default=864, gt=0)
    height: int = Field(default=1536, gt=0)
    seed: int | None = None


class LTXVideoRequest(BaseModel):
    prompt: str
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    image: str | None = None
    width: int = Field(default=960, gt=0)
    height: int = Field(default=544, gt=0)
    frames: int = Field(default=121, gt=0)
    fps: float = Field(default=24, gt=0)
    seed: int | None = None


class LTXAudioRequest(BaseModel):
    prompt: str
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    frames: int = Field(default=161, gt=0)
    fps: float = Field(default=24, gt=0)
    seed: int | None = None


class LTXHDRRequest(BaseModel):
    video: str
    prompt: str = "HDR footage"
    negative_prompt: str = (
        "pc game, console game, video game, ugly, still, static, slow"
    )
    exposure: float = 7.1
    save_exr: bool = True
    seed: int | None = None


class LTXIngredientsRequest(BaseModel):
    image: str
    prompt: str
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    frames: int = Field(default=241, gt=0)
    fps: float = Field(default=24, gt=0)
    seed: int | None = None


class LTXInpaintRequest(BaseModel):
    video: str
    mask_video: str
    prompt: str = ""
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    mask_dilation: int = Field(default=15, ge=0)
    seed: int | None = None


class LTXLipdubRequest(BaseModel):
    video: str
    prompt: str
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    seed: int | None = None


class LTXTrackPoint(BaseModel):
    x: float
    y: float


class LTXMotionTrackRequest(BaseModel):
    image: str
    prompt: str
    tracks: list[list[LTXTrackPoint]] = Field(min_length=1)
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    frames: int = Field(default=121, gt=1)
    fps: float = Field(default=24, gt=0)
    seed: int | None = None


class LTXOutpaintRequest(BaseModel):
    video: str
    prompt: str = ""
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1088, gt=0)
    seed: int | None = None


class LTXPixelUpscaleRequest(BaseModel):
    video: str
    prompt: str
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    seed: int | None = None


class LTXUnionControlRequest(BaseModel):
    video: str
    prompt: str
    control: Literal["canny", "depth", "pose"] = "canny"
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    seed: int | None = None


class LTXVideoToVideoRequest(BaseModel):
    video: str
    prompt: str
    negative_prompt: str = (
        "pc game, console game, video game, cartoon, childish, ugly"
    )
    seed: int | None = None


class MiniMaxH3Ref2VARequest(BaseModel):
    images: list[str] = Field(min_length=1, max_length=9)
    prompt: str = Field(min_length=1)
    width: int = Field(default=1344, ge=32, le=1344, multiple_of=32)
    height: int = Field(default=768, ge=32, le=1344, multiple_of=32)
    duration: float = Field(default=5.0, ge=5.0, le=15.0)
    steps: int = Field(default=20, ge=1, le=100)
    scheduler: Literal["simple", "normal", "beta"] = "simple"
    ref_image_size: Literal["match", "max"] = "match"
    seed: int | None = Field(default=None, ge=0, lt=2**63)
