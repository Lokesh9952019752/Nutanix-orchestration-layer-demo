from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import EnvironmentKey

AddressMode = Literal["dhcp", "static"]


class EnvironmentIdentity(BaseModel):
    key: EnvironmentKey
    label: str
    base_url: str


class VMNic(BaseModel):
    subnet_uuid: str | None = None
    ip_address: str | None = None
    address_mode: AddressMode | str | None = None
    mac_address: str | None = None


class VMDisk(BaseModel):
    size_gib: float | None = None
    storage_container_uuid: str | None = None
    device_type: str | None = None


class VMSummary(BaseModel):
    uuid: str
    name: str
    power_state: str = "UNKNOWN"
    cpu_count: int | None = None
    memory_mib: int | None = None
    description: str | None = None


class VMDetail(VMSummary):
    cores_per_socket: int | None = None
    cluster_uuid: str | None = None
    nics: list[VMNic] = Field(default_factory=list)
    disks: list[VMDisk] = Field(default_factory=list)


class ConsoleLaunchInfo(BaseModel):
    vm_uuid: str
    url: str
    ticket: str | None = None
    iframe_allowed: bool = True


class PrismErrorDisplay(BaseModel):
    environment_key: str
    environment_label: str
    message: str
    status_code: int | None = None


class VMCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    cpu_count: int = Field(default=2, ge=1)
    cores_per_socket: int = Field(default=1, ge=1)
    memory_gib: float | None = Field(default=None, gt=0)
    memory_mib: int | None = Field(default=None, gt=0)
    disk_gib: float = Field(default=20, gt=0)
    image_uuid: str = Field(min_length=1)
    subnet_uuid: str = Field(min_length=1)
    cluster_uuid: str = Field(min_length=1)
    description: str | None = None
    static_ip: str | None = None
    address_mode: AddressMode = "dhcp"

    @field_validator("description", "static_ip", mode="before")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def normalize_memory(self) -> "VMCreateRequest":
        if self.memory_mib is None:
            gib = self.memory_gib if self.memory_gib is not None else 4
            self.memory_mib = int(gib * 1024)
        if self.address_mode == "static" and not self.static_ip:
            raise ValueError("static_ip is required when address_mode is static")
        return self
