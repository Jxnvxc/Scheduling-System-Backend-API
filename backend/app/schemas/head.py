from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ManagerBranchAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: int = Field(gt=0)


class HeadManagerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    manager_id: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+$")
    password: str = Field(min_length=8)
    branch_id: int = Field(gt=0)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name cannot be blank.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 bytes.")
        return value


class HeadManagerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    manager_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        pattern=r"^[0-9]+$",
    )
    branch_id: int | None = Field(default=None, gt=0)
    password: str | None = Field(default=None, min_length=8)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name cannot be blank.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_byte_length(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no more than 72 bytes.")
        return value

    @model_validator(mode="after")
    def require_editable_fields(self) -> "HeadManagerUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one manager setting must be provided.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Edited manager settings cannot be null.")
        return self
