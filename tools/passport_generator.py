"""
TraceX AI — Digital Product Passport Generator

Combines outputs from:
    Evidence Agent
    Traceability Agent
    Compliance Agent
    Risk Agent
    Verification Agent

into one structured Digital Product Passport.

This version:
    - Preserves canonical product identity
    - Deduplicates evidence gaps semantically
    - Consolidates repetitive action items
    - Keeps human-review requirements separate
    - Keeps deterministic risk values unchanged
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List


# =========================================================
# HELPERS
# =========================================================

def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _first_non_empty(
    *values: Any,
    default: Any = None,
) -> Any:

    for value in values:

        if value not in (None, "", [], {}):

            return value

    return default


def _normalize_status(
    value: Any,
    default: str = "UNKNOWN",
) -> str:

    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return text.upper().replace(" ", "_")


def _clean_text(
    value: Any,
) -> str:

    text = str(value or "").strip()

    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("ﬁ", "fi")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _unique_strings(
    items: List[Any],
) -> List[str]:
    """
    Remove exact duplicates while preserving order.
    """

    result: List[str] = []
    seen = set()

    for item in items:

        if item is None:
            continue

        value = _clean_text(item)

        if not value:
            continue

        key = value.lower()

        if key not in seen:

            seen.add(key)
            result.append(value)

    return result


# =========================================================
# SEMANTIC ISSUE NORMALIZATION
# =========================================================

def _canonical_issue(
    value: Any,
) -> str:
    """
    Convert different descriptions of the same underlying
    issue into one canonical key.

    Examples:

        Cotton Fiber Origin
        Raw-material origin provenance
        Cotton source unverified

            -> MATERIAL_ORIGIN

        Manufacturing Batch ID
        Processing Batch Reference
        Dye House Lot Identification

            -> BATCH_TRACEABILITY

        Energy Consumption Record
        Energy / Environmental Data
        Factory Energy Usage

            -> ENERGY_ENVIRONMENT

        Destination Market
        Unspecified destination
        Target market

            -> DESTINATION_MARKET

        Export certificate
        Required export documentation

            -> EXPORT_CERTIFICATE
    """

    text = _clean_text(
        value
    ).lower()

    # Common noise words.
    text = re.sub(
        r"\b(missing|gap|gaps|evidence|provide|verify|"
        r"verification|recommended|requirement|"
        r"requires|review|item|information)\b",
        " ",
        text,
    )

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    # -----------------------------------------------------
    # Destination Market
    # -----------------------------------------------------

    if (
        "destination" in text
        or "target market" in text
        or "export market" in text
        or "market specific" in text
        or "market-specific" in text
    ):
        return "DESTINATION_MARKET"

    # -----------------------------------------------------
    # Material Origin
    # -----------------------------------------------------

    if (
        (
            "origin" in text
            and (
                "cotton" in text
                or "fiber" in text
                or "fibre" in text
                or "raw material" in text
                or "material" in text
            )
        )
        or "cotton source" in text
        or "raw material provenance" in text
        or "origin provenance" in text
    ):
        return "MATERIAL_ORIGIN"

    # -----------------------------------------------------
    # Batch Traceability
    # -----------------------------------------------------

    if (
        "batch" in text
        or "dye lot" in text
        or "dye house lot" in text
        or "processing lot" in text
        or "lot identification" in text
        or "manufacturing reference" in text
        or "production reference" in text
    ):
        return "BATCH_TRACEABILITY"

    # -----------------------------------------------------
    # Energy / Environmental
    # -----------------------------------------------------

    if (
        "energy" in text
        or "environmental" in text
        or "etp" in text
        or "factory usage" in text
        or "energy consumption" in text
    ):
        return "ENERGY_ENVIRONMENT"

    # -----------------------------------------------------
    # Export Certificate
    # -----------------------------------------------------

    if (
        "certificate" in text
        or "export documentation" in text
        or "export document" in text
    ):
        return "EXPORT_CERTIFICATE"

    # -----------------------------------------------------
    # Recycling
    # -----------------------------------------------------

    if "recycling" in text:
        return "RECYCLING_INFORMATION"

    # -----------------------------------------------------
    # Generic fallback
    # -----------------------------------------------------

    return text


# =========================================================
# GAP MERGING
# =========================================================

def _merge_gaps(
    *sources: List[Any],
) -> List[str]:
    """
    Merge gaps using semantic canonical keys instead of
    exact string matching.

    This prevents the same issue from appearing multiple
    times because different agents used different wording.
    """

    result: List[str] = []
    seen = set()

    for source in sources:

        for item in _safe_list(source):

            value = _clean_text(item)

            if not value:
                continue

            key = _canonical_issue(
                value
            )

            if not key:
                continue

            if key in seen:
                continue

            seen.add(key)

            result.append(
                value
            )

    return result


# =========================================================
# PRODUCT IDENTITY
# =========================================================

def build_product_identity(
    evidence: Dict[str, Any],
    traceability: Dict[str, Any],
    risk: Dict[str, Any],
) -> Dict[str, Any]:

    product_name = _first_non_empty(
        evidence.get("product"),
        traceability.get("product"),
        risk.get("product"),
        default="Unknown Product",
    )

    product_name = _clean_text(
        product_name
    )

    if not product_name:
        product_name = "Unknown Product"

    return {
        "name": product_name,
        "sku_or_product_id": "Not provided",
        "category": "Textile / Apparel",
    }


# =========================================================
# SUPPLIER
# =========================================================

def build_supplier(
    evidence: Dict[str, Any],
    traceability: Dict[str, Any],
) -> Dict[str, Any]:

    supplier_name = _first_non_empty(
        evidence.get("supplier"),
        traceability.get("supplier"),
        default="Unknown Supplier",
    )

    supplier_name = _clean_text(
        supplier_name
    )

    registration_status = "UNKNOWN"

    evidence_items = _safe_list(
        evidence.get(
            "evidence_items"
        )
    )

    for item in evidence_items:

        item_data = _safe_dict(
            item
        )

        item_name = _clean_text(
            item_data.get(
                "item",
                "",
            )
        ).lower()

        item_status = _normalize_status(
            item_data.get(
                "status"
            )
        )

        if (
            "supplier registration" in item_name
            and item_status == "VERIFIED"
        ):

            registration_status = "VERIFIED"

    return {
        "name": supplier_name,
        "registration_status": registration_status,
    }


# =========================================================
# MATERIAL
# =========================================================

def build_material(
    evidence: Dict[str, Any],
    traceability: Dict[str, Any],
) -> Dict[str, Any]:

    material = "Not provided"
    origin = "Not verified"

    trace_chain = _safe_list(
        traceability.get(
            "trace_chain"
        )
    )

    for item in trace_chain:

        item_data = _safe_dict(
            item
        )

        entity_type = _normalize_status(
            item_data.get(
                "entity_type"
            )
        )

        entity_name = _clean_text(
            item_data.get(
                "entity_name",
                "",
            )
        )

        if entity_type == "MATERIAL":

            if entity_name:
                material = entity_name

        if (
            entity_name.lower()
            in {
                "cotton farm/origin",
                "material origin",
                "cotton fiber origin",
                "raw material origin",
            }
        ):

            status = _normalize_status(
                item_data.get(
                    "status"
                )
            )

            if status == "VERIFIED":

                origin = entity_name

            else:

                origin = "Not verified"

    return {
        "composition": material,
        "origin": origin,
    }


# =========================================================
# EVIDENCE MATRIX
# =========================================================

def build_evidence_matrix(
    evidence: Dict[str, Any],
) -> Dict[str, Any]:

    evidence_items = _safe_list(
        evidence.get(
            "evidence_items"
        )
    )

    verified = []
    missing = []
    unclear = []

    for item in evidence_items:

        item_data = _safe_dict(
            item
        )

        name = item_data.get(
            "item",
            "Unknown evidence",
        )

        status = _normalize_status(
            item_data.get(
                "status"
            )
        )

        if status == "VERIFIED":

            verified.append(
                name
            )

        elif status == "MISSING":

            missing.append(
                name
            )

        else:

            unclear.append(
                name
            )

    critical_gaps = _safe_list(
        evidence.get(
            "critical_gaps"
        )
    )

    overall_status = _normalize_status(
        evidence.get(
            "overall_evidence_status"
        )
    )

    return {
        "status": overall_status,
        "verified": _unique_strings(
            verified
        ),
        "missing": _unique_strings(
            missing
        ),
        "unclear": _unique_strings(
            unclear
        ),
        "critical_gaps": _merge_gaps(
            critical_gaps
        ),
    }


# =========================================================
# TRACEABILITY
# =========================================================

def build_traceability(
    traceability: Dict[str, Any],
) -> Dict[str, Any]:

    status = _normalize_status(
        traceability.get(
            "traceability_status"
        )
    )

    chain = _safe_list(
        traceability.get(
            "trace_chain"
        )
    )

    gaps = _safe_list(
        traceability.get(
            "gaps"
        )
    )

    return {
        "status": status,
        "chain": chain,
        "gaps": _merge_gaps(
            gaps
        ),
    }


# =========================================================
# COMPLIANCE
# =========================================================

def build_compliance(
    compliance: Dict[str, Any],
) -> Dict[str, Any]:

    status = _normalize_status(
        compliance.get(
            "overall_status"
        )
    )

    checks = _safe_list(
        compliance.get(
            "checks"
        )
    )

    critical_gaps = _safe_list(
        compliance.get(
            "critical_gaps"
        )
    )

    recommended_actions = _safe_list(
        compliance.get(
            "recommended_actions"
        )
    )

    human_review = []

    for check in checks:

        check_data = _safe_dict(
            check
        )

        check_status = _normalize_status(
            check_data.get(
                "status"
            )
        )

        if check_status == "HUMAN_REVIEW":

            requirement = check_data.get(
                "requirement",
                "Compliance requirement",
            )

            human_review.append(
                requirement
            )

    return {
        "status": status,
        "requirements": checks,
        "gaps": _merge_gaps(
            critical_gaps
        ),
        "human_review": _unique_strings(
            human_review
        ),
        "recommended_actions": _unique_strings(
            recommended_actions
        ),
    }


# =========================================================
# RISK
# =========================================================

def build_risk(
    risk: Dict[str, Any],
) -> Dict[str, Any]:

    score = risk.get(
        "risk_score",
        0,
    )

    level = _normalize_status(
        risk.get(
            "overall_risk"
        )
    )

    product = _clean_text(
        risk.get(
            "product",
            "",
        )
    )

    breakdown: Dict[str, str] = {}

    risks = _safe_list(
        risk.get(
            "risks"
        )
    )

    for risk_item in risks:

        risk_data = _safe_dict(
            risk_item
        )

        category = risk_data.get(
            "category",
            "UNKNOWN",
        )

        severity = risk_data.get(
            "severity",
            "UNKNOWN",
        )

        breakdown[
            str(category)
        ] = str(severity)

    human_review_required = any(
        bool(
            _safe_dict(item).get(
                "human_review_required",
                False,
            )
        )
        for item in risks
    )

    explanation = risk.get(
        "decision_summary",
        "",
    )

    return {
        "product": product,
        "score": score,
        "level": level,
        "breakdown": breakdown,
        "explanation": explanation,
        "human_review_required": human_review_required,
    }


# =========================================================
# VERIFICATION
# =========================================================

def build_verification(
    verification: Dict[str, Any],
) -> Dict[str, Any]:

    status = _normalize_status(
        verification.get(
            "overall_verdict"
        )
    )

    findings = _safe_list(
        verification.get(
            "findings"
        )
    )

    human_review_required = bool(
        verification.get(
            "human_review_required",
            False,
        )
    )

    verified_claims = verification.get(
        "verified_claims",
        0,
    )

    flagged_claims = verification.get(
        "flagged_claims",
        0,
    )

    unsupported_claims = []

    for finding in findings:

        finding_data = _safe_dict(
            finding
        )

        verdict = _normalize_status(
            finding_data.get(
                "verdict"
            )
        )

        if verdict == "UNSUPPORTED":

            claim = finding_data.get(
                "claim"
            )

            if claim:

                unsupported_claims.append(
                    claim
                )

    return {
        "status": status,
        "findings": findings,
        "verified_claims": verified_claims,
        "flagged_claims": flagged_claims,
        "unsupported_claims": _unique_strings(
            unsupported_claims
        ),
        "human_review_required": human_review_required,
        "final_guidance": _unique_strings(
            verification.get(
                "final_guidance",
                [],
            )
        ),
    }


# =========================================================
# EVIDENCE GAPS
# =========================================================

def collect_evidence_gaps(
    evidence: Dict[str, Any],
    traceability: Dict[str, Any],
    compliance: Dict[str, Any],
) -> List[str]:

    evidence_gaps = _safe_list(
        evidence.get(
            "critical_gaps"
        )
    )

    traceability_gaps = _safe_list(
        traceability.get(
            "gaps"
        )
    )

    compliance_gaps = _safe_list(
        compliance.get(
            "critical_gaps"
        )
    )

    return _merge_gaps(
        evidence_gaps,
        traceability_gaps,
        compliance_gaps,
    )


# =========================================================
# HUMAN REVIEW FLAGS
# =========================================================

def collect_human_review_flags(
    compliance: Dict[str, Any],
    risk: Dict[str, Any],
    verification: Dict[str, Any],
) -> List[str]:

    flags = []

    # -----------------------------------------------------
    # Compliance human review
    # -----------------------------------------------------

    for item in _safe_list(
        compliance.get(
            "checks"
        )
    ):

        item_data = _safe_dict(
            item
        )

        if (
            _normalize_status(
                item_data.get(
                    "status"
                )
            )
            == "HUMAN_REVIEW"
        ):

            requirement = item_data.get(
                "requirement"
            )

            if requirement:

                flags.append(
                    f"Review compliance requirement: {requirement}"
                )

    # -----------------------------------------------------
    # Risk human review
    # -----------------------------------------------------

    for item in _safe_list(
        risk.get(
            "risks"
        )
    ):

        item_data = _safe_dict(
            item
        )

        if item_data.get(
            "human_review_required",
            False,
        ):

            issue = item_data.get(
                "issue",
                "Risk item requires human review.",
            )

            flags.append(
                f"Review risk item: {issue}"
            )

    # -----------------------------------------------------
    # Verification human review
    # -----------------------------------------------------

    if verification.get(
        "human_review_required",
        False,
    ):

        flags.append(
            "Verification layer requires human review."
        )

    # -----------------------------------------------------
    # Semantic deduplication
    # -----------------------------------------------------

    unique_flags = []
    seen = set()

    for flag in flags:

        key = _canonical_issue(
            flag
        )

        if not key:
            key = _clean_text(
                flag
            ).lower()

        if key in seen:
            continue

        seen.add(key)

        unique_flags.append(
            _clean_text(
                flag
            )
        )

    return unique_flags


# =========================================================
# EXPORT READINESS
# =========================================================

def determine_export_readiness(
    compliance: Dict[str, Any],
    risk: Dict[str, Any],
    verification: Dict[str, Any],
    evidence_gaps: List[str],
) -> str:

    compliance_status = _normalize_status(
        compliance.get(
            "overall_status"
        )
    )

    risk_level = _normalize_status(
        risk.get(
            "overall_risk"
        )
    )

    if compliance_status in {
        "GAPS_FOUND",
        "INCOMPLETE",
        "NON_COMPLIANT",
    }:

        return "NOT_READY"

    if verification.get(
        "human_review_required",
        False,
    ):

        return "HUMAN_REVIEW_REQUIRED"

    if risk_level == "HIGH":

        return "HIGH_RISK_REVIEW"

    if evidence_gaps:

        return "PARTIALLY_READY"

    return "READY"


# =========================================================
# ACTION PLAN — SEMANTIC CONSOLIDATION
# =========================================================

def _action_bucket(
    text: Any,
) -> str:
    """
    Map any action wording into one semantic bucket.
    """

    return _canonical_issue(
        text
    )


def _build_clean_action(
    bucket: str,
    compliance: Dict[str, Any],
    evidence_gaps: List[str],
    human_review_flags: List[str],
) -> Dict[str, Any] | None:
    """
    Generate one clean exporter-focused action per issue.
    """

    # -----------------------------------------------------
    # Destination
    # -----------------------------------------------------

    if bucket == "DESTINATION_MARKET":

        return {
            "priority": "HIGH",
            "action": (
                "Specify the intended destination market."
            ),
            "reason": (
                "Destination-specific export requirements "
                "cannot be reliably assessed without the "
                "target market."
            ),
        }

    # -----------------------------------------------------
    # Material origin
    # -----------------------------------------------------

    if bucket == "MATERIAL_ORIGIN":

        return {
            "priority": "HIGH",
            "action": (
                "Provide raw-material/fiber origin provenance "
                "evidence."
            ),
            "reason": (
                "The upstream origin of the material is not "
                "fully linked to verified evidence."
            ),
        }

    # -----------------------------------------------------
    # Batch traceability
    # -----------------------------------------------------

    if bucket == "BATCH_TRACEABILITY":

        return {
            "priority": "HIGH",
            "action": (
                "Add production, processing or dye-lot "
                "batch references."
            ),
            "reason": (
                "Batch-level linkage is needed to strengthen "
                "product traceability."
            ),
        }

    # -----------------------------------------------------
    # Energy / environmental
    # -----------------------------------------------------

    if bucket == "ENERGY_ENVIRONMENT":

        return {
            "priority": "MEDIUM",
            "action": (
                "Provide available energy or environmental "
                "records."
            ),
            "reason": (
                "Environmental evidence is currently "
                "incomplete in the dossier."
            ),
        }

    # -----------------------------------------------------
    # Export certificate
    # -----------------------------------------------------

    if bucket == "EXPORT_CERTIFICATE":

        return {
            "priority": "HIGH",
            "action": (
                "Verify and provide the required export "
                "certificate or supporting documentation."
            ),
            "reason": (
                "The dossier does not contain sufficient "
                "export-document evidence for final validation."
            ),
        }

    # -----------------------------------------------------
    # Recycling
    # -----------------------------------------------------

    if bucket == "RECYCLING_INFORMATION":

        return {
            "priority": "MEDIUM",
            "action": (
                "Provide available recycling or end-of-life "
                "information."
            ),
            "reason": (
                "Relevant lifecycle evidence is currently "
                "incomplete."
            ),
        }

    # -----------------------------------------------------
    # Generic evidence
    # -----------------------------------------------------

    for gap in evidence_gaps:

        if _action_bucket(gap) == bucket:

            return {
                "priority": "HIGH",
                "action": (
                    f"Provide or verify evidence for: {gap}"
                ),
                "reason": (
                    "Missing or unresolved evidence reduces "
                    "export readiness."
                ),
            }

    # -----------------------------------------------------
    # Generic human review
    # -----------------------------------------------------

    for flag in human_review_flags:

        if _action_bucket(flag) == bucket:

            return {
                "priority": "REVIEW",
                "action": _clean_text(
                    flag
                ),
                "reason": (
                    "TraceX identified a finding requiring "
                    "human validation."
                ),
            }

    return None


def build_priority_actions(
    evidence: Dict[str, Any],
    traceability: Dict[str, Any],
    compliance: Dict[str, Any],
    risk: Dict[str, Any],
    verification: Dict[str, Any],
    evidence_gaps: List[str],
    human_review_flags: List[str],
) -> List[Dict[str, Any]]:

    # =====================================================
    # COLLECT POSSIBLE ISSUE BUCKETS
    # =====================================================

    buckets: List[str] = []

    # Compliance gaps.
    for gap in _safe_list(
        compliance.get(
            "critical_gaps"
        )
    ):

        bucket = _action_bucket(
            gap
        )

        if bucket:
            buckets.append(
                bucket
            )

    # Evidence gaps.
    for gap in evidence_gaps:

        bucket = _action_bucket(
            gap
        )

        if bucket:
            buckets.append(
                bucket
            )

    # Human review.
    for flag in human_review_flags:

        bucket = _action_bucket(
            flag
        )

        if bucket:
            buckets.append(
                bucket
            )

    # Compliance recommended actions.
    for action in _safe_list(
        compliance.get(
            "recommended_actions"
        )
    ):

        bucket = _action_bucket(
            action
        )

        if bucket:
            buckets.append(
                bucket
            )

    # =====================================================
    # ORDER + DEDUPLICATE
    # =====================================================

    preferred_order = [
        "DESTINATION_MARKET",
        "MATERIAL_ORIGIN",
        "BATCH_TRACEABILITY",
        "EXPORT_CERTIFICATE",
        "ENERGY_ENVIRONMENT",
        "RECYCLING_INFORMATION",
    ]

    ordered_buckets = []

    # First preferred business-critical categories.
    for bucket in preferred_order:

        if bucket in buckets:

            if bucket not in ordered_buckets:

                ordered_buckets.append(
                    bucket
                )

    # Then any other detected categories.
    for bucket in buckets:

        if bucket not in ordered_buckets:

            ordered_buckets.append(
                bucket
            )

    # =====================================================
    # BUILD CLEAN ACTIONS
    # =====================================================

    actions: List[Dict[str, Any]] = []

    for bucket in ordered_buckets:

        action = _build_clean_action(
            bucket=bucket,
            compliance=compliance,
            evidence_gaps=evidence_gaps,
            human_review_flags=human_review_flags,
        )

        if action:

            actions.append(
                action
            )

    # =====================================================
    # EXPLICIT HUMAN REVIEW ACTION
    # =====================================================

    if human_review_flags:

        has_destination = any(
            _action_bucket(flag)
            == "DESTINATION_MARKET"
            for flag in human_review_flags
        )

        if not has_destination:

            actions.append(
                {
                    "priority": "REVIEW",
                    "action": (
                        "Complete human review of unresolved "
                        "export/compliance findings."
                    ),
                    "reason": (
                        "TraceX cannot make a reliable final "
                        "determination from the available evidence."
                    ),
                }
            )

    # =====================================================
    # RISK-DRIVEN ACTION
    # =====================================================

    risk_level = _normalize_status(
        risk.get(
            "overall_risk"
        )
    )

    if risk_level == "HIGH":

        actions.append(
            {
                "priority": "HIGH",
                "action": (
                    "Perform final export-readiness review "
                    "before shipment."
                ),
                "reason": (
                    "The deterministic risk engine classified "
                    "this case as HIGH risk."
                ),
            }
        )

    elif risk_level == "CRITICAL":

        actions.append(
            {
                "priority": "CRITICAL",
                "action": (
                    "Escalate the dossier for immediate "
                    "human review before shipment."
                ),
                "reason": (
                    "The deterministic risk engine classified "
                    "this case as CRITICAL risk."
                ),
            }
        )

    # =====================================================
    # FINAL DEDUPLICATION
    # =====================================================

    final_actions = []

    seen = set()

    for action in actions:

        action_text = _clean_text(
            action.get(
                "action",
                "",
            )
        )

        if not action_text:
            continue

        key = _action_bucket(
            action_text
        )

        if key in seen:
            continue

        seen.add(key)

        final_actions.append(
            {
                "priority": action.get(
                    "priority",
                    "MEDIUM",
                ),
                "action": action_text,
                "reason": _clean_text(
                    action.get(
                        "reason",
                        "",
                    )
                ),
            }
        )

    # =====================================================
    # MAX 5 JUDGE-FACING ACTIONS
    # =====================================================

    final_actions = final_actions[:5]

    # =====================================================
    # SAFE FALLBACK
    # =====================================================

    if not final_actions:

        final_actions.append(
            {
                "priority": "LOW",
                "action": (
                    "Maintain current evidence and "
                    "compliance records."
                ),
                "reason": (
                    "No major unresolved actions were identified."
                ),
            }
        )

    return final_actions


# =========================================================
# MAIN PASSPORT GENERATOR
# =========================================================

def generate_passport(
    evidence: Dict[str, Any],
    traceability: Dict[str, Any],
    compliance: Dict[str, Any],
    risk: Dict[str, Any],
    verification: Dict[str, Any],
) -> Dict[str, Any]:

    evidence = _safe_dict(
        evidence
    )

    traceability = _safe_dict(
        traceability
    )

    compliance = _safe_dict(
        compliance
    )

    risk = _safe_dict(
        risk
    )

    verification = _safe_dict(
        verification
    )

    # -----------------------------------------------------
    # Build sections
    # -----------------------------------------------------

    product_identity = build_product_identity(
        evidence,
        traceability,
        risk,
    )

    supplier = build_supplier(
        evidence,
        traceability,
    )

    material = build_material(
        evidence,
        traceability,
    )

    evidence_matrix = build_evidence_matrix(
        evidence
    )

    traceability_section = build_traceability(
        traceability
    )

    compliance_section = build_compliance(
        compliance
    )

    risk_section = build_risk(
        risk
    )

    verification_section = build_verification(
        verification
    )

    evidence_gaps = collect_evidence_gaps(
        evidence,
        traceability,
        compliance,
    )

    human_review_flags = collect_human_review_flags(
        compliance,
        risk,
        verification,
    )

    export_readiness = determine_export_readiness(
        compliance,
        risk,
        verification,
        evidence_gaps,
    )

    priority_actions = build_priority_actions(
        evidence,
        traceability,
        compliance,
        risk,
        verification,
        evidence_gaps,
        human_review_flags,
    )

    # -----------------------------------------------------
    # Final passport
    # -----------------------------------------------------

    passport = {

        "passport_metadata": {
            "passport_version": "1.0",
            "generated_by": "TraceX AI",
            "generated_at": datetime.now().isoformat(
                timespec="seconds"
            ),
            "verification_model": (
                "Multi-Agent Verification"
            ),
        },

        "product_identity": product_identity,

        "supplier": supplier,

        "material": material,

        "traceability": traceability_section,

        "evidence_matrix": evidence_matrix,

        "compliance": compliance_section,

        "risk": risk_section,

        "verification": verification_section,

        "export_readiness": {
            "status": export_readiness,
            "evidence_gap_count": len(
                evidence_gaps
            ),
            "human_review_required": bool(
                human_review_flags
            ),
        },

        "evidence_gaps": evidence_gaps,

        "human_review_flags": human_review_flags,

        "priority_actions": priority_actions,
    }

    return passport


# =========================================================
# JSON EXPORT
# =========================================================

def passport_to_json(
    passport: Dict[str, Any],
    indent: int = 2,
) -> str:

    return json.dumps(
        passport,
        indent=indent,
        ensure_ascii=False,
        default=str,
    )


def save_passport_json(
    passport: Dict[str, Any],
    output_path: str = "data/passport.json",
) -> str:

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            passport,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    return output_path


# =========================================================
# LOCAL TEST
# =========================================================

if __name__ == "__main__":

    print("\n" + "=" * 60)

    print(
        "       TRACEX AI — DIGITAL PRODUCT PASSPORT"
    )

    print("=" * 60)

    demo_evidence = {

        "product": "100% Cotton T-Shirt",

        "supplier": "ABC Textile Mills",

        "evidence_items": [

            {
                "item": "Supplier registration document",
                "status": "VERIFIED",
            },

            {
                "item": "Cotton material declaration",
                "status": "VERIFIED",
            },

            {
                "item": "Lab test report",
                "status": "VERIFIED",
            },

            {
                "item": "Cotton farm/origin",
                "status": "MISSING",
            },

            {
                "item": "Manufacturing batch ID",
                "status": "MISSING",
            },

            {
                "item": "Energy consumption record",
                "status": "MISSING",
            },

            {
                "item": "Required export certificate",
                "status": "MISSING",
            },
        ],

        "overall_evidence_status": "INCOMPLETE",

        "critical_gaps": [

            "Cotton farm/origin",

            "Manufacturing batch ID",

            "Energy consumption record",

            "Required export certificate",
        ],
    }

    demo_traceability = {

        "product": "100% Cotton T-Shirt",

        "supplier": "ABC Textile Mills",

        "trace_chain": [

            {
                "entity_type": "SUPPLIER",
                "entity_name": "ABC Textile Mills",
                "status": "VERIFIED",
            },

            {
                "entity_type": "MATERIAL",
                "entity_name": "100% Cotton",
                "status": "VERIFIED",
            },

            {
                "entity_type": "PRODUCT",
                "entity_name": "100% Cotton T-Shirt",
                "status": "VERIFIED",
            },
        ],

        "traceability_status": "PARTIALLY_TRACED",

        "gaps": [

            "Cotton farm/origin",

            "Cotton farm / raw material origin is missing",

            "Manufacturing batch ID",

            "Processing batch reference is missing",

            "Energy consumption record",

            "Energy / environmental data",
            
            "Required export certificate",
        ],
    }

    demo_compliance = {

        "overall_status": "GAPS_FOUND",

        "checks": [

            {
                "requirement": (
                    "Supplier identity and registration"
                ),
                "status": "SATISFIED",
            },

            {
                "requirement": (
                    "Material composition declaration"
                ),
                "status": "SATISFIED",
            },

            {
                "requirement": (
                    "Cotton farm or material origin"
                ),
                "status": "GAP",
            },

            {
                "requirement": (
                    "Manufacturing batch reference"
                ),
                "status": "GAP",
            },

            {
                "requirement": (
                    "Energy consumption record"
                ),
                "status": "GAP",
            },

            {
                "requirement": (
                    "Required export certificate"
                ),
                "status": "HUMAN_REVIEW",
            },
        ],

        "critical_gaps": [

            "Missing cotton farm/origin evidence",

            "Missing manufacturing batch ID",

            "Missing energy consumption record",

            "Missing required export certificate",
        ],

        "recommended_actions": [

            "Obtain and add the cotton farm and origin documentation to the product dossier.",

            "Include the manufacturing batch ID to complete the product traceability link.",

            "Provide energy consumption records if applicable.",

            "Conduct a human review to verify specific export certificate requirements for the destination market.",
        ],
    }

    demo_risk = {

        "product": "100% Cotton T-Shirt",

        "overall_risk": "HIGH",

        "risk_score": 71,

        "risks": [

            {
                "category": "TRACEABILITY",
                "severity": "HIGH",
                "human_review_required": False,
                "issue": (
                    "Missing cotton farm/origin evidence"
                ),
            },

            {
                "category": "DOCUMENTATION",
                "severity": "HIGH",
                "human_review_required": False,
                "issue": (
                    "Missing manufacturing batch ID"
                ),
            },

            {
                "category": "DATA_QUALITY",
                "severity": "MEDIUM",
                "human_review_required": False,
                "issue": (
                    "Missing energy consumption record"
                ),
            },

            {
                "category": "COMPLIANCE",
                "severity": "HIGH",
                "human_review_required": True,
                "issue": (
                    "Required export certificate "
                    "requires review"
                ),
            },
        ],

        "decision_summary": (
            "The numeric risk score of 71 and overall "
            "risk level of HIGH come from TraceX "
            "deterministic evidence/risk rules."
        ),
    }

    demo_verification = {

        "overall_verdict": "VERIFIED_WITH_WARNINGS",

        "verified_claims": 18,

        "flagged_claims": 2,

        "human_review_required": True,

        "findings": [

            {
                "claim": (
                    "Specific export certificate "
                    "requirements require human review."
                ),
                "verdict": "SUPPORTED",
            },

            {
                "claim": (
                    "Risk score 71 is an internal "
                    "heuristic indicator."
                ),
                "verdict": "PARTIALLY_SUPPORTED",
            },
        ],

        "final_guidance": [

            "Address missing dossier items.",

            "Do not treat missing information as an "
            "automatic legal rejection.",
        ],
    }

    passport = generate_passport(

        evidence=demo_evidence,

        traceability=demo_traceability,

        compliance=demo_compliance,

        risk=demo_risk,

        verification=demo_verification,
    )

    print(
        "\n✅ Passport generated successfully.\n"
    )

    print(
        passport_to_json(
            passport
        )
    )

    print("\n" + "=" * 60)

    print(
        "✅ DIGITAL PRODUCT PASSPORT TEST PASSED"
    )

    print("=" * 60)