"""
Curated RAG knowledge corpus (Part 5).

These are HAND-SUMMARIZED chunks - paraphrased guidance drawn from
publicly known AWS Well-Architected Cost Optimization pillar concepts,
FinOps Foundation best practices, and Trusted Advisor rule patterns.
This is NOT a scrape of any document and contains no verbatim quoted
text from any source; each entry is an original, short restatement of
a well-known best practice, written specifically for this project's
retrieval layer. 50-100 chunks per spec - this file holds the curated
set actually embedded into FAISS by rag/knowledge_base.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    category: str  # well_architected | finops_foundation | trusted_advisor | pricing_reference
    title: str
    content: str


KNOWLEDGE_CHUNKS: list[KnowledgeChunk] = [
    # --- AWS Well-Architected Cost Optimization pillar ---
    KnowledgeChunk("wa_001", "well_architected", "Right-sizing instances",
        "Match instance types and sizes to actual workload requirements rather than over-provisioning for peak "
        "scenarios that rarely occur. Continuously monitor utilization and resize or change instance family when "
        "actual CPU/memory usage is consistently far below the provisioned capacity."),
    KnowledgeChunk("wa_002", "well_architected", "Elasticity over fixed capacity",
        "Use auto scaling and on-demand provisioning so capacity expands and contracts with real demand, instead "
        "of running fixed-size fleets sized for worst-case load around the clock."),
    KnowledgeChunk("wa_003", "well_architected", "Pricing model selection",
        "Choose the pricing model that matches workload predictability: steady-state workloads benefit from "
        "reserved or savings-plan commitments, spiky or interruptible workloads benefit from spot capacity, and "
        "unpredictable short-lived workloads are often cheapest on-demand or serverless."),
    KnowledgeChunk("wa_004", "well_architected", "Eliminating idle resources",
        "Resources with consistently low utilization over an extended window (commonly two weeks or more) are "
        "strong termination or downsizing candidates. Idle-but-billed resources are one of the most common and "
        "easiest-to-fix sources of cloud waste."),
    KnowledgeChunk("wa_005", "well_architected", "Storage tiering",
        "Move infrequently accessed data to cheaper storage tiers automatically using lifecycle policies, rather "
        "than leaving all data on the highest-performance, highest-cost storage class indefinitely."),
    KnowledgeChunk("wa_006", "well_architected", "Managed services reduce operational cost",
        "Where workload fit allows, managed database, queueing, and compute services can reduce total cost of "
        "ownership by removing the operational overhead of self-managing the underlying infrastructure."),
    KnowledgeChunk("wa_007", "well_architected", "Measuring overall efficiency",
        "Track cost per business outcome (e.g., cost per transaction or cost per active user) in addition to "
        "absolute spend, so cost trends are evaluated against the value they are delivering."),
    KnowledgeChunk("wa_008", "well_architected", "Decommissioning unused resources",
        "Regularly audit and decommission unattached storage volumes, idle load balancers, unused snapshots, and "
        "orphaned IP addresses - these accumulate quietly and rarely show up in headline cost dashboards."),
    KnowledgeChunk("wa_009", "well_architected", "Data transfer cost awareness",
        "Cross-region and cross-AZ data transfer can be a significant and easily overlooked cost driver; "
        "co-locating tightly coupled services in the same AZ reduces this overhead."),
    KnowledgeChunk("wa_010", "well_architected", "Continuous cost review cadence",
        "Cost optimization is not a one-time project - establishing a recurring review cadence (weekly or "
        "monthly) catches drift and regressions before they compound into large unnecessary spend."),

    # --- FinOps Foundation best practices ---
    KnowledgeChunk("finops_001", "finops_foundation", "Inform, Optimize, Operate phases",
        "FinOps maturity is commonly described in three phases: Inform (gain visibility into spend and "
        "allocation), Optimize (act on waste and rate opportunities), and Operate (embed continuous cost "
        "governance into engineering and business processes)."),
    KnowledgeChunk("finops_002", "finops_foundation", "Showback and chargeback",
        "Allocating cloud cost back to the teams or business units that incurred it (showback for visibility, "
        "chargeback for actual billing) creates accountability and drives more cost-conscious engineering decisions."),
    KnowledgeChunk("finops_003", "finops_foundation", "Unit economics",
        "Tracking cost per unit of business value (per customer, per request, per GB processed) makes cost trends "
        "meaningful to non-engineering stakeholders and ties cloud spend directly to business growth."),
    KnowledgeChunk("finops_004", "finops_foundation", "Anomaly response process",
        "A mature FinOps practice has a defined process for triaging cost anomalies quickly - who gets alerted, "
        "how fast it must be investigated, and what the rollback or mitigation steps are - rather than discovering "
        "spikes only at month-end billing review."),
    KnowledgeChunk("finops_005", "finops_foundation", "Forecasting accuracy as a KPI",
        "Forecast accuracy (commonly measured via MAPE against actuals) is itself a FinOps KPI - a forecasting "
        "process that is consistently off by a large margin undermines budget planning and commitment purchasing "
        "decisions."),
    KnowledgeChunk("finops_006", "finops_foundation", "Tagging and allocation hygiene",
        "Consistent resource tagging (by team, environment, project) is the foundation that makes every other "
        "FinOps practice - showback, chargeback, unit economics, anomaly attribution - possible at all."),
    KnowledgeChunk("finops_007", "finops_foundation", "Balancing commitment-based discounts",
        "Reserved capacity and savings plans offer meaningful discounts in exchange for usage commitment, but "
        "over-committing relative to actual future usage can itself become a source of waste; commitment levels "
        "should be sized against a rolling baseline of confirmed steady-state usage."),
    KnowledgeChunk("finops_008", "finops_foundation", "Cross-functional ownership",
        "Effective cost optimization requires collaboration between finance, engineering, and product - "
        "engineering controls the technical levers, finance understands the budget context, and product "
        "understands which workloads justify their cost."),

    # --- Trusted Advisor style rule patterns ---
    KnowledgeChunk("ta_001", "trusted_advisor", "Low utilization EC2 instances",
        "Instances with average CPU utilization below roughly 10% over a 14-day period are commonly flagged as "
        "low-utilization candidates for downsizing or termination."),
    KnowledgeChunk("ta_002", "trusted_advisor", "Idle load balancers",
        "A load balancer with no healthy backend targets or near-zero request volume over an extended period is "
        "a strong candidate for removal, since it continues to incur cost without serving meaningful traffic."),
    KnowledgeChunk("ta_003", "trusted_advisor", "Underutilized EBS volumes",
        "Storage volumes attached to an instance but with consistently low read/write activity, or volumes not "
        "attached to any instance at all, are common targets for resizing, snapshot-and-delete, or removal."),
    KnowledgeChunk("ta_004", "trusted_advisor", "Unassociated Elastic IPs",
        "Elastic IP addresses that are allocated but not associated with a running instance continue to accrue "
        "charges and should be released if no longer needed."),
    KnowledgeChunk("ta_005", "trusted_advisor", "RDS instances with low connection counts",
        "A database instance with near-zero connection activity over a sustained window may be a decommissioned "
        "or forgotten environment and is worth confirming before continued billing."),
    KnowledgeChunk("ta_006", "trusted_advisor", "Underutilized reserved capacity",
        "If purchased reserved instances or savings plan commitments are not being fully consumed by current "
        "usage, that gap represents wasted commitment spend and should inform the next purchasing cycle."),
    KnowledgeChunk("ta_007", "trusted_advisor", "Old generation instance types",
        "Workloads still running on older-generation instance families often cost more per unit of performance "
        "than the current generation equivalent; migrating can reduce cost without reducing capability."),

    # --- AWS pricing reference notes (general, not a price list) ---
    KnowledgeChunk("pricing_001", "pricing_reference", "On-demand vs spot pricing",
        "On-demand pricing offers no commitment and the highest per-hour rate; spot pricing offers a significant "
        "discount in exchange for the possibility of interruption, making it well suited to fault-tolerant, "
        "flexible, or batch workloads rather than stateful production services."),
    KnowledgeChunk("pricing_002", "pricing_reference", "Pricing varies by region",
        "The same instance type can have meaningfully different hourly rates across regions; workloads without a "
        "strict latency or data-residency requirement may find real savings by relocating to a lower-cost region."),
    KnowledgeChunk("pricing_003", "pricing_reference", "Storage and compute are priced independently",
        "Compute (instance hours) and storage (provisioned or consumed capacity) are billed on separate meters; "
        "a workload can look cheap on compute while storage or data transfer quietly dominates the total bill."),
    KnowledgeChunk("pricing_004", "pricing_reference", "Operating system licensing affects price",
        "Instances running licensed operating systems (e.g., Windows, certain Linux distributions with paid "
        "support) carry a higher hourly rate than the equivalent open-source Linux instance of the same size."),

    # --- additional Well-Architected / FinOps chunks to round out the curated set ---
    KnowledgeChunk("wa_011", "well_architected", "Serverless for spiky workloads",
        "Workloads with highly variable or unpredictable traffic patterns often cost less on serverless compute, "
        "which bills per invocation/duration, than on a fleet of always-on instances sized for peak load."),
    KnowledgeChunk("wa_012", "well_architected", "Multi-account cost visibility",
        "Splitting workloads across separate accounts (e.g., by environment or team) improves cost visibility and "
        "blast-radius isolation, but requires a consolidated billing and tagging strategy to avoid losing the "
        "organization-wide cost picture."),
    KnowledgeChunk("finops_009", "finops_foundation", "Budget alerts as a guardrail",
        "Proactive budget alerts (warning at a percentage of monthly budget consumed) catch runaway spend earlier "
        "than a reactive month-end invoice review."),
    KnowledgeChunk("finops_010", "finops_foundation", "Avoiding optimization theater",
        "Optimization actions should be tied to a measurable savings estimate and tracked against actual realized "
        "savings after the change - otherwise a long list of 'recommendations applied' can look like progress "
        "without ever showing up in the actual bill."),
    KnowledgeChunk("ta_008", "trusted_advisor", "Snapshot accumulation",
        "Automated backup snapshots that are never pruned accumulate storage cost over time even after the source "
        "volume or database has been deleted; a retention policy should cap how long snapshots are kept."),

    # --- additional Well-Architected chunks ---
    KnowledgeChunk("wa_013", "well_architected", "Graviton and architecture choice",
        "ARM-based instance architectures frequently offer better price-performance than equivalent x86 instances "
        "for compatible workloads, and migrating compatible services can reduce compute cost without changing "
        "instance size."),
    KnowledgeChunk("wa_014", "well_architected", "Container density and bin-packing",
        "Running multiple containerized workloads on shared underlying instances, rather than one workload per "
        "dedicated instance, improves resource utilization and reduces the number of idle CPU/memory cycles being "
        "paid for."),
    KnowledgeChunk("wa_015", "well_architected", "Scheduled shutdown for non-production",
        "Development, test, and staging environments that are only needed during business hours can be "
        "automatically stopped outside those hours, which can cut their compute cost substantially with no "
        "production impact."),
    KnowledgeChunk("wa_016", "well_architected", "Caching to reduce compute and data transfer",
        "Introducing a caching layer for frequently accessed data reduces redundant compute work and repeated data "
        "transfer, lowering cost on both fronts simultaneously."),
    KnowledgeChunk("wa_017", "well_architected", "Database read replica right-sizing",
        "Read replicas should be sized and counted based on actual read traffic, not provisioned defensively; "
        "over-provisioned replica fleets are a common and easily overlooked source of database cost waste."),
    KnowledgeChunk("wa_018", "well_architected", "Burstable instance families",
        "Burstable instance families are well suited to workloads with low average utilization and occasional "
        "short bursts, but sustained high utilization on a burstable instance can be more expensive than a "
        "standard instance sized for that sustained load."),
    KnowledgeChunk("wa_019", "well_architected", "Avoiding premature over-provisioning",
        "Provisioning for projected future growth far in advance of actual demand ties up budget in capacity that "
        "sits idle; incremental scaling aligned with observed growth is typically more cost efficient."),
    KnowledgeChunk("wa_020", "well_architected", "Compute Savings Plans flexibility",
        "Compute-focused savings plans apply across instance families and regions, offering more flexibility than "
        "instance-specific reservations, which suits organizations whose workload mix changes over time."),
    KnowledgeChunk("wa_021", "well_architected", "Monitoring as a cost-reduction enabler",
        "Detailed utilization monitoring is a prerequisite for every right-sizing decision; without it, "
        "optimization decisions are guesses rather than evidence-based actions."),
    KnowledgeChunk("wa_022", "well_architected", "Network egress minimization",
        "Architectures that minimize cross-region and internet egress traffic - for example by serving cached "
        "content from a CDN edge location - reduce a cost category that is easy to overlook relative to compute "
        "and storage."),

    # --- additional FinOps Foundation chunks ---
    KnowledgeChunk("finops_011", "finops_foundation", "Real-time cost visibility",
        "Near-real-time cost data (rather than only month-end invoices) allows engineering teams to see the cost "
        "impact of a change shortly after deploying it, closing the feedback loop between action and cost."),
    KnowledgeChunk("finops_012", "finops_foundation", "Benchmarking against peers",
        "Comparing unit economics and waste ratios against industry or internal benchmarks helps an organization "
        "judge whether its current spend efficiency is actually good, rather than just better than last quarter."),
    KnowledgeChunk("finops_013", "finops_foundation", "Avoiding false precision in forecasts",
        "A forecast with a wide but honest confidence interval is more useful for planning than a falsely precise "
        "point estimate that consistently misses by a wide margin."),
    KnowledgeChunk("finops_014", "finops_foundation", "Executive reporting cadence",
        "Regular, concise executive-level cost reporting (e.g., weekly) that highlights material changes keeps "
        "leadership engaged with cost trends without requiring them to parse raw billing data."),
    KnowledgeChunk("finops_015", "finops_foundation", "Treating savings as a target, not a one-time event",
        "Realized savings can erode over time as new resources are provisioned without the same optimization "
        "discipline; tracking net savings on a rolling basis catches this regression."),
    KnowledgeChunk("finops_016", "finops_foundation", "Confidence-weighted recommendations",
        "Not all cost-saving recommendations carry equal certainty; surfacing a confidence level alongside each "
        "recommendation helps teams triage which actions to take immediately versus which need further "
        "investigation first."),
    KnowledgeChunk("finops_017", "finops_foundation", "Waste versus risk trade-off",
        "Some apparent waste (e.g., low average utilization) exists deliberately for headroom against rare traffic "
        "spikes or failover; a good optimization process distinguishes intentional headroom from true waste before "
        "recommending action."),

    # --- additional Trusted Advisor style rule patterns ---
    KnowledgeChunk("ta_009", "trusted_advisor", "Unused NAT gateways",
        "NAT gateways provisioned for a workload that has since been decommissioned continue to bill hourly "
        "regardless of traffic and are easy to miss during cleanup."),
    KnowledgeChunk("ta_010", "trusted_advisor", "Multiple small underutilized databases",
        "Several small, lightly used database instances are sometimes cheaper to consolidate onto fewer, "
        "appropriately sized instances than to run separately, especially when each carries its own fixed minimum "
        "cost overhead."),
    KnowledgeChunk("ta_011", "trusted_advisor", "Stale auto-scaling group minimums",
        "An auto-scaling group with a minimum instance count set defensively high relative to actual baseline "
        "traffic keeps paying for capacity that scaling logic would otherwise remove."),
    KnowledgeChunk("ta_012", "trusted_advisor", "Orphaned load test infrastructure",
        "Infrastructure stood up temporarily for load testing or a one-off migration is a common source of "
        "forgotten, still-billing resources if there is no explicit teardown step in the process."),

    # --- additional pricing reference notes ---
    KnowledgeChunk("pricing_005", "pricing_reference", "Spot price volatility",
        "Spot prices fluctuate with capacity supply and demand and can vary meaningfully across availability "
        "zones within the same region for the same instance type, which is why spot-price prediction and "
        "monitoring add value over treating spot pricing as static."),
    KnowledgeChunk("pricing_006", "pricing_reference", "Minimum billing increments",
        "Some services bill in whole-hour or whole-second increments with a practical minimum charge; very "
        "short-lived resources can accrue cost disproportionate to their actual runtime if spun up and down "
        "frequently."),
    KnowledgeChunk("pricing_007", "pricing_reference", "Free tier limits",
        "Free-tier allowances typically apply only up to a usage threshold and often only for a limited account "
        "age; usage that consistently sits near the free-tier ceiling is worth monitoring since small growth can "
        "push it into billed usage."),
]


def get_corpus_size() -> int:
    return len(KNOWLEDGE_CHUNKS)


if __name__ == "__main__":
    print(f"Curated corpus size: {get_corpus_size()} chunks")
    by_category: dict[str, int] = {}
    for c in KNOWLEDGE_CHUNKS:
        by_category[c.category] = by_category.get(c.category, 0) + 1
    for cat, count in by_category.items():
        print(f"  {cat}: {count}")
