"""
Standard instance-family reference table (Part 1, Telemetry Cost
Estimation Engine).

This is the deterministic reference the matching engine normalizes
telemetry against. Values are standard published AWS instance specs
(vCPU count and RAM in GB) - this is reference data, not invented.
Extend this table to widen instance-family coverage; the matching
engine only ever matches against entries actually present here AND in
the pricing catalog (Part 5 deterministic lookup table mirrors this).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstanceSpec:
    instance_type: str
    family: str
    vcpu: int
    ram_gb: float


# Standard EC2-family specs (vCPU, RAM GB) - published AWS specifications.
INSTANCE_SPECS: list[InstanceSpec] = [
    InstanceSpec("t3.nano", "t3", 2, 0.5),
    InstanceSpec("t3.micro", "t3", 2, 1.0),
    InstanceSpec("t3.small", "t3", 2, 2.0),
    InstanceSpec("t3.medium", "t3", 2, 4.0),
    InstanceSpec("t3.large", "t3", 2, 8.0),
    InstanceSpec("t3.xlarge", "t3", 4, 16.0),
    InstanceSpec("m5.large", "m5", 2, 8.0),
    InstanceSpec("m5.xlarge", "m5", 4, 16.0),
    InstanceSpec("m5.2xlarge", "m5", 8, 32.0),
    InstanceSpec("m5.4xlarge", "m5", 16, 64.0),
    InstanceSpec("c5.large", "c5", 2, 4.0),
    InstanceSpec("c5.xlarge", "c5", 4, 8.0),
    InstanceSpec("c5.2xlarge", "c5", 8, 16.0),
    InstanceSpec("c5.4xlarge", "c5", 16, 32.0),
    InstanceSpec("r4.large", "r4", 2, 15.25),
    InstanceSpec("r4.xlarge", "r4", 4, 30.5),
    InstanceSpec("r4.2xlarge", "r4", 8, 61.0),
    InstanceSpec("r4.4xlarge", "r4", 16, 122.0),
    InstanceSpec("r5.large", "r5", 2, 16.0),
    InstanceSpec("r5.xlarge", "r5", 4, 32.0),
    InstanceSpec("r5.2xlarge", "r5", 8, 64.0),
    InstanceSpec("r5.4xlarge", "r5", 16, 128.0),
    InstanceSpec("x1e.xlarge", "x1e", 4, 122.0),
    InstanceSpec("x1e.2xlarge", "x1e", 8, 244.0),
    InstanceSpec("z1d.xlarge", "z1d", 4, 32.0),
    InstanceSpec("z1d.2xlarge", "z1d", 8, 64.0),
    InstanceSpec("d2.xlarge", "d2", 4, 30.5),
    InstanceSpec("d2.2xlarge", "d2", 8, 61.0),
    InstanceSpec("d2.4xlarge", "d2", 16, 122.0),
    InstanceSpec("d2.8xlarge", "d2", 36, 244.0),
    InstanceSpec("db.t3.medium", "db.t3", 2, 4.0),
    InstanceSpec("db.m5.large", "db.m5", 2, 8.0),
    InstanceSpec("db.r5.large", "db.r5", 2, 16.0),
]

INSTANCE_SPEC_BY_TYPE: dict[str, InstanceSpec] = {s.instance_type: s for s in INSTANCE_SPECS}
