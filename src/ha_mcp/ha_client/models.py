"""Pydantic models representing Home Assistant data structures."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HADevice(BaseModel):
    id: str
    name: str | None = None
    name_by_user: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    model_id: str | None = None
    area_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    disabled_by: str | None = None

    @property
    def display_name(self) -> str:
        return self.name_by_user or self.name or self.id


class HAEntity(BaseModel):
    entity_id: str
    name: str | None = None
    original_name: str | None = None
    platform: str | None = None
    device_id: str | None = None
    area_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    disabled_by: str | None = None
    hidden_by: str | None = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".")[0]

    @property
    def display_name(self) -> str:
        return self.name or self.original_name or self.entity_id


class HAState(BaseModel):
    entity_id: str
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_changed: str | None = None
    last_updated: str | None = None

    @property
    def friendly_name(self) -> str:
        return self.attributes.get("friendly_name", self.entity_id)


class HAArea(BaseModel):
    area_id: str
    name: str
    floor_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    icon: str | None = None


class HAFloor(BaseModel):
    floor_id: str
    name: str
    level: int | None = None
    icon: str | None = None


class HALabel(BaseModel):
    label_id: str
    name: str
    color: str | None = None
    icon: str | None = None
    description: str | None = None


class HAAutomation(BaseModel):
    id: str
    alias: str | None = None
    description: str | None = None
    triggers: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "single"


class HAScript(BaseModel):
    id: str
    alias: str | None = None
    description: str | None = None
    sequence: list[dict[str, Any]] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)
    mode: str = "single"


class HAScene(BaseModel):
    id: str
    name: str | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None


class HAServiceField(BaseModel):
    name: str | None = None
    description: str | None = None
    required: bool = False
    selector: dict[str, Any] | None = None


class HAService(BaseModel):
    domain: str
    service: str
    name: str | None = None
    description: str | None = None
    fields: dict[str, HAServiceField] = Field(default_factory=dict)


class HAValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# Custom exceptions


class HAError(Exception):
    """Base exception for HA client errors."""


class HAConnectionError(HAError):
    """Failed to connect to Home Assistant."""


class HAAuthError(HAError):
    """Authentication failed."""


class HANotFoundError(HAError):
    """Requested resource not found."""


class HAValidationError(HAError):
    """Configuration validation failed."""


class HAConnectionLost(HAError):
    """WebSocket connection was lost."""
