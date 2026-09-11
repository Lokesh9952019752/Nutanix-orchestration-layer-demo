from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, PositiveInt


class EnvironmentInfo(BaseModel):
    key: str
    label: str
    base_url: str


class VMSize(BaseModel):
    vcpus: PositiveInt = Field(default=2, description="Number of vCPU sockets")
    cores_per_vcpu: PositiveInt = Field(default=1, description="Cores per vCPU socket")
    memory_mib: PositiveInt = Field(default=4096, description="Memory in MiB")


class VMDisk(BaseModel):
    size_mib: PositiveInt = Field(default=51200, description="Disk size in MiB")
    image_uuid: Optional[str] = Field(default=None, description="Optional disk image UUID")


class VMNic(BaseModel):
    network_uuid: str = Field(description="Target subnet/network UUID")


class VMCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = "Created by Prism FastAPI demo"
    cluster_uuid: str = Field(min_length=1)
    image_uuid: Optional[str] = None
    network_uuid: str = Field(min_length=1)
    vcpus: PositiveInt = 2
    cores_per_vcpu: PositiveInt = 1
    memory_mib: PositiveInt = 4096
    disk_size_mib: PositiveInt = 51200


class VMSummary(BaseModel):
    uuid: str
    name: str
    power_state: str = "UNKNOWN"
    environment: str
    description: Optional[str] = None
    ip_addresses: List[str] = Field(default_factory=list)


class VMDetail(VMSummary):
    cluster_name: Optional[str] = None
    num_vcpus: Optional[int] = None
    num_cores_per_vcpu: Optional[int] = None
    memory_mib: Optional[int] = None
    disks: List[Dict[str, Any]] = Field(default_factory=list)
    nics: List[Dict[str, Any]] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)


class TaskReference(BaseModel):
    uuid: str
    status: str = "submitted"
    message: Optional[str] = None


class ConsoleURL(BaseModel):
    vm_uuid: str
    url: HttpUrl | str
    ticket: Optional[str] = None
