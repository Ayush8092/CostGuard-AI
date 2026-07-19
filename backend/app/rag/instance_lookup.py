"""
Deterministic instance lookup (Part 5) - SEPARATE from RAG.

This is an exact-key lookup: instance_type -> vCPU/RAM/hourly price.
It is NOT a retrieval or embedding system, and is intentionally kept
separate from faiss_store.py per spec ("Deterministic lookup (separate
from RAG): instance type -> vCPU/RAM/hourly price, exact-key JSON
lookup"). The Copilot and Advisor call this directly for hard facts
(specs, prices) and call the FAISS layer separately for best-practice
guidance/citations - the two are never conflated.
"""
from __future__ import annotations

from app.data.instance_specs import INSTANCE_SPEC_BY_TYPE


def lookup_instance(instance_type: str, pricing_catalog: dict[str, float] | None = None) -> dict | None:
    """
    Exact-key lookup. pricing_catalog, if given, maps instance_type ->
    hourly_rate (typically pre-fetched from the pricing_catalog DB table
    for a specific region/os). Returns None for an unknown instance type
    rather than guessing - callers should fall back to the fuzzy
    matching engine (telemetry_cost_engine.py) only when an exact lookup
    is insufficient, never silently here.
    """
    spec = INSTANCE_SPEC_BY_TYPE.get(instance_type)
    if spec is None:
        return None

    result = {
        "instance_type": spec.instance_type,
        "family": spec.family,
        "vcpu": spec.vcpu,
        "ram_gb": spec.ram_gb,
    }
    if pricing_catalog and instance_type in pricing_catalog:
        result["hourly_rate"] = pricing_catalog[instance_type]
    return result


if __name__ == "__main__":
    print(lookup_instance("m5.xlarge"))
    print(lookup_instance("c5.xlarge", pricing_catalog={"c5.xlarge": 0.1308}))
    print(lookup_instance("not-a-real-type"))
