# auth schema（M1/M4 对应任务实现；M6 上线就绪：改密）
from __future__ import annotations

from pydantic import BaseModel, Field


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)
