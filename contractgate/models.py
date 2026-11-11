"""Small explicit contract dialect; unsupported keys are errors, not ignored."""

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["string", "integer", "decimal", "date"] = "string"
    nullable: bool = False
    unique: bool = False
    min: Decimal | None = None
    max: Decimal | None = None
    allowed: list[str] | None = Field(default=None, max_length=1000)
    pattern: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def valid_constraints(self):
        if self.min is not None or self.max is not None:
            if self.type not in ("integer", "decimal"):
                raise ValueError("min/max require a numeric type")
            if any(v is not None and not v.is_finite() for v in (self.min, self.max)):
                raise ValueError("min/max must be finite")
            if self.min is not None and self.max is not None and self.min > self.max:
                raise ValueError("min cannot exceed max")
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise ValueError("invalid regular expression") from error
        return self


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    columns: dict[str, Column] = Field(min_length=1, max_length=100)
    allow_extra_columns: bool = False
    min_rows: int = Field(default=1, ge=0, le=100000)
    max_rows: int = Field(default=100000, ge=0, le=100000)

    @model_validator(mode="after")
    def valid_contract(self):
        if self.min_rows > self.max_rows:
            raise ValueError("min_rows cannot exceed max_rows")
        if any(not name.strip() or len(name) > 100 for name in self.columns):
            raise ValueError("column names must be nonblank and at most 100 characters")
        return self
