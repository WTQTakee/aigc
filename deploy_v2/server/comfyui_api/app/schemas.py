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
    width: int = Field(default=864, gt=0)
    height: int = Field(default=1536, gt=0)
    steps: int = Field(default=4, gt=0)
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
