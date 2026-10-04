import re
import sys
import inspect
from pathlib import Path
from typing import List, Any, Dict

from pydantic import BaseModel, Field, ValidationError


# =========================================================
# 1. PROJECT ROOT
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =========================================================
# 2. CENTRAL AI SERVICE
# =========================================================

try:
    import services.ai_service as central_ai

except Exception as error:
    raise ImportError(
        "Could not import the Central AI Service.\n"
        "Please make sure this file exists:\n"
        r"C:\TraceXAI\services\ai_service.py"
    ) from error


# =========================================================
# 3. STRUCTURED OUTPUT MODELS
# =========================================================

class RiskItem(BaseModel):
    risk_id: str

    category: str = Field(
        description=(
            "One of: TRACEABILITY, EVIDENCE, COMPLIANCE, "
            "DOCUMENTATION, DATA_QUALITY, OPERATIONAL."
        )
    )

    severity: str = Field(
        description=(
            "One of: LOW, MEDIUM, HIGH, CRITICAL."
        )
    )

    issue: str
    trigger: str
    affected_area: str
    rationale: str
    recommended_mitigation: str
    human_review_required: bool


class RiskReport(BaseModel):
    product: str

    overall_risk: str = Field(
        description=(
            "One of: LOW, MEDIUM, HIGH, CRITICAL."
        )
    )

    risk_score: int = Field(
        ge=0,
        le=100,
        description=(
            "Deterministic overall risk score from 0 to 100."
        ),
    )

    risks: List[RiskItem]

    top_priority_actions: List[str]

    decision_summary: str


# =========================================================
# 4. TEXT HELPERS
# =========================================================

def _clean_text(value: str) -> str:
    """
    Normalize text for reliable comparison.
    """

    text = str(value or "").strip().lower()

    text = text.replace("–", "-")
    text = text.replace("—", "-")

    # Normalize slash spacing.
    text = re.sub(
        r"\s*/\s*",
        " / ",
        text,
    )

    # Normalize whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# =========================================================
# 5. ROBUST ISSUE CANONICALIZER
# =========================================================

def _canonical_issue(value: str) -> str:
    """
    Convert different descriptions of the same issue into
    one canonical key.
    """

    text = _clean_text(value)

    # -----------------------------------------------------
    # Remove common wording.
    # -----------------------------------------------------

    text = re.sub(
        r"\bmissing\b",
        " ",
        text,
    )

    text = re.sub(
        r"\bcritical\b",
        " ",
        text,
    )

    text = re.sub(
        r"\b(gap|gaps)\b",
        " ",
        text,
    )

    text = re.sub(
        r"\bevidence\b",
        " ",
        text,
    )

    text = re.sub(
        r"\brequired\b",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    # =====================================================
    # SEMANTIC ISSUE DETECTION
    # =====================================================

    # -----------------------------------------------------
    # 1. MATERIAL ORIGIN
    # -----------------------------------------------------

    if (
        (
            "cotton" in text
            and (
                "origin" in text
                or "farm" in text
            )
        )
        or "raw material origin" in text
        or "material origin" in text
    ):
        return "material origin"

    # -----------------------------------------------------
    # 2. BATCH ID
    # -----------------------------------------------------

    if (
        (
            "batch" in text
            and (
                "id" in text
                or "identifier" in text
                or "reference" in text
            )
        )
        or "manufacturing batch" in text
        or "batch reference" in text
    ):
        return "batch id"

    # -----------------------------------------------------
    # 3. ENERGY RECORD
    # -----------------------------------------------------

    if (
        "energy" in text
        and (
            "consumption" in text
            or "record" in text
            or "data" in text
        )
    ):
        return "energy record"

    # -----------------------------------------------------
    # 4. EXPORT CERTIFICATE
    # -----------------------------------------------------

    if (
        "export" in text
        and "certificate" in text
    ):
        return "export certificate"

    # -----------------------------------------------------
    # 5. RECYCLING INFORMATION
    # -----------------------------------------------------

    if "recycling" in text:
        return "recycling information"

    # -----------------------------------------------------
    # 6. Generic fallback
    # -----------------------------------------------------

    text = text.replace("/", " ")

    text = re.sub(
        r"[^a-z0-9 ]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


# =========================================================
# 6. PRODUCT EXTRACTION
# =========================================================

def _extract_product(
    product_dossier: str,
) -> str:
    """
    Extract product name from:

        Product: ...

    Does not infer a product.
    """

    match = re.search(
        r"^\s*Product:\s*(.+?)\s*$",
        product_dossier,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    if match:

        product = match.group(1).strip()

        if product:
            return product

    return "Unknown Product"


# =========================================================
# 7. DOSSIER MISSING INFORMATION EXTRACTION
# =========================================================

def _extract_missing_information(
    product_dossier: str,
) -> List[str]:
    """
    Extract bullet items from the Missing information section.
    """

    items: List[str] = []

    match = re.search(
        r"Missing information:\s*(.*?)(?:"
        r"\n\s*(?:Destination market|Source document content):"
        r"|$"
        r")",
        product_dossier,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return items

    section = match.group(1)

    for line in section.splitlines():

        cleaned = line.strip()

        if cleaned.startswith("-"):

            item = cleaned.lstrip("-").strip()

            if item:
                items.append(item)

    return items


# =========================================================
# 8. BULLET EXTRACTION
# =========================================================

def _extract_bullet_items(
    text: str,
) -> List[str]:
    """
    Extract '-' bullet items from upstream agent reports.
    """

    items: List[str] = []

    for line in str(text or "").splitlines():

        cleaned = line.strip()

        if cleaned.startswith("-"):

            item = cleaned.lstrip("-").strip()

            if item:
                items.append(item)

    return items


# =========================================================
# 9. PHRASE DETECTION
# =========================================================

def _contains_phrase(
    text: str,
    phrases: List[str],
) -> bool:
    """
    Check whether any phrase exists in normalized text.
    """

    normalized = _clean_text(text)

    return any(
        phrase in normalized
        for phrase in phrases
    )


# =========================================================
# 10. UNIQUE ISSUE COLLECTION
# =========================================================

def _unique_by_canonical_key(
    items: List[str],
) -> List[str]:
    """
    Keep only one item for each canonical issue.
    """

    unique_items: List[str] = []
    seen_keys = set()

    for item in items:

        key = _canonical_issue(item)

        if not key:
            continue

        if key in seen_keys:
            continue

        seen_keys.add(key)

        unique_items.append(item)

    return unique_items


# =========================================================
# 11. DETERMINISTIC RISK ENGINE
# =========================================================

def calculate_deterministic_risk(
    product_dossier: str,
    evidence_report: str,
    traceability_report: str,
    compliance_report: str,
) -> Dict[str, Any]:
    """
    Deterministic TraceX risk engine.

    IMPORTANT:
    Gemini does NOT control the numeric score.

    SCORE RULES:

    Primary dossier missing information:
        +12 per unique missing item
        Maximum +48

    Additional compliance gaps:
        +8 per genuinely new issue
        Maximum +16

    Additional traceability gaps:
        +5 per genuinely new issue
        Maximum +10

    Incomplete / partially traced:
        +5

    Missing export certificate:
        +8

    Human review:
        FLAG ONLY.
        It is NOT separately scored because the underlying
        issue is already represented by the evidence gap.

    Final score:
        0 to 100

    Risk bands:
        0-24    LOW
        25-49   MEDIUM
        50-79   HIGH
        80-100  CRITICAL
    """

    # =====================================================
    # PRIMARY DOSSIER
    # =====================================================

    dossier_missing_raw = _extract_missing_information(
        product_dossier
    )

    dossier_missing = _unique_by_canonical_key(
        dossier_missing_raw
    )

    dossier_issue_keys = {
        _canonical_issue(item)
        for item in dossier_missing
    }

    # =====================================================
    # UPSTREAM REPORTS
    # =====================================================

    evidence_items = _extract_bullet_items(
        evidence_report
    )

    traceability_items = _extract_bullet_items(
        traceability_report
    )

    compliance_items = _extract_bullet_items(
        compliance_report
    )

    # =====================================================
    # ADDITIONAL COMPLIANCE GAPS
    # =====================================================

    additional_compliance_raw: List[str] = []

    for item in compliance_items:

        key = _canonical_issue(item)

        if (
            key
            and key not in dossier_issue_keys
        ):

            additional_compliance_raw.append(
                item
            )

    additional_compliance = (
        _unique_by_canonical_key(
            additional_compliance_raw
        )
    )

    # =====================================================
    # ADDITIONAL TRACEABILITY GAPS
    # =====================================================

    additional_traceability_raw: List[str] = []

    for item in traceability_items:

        key = _canonical_issue(item)

        if (
            key
            and key not in dossier_issue_keys
        ):

            additional_traceability_raw.append(
                item
            )

    additional_traceability = (
        _unique_by_canonical_key(
            additional_traceability_raw
        )
    )

    # =====================================================
    # SCORE INITIALIZATION
    # =====================================================

    score = 0

    score_breakdown: List[Dict[str, Any]] = []

    # =====================================================
    # A. PRIMARY MISSING EVIDENCE
    # =====================================================

    missing_count = len(
        dossier_missing
    )

    evidence_points = min(
        missing_count * 12,
        48,
    )

    score += evidence_points

    score_breakdown.append(
        {
            "component": (
                "Primary dossier missing information"
            ),
            "count": missing_count,
            "points": evidence_points,
        }
    )

    # =====================================================
    # B. ADDITIONAL COMPLIANCE
    # =====================================================

    compliance_points = min(
        len(additional_compliance) * 8,
        16,
    )

    score += compliance_points

    score_breakdown.append(
        {
            "component": (
                "Additional compliance gaps"
            ),
            "count": len(
                additional_compliance
            ),
            "points": compliance_points,
        }
    )

    # =====================================================
    # C. ADDITIONAL TRACEABILITY
    # =====================================================

    traceability_points = min(
        len(additional_traceability) * 5,
        10,
    )

    score += traceability_points

    score_breakdown.append(
        {
            "component": (
                "Additional traceability gaps"
            ),
            "count": len(
                additional_traceability
            ),
            "points": traceability_points,
        }
    )

    # =====================================================
    # D. HUMAN REVIEW
    # =====================================================

    human_review_detected = (
        "human review" in _clean_text(
            compliance_report
        )
        or "human_review" in _clean_text(
            compliance_report
        )
        or any(
            _canonical_issue(item)
            == "export certificate"
            for item in dossier_missing
        )
    )

    score_breakdown.append(
        {
            "component": (
                "Explicit human review requirement"
            ),
            "count": (
                1
                if human_review_detected
                else 0
            ),
            "points": 0,
            "note": (
                "Flag only; not separately scored "
                "to prevent double-counting."
            ),
        }
    )

    # =====================================================
    # E. INCOMPLETE / PARTIALLY TRACED
    # =====================================================

    incomplete_state = (
        _contains_phrase(
            evidence_report,
            [
                "evidence status: incomplete",
                "overall evidence status: incomplete",
                "incomplete",
            ],
        )
        or _contains_phrase(
            traceability_report,
            [
                "partially_traced",
                "partially traced",
            ],
        )
    )

    completeness_points = (
        5
        if incomplete_state
        else 0
    )

    score += completeness_points

    score_breakdown.append(
        {
            "component": (
                "Overall data completeness signal"
            ),
            "count": (
                1
                if incomplete_state
                else 0
            ),
            "points": completeness_points,
        }
    )

    # =====================================================
    # F. EXPORT CERTIFICATE
    # =====================================================

    export_certificate_missing = any(
        _canonical_issue(item)
        == "export certificate"
        for item in dossier_missing
    )

    export_certificate_points = (
        8
        if export_certificate_missing
        else 0
    )

    score += export_certificate_points

    score_breakdown.append(
        {
            "component": (
                "Export documentation readiness gap"
            ),
            "count": (
                1
                if export_certificate_missing
                else 0
            ),
            "points": export_certificate_points,
        }
    )

    # =====================================================
    # 12. FINAL SCORE LIMIT
    # =====================================================

    score = max(
        0,
        min(score, 100),
    )

    # =====================================================
    # 13. RISK BAND
    # =====================================================

    if score <= 24:

        overall_risk = "LOW"

    elif score <= 49:

        overall_risk = "MEDIUM"

    elif score <= 79:

        overall_risk = "HIGH"

    else:

        overall_risk = "CRITICAL"

    # =====================================================
    # 14. RETURN ENGINE DATA
    # =====================================================

    return {
        "score": score,
        "overall_risk": overall_risk,
        "dossier_missing": dossier_missing,
        "evidence_items": evidence_items,
        "traceability_items": traceability_items,
        "compliance_items": compliance_items,
        "additional_compliance": (
            additional_compliance
        ),
        "additional_traceability": (
            additional_traceability
        ),
        "human_review_required": (
            human_review_detected
        ),
        "score_breakdown": score_breakdown,
    }


# =========================================================
# 12. CENTRAL AI RESPONSE NORMALIZER
# =========================================================

def _normalize_risk_response(
    response: Any,
) -> RiskReport:

    # -----------------------------------------------------
    # Already RiskReport
    # -----------------------------------------------------

    if isinstance(
        response,
        RiskReport,
    ):
        return response

    # -----------------------------------------------------
    # Any Pydantic model
    # -----------------------------------------------------

    if isinstance(
        response,
        BaseModel,
    ):

        try:

            return RiskReport.model_validate(
                response.model_dump()
            )

        except Exception:
            pass

    # -----------------------------------------------------
    # Dictionary
    # -----------------------------------------------------

    if isinstance(
        response,
        dict,
    ):

        return RiskReport.model_validate(
            response
        )

    # -----------------------------------------------------
    # Object containing output_text
    # -----------------------------------------------------

    output_text = getattr(
        response,
        "output_text",
        None,
    )

    if output_text:

        return RiskReport.model_validate_json(
            output_text
        )

    # -----------------------------------------------------
    # JSON string
    # -----------------------------------------------------

    if isinstance(
        response,
        str,
    ):

        return RiskReport.model_validate_json(
            response
        )

    raise RuntimeError(
        "Central AI Service returned an unsupported "
        "Risk Agent response format."
    )


# =========================================================
# 13. CENTRAL AI SERVICE ROUTER
# =========================================================

def _call_central_ai(
    prompt: str,
) -> RiskReport:
    """
    Locate the structured-generation function exposed
    by services/ai_service.py.
    """

    candidate_functions = [
        "generate_structured",
        "generate_structured_output",
        "generate_json",
        "generate_structured_response",
        "generate_response",
        "generate",
    ]

    # =====================================================
    # MODULE FUNCTIONS
    # =====================================================

    for function_name in candidate_functions:

        function = getattr(
            central_ai,
            function_name,
            None,
        )

        if not callable(function):
            continue

        print(
            f"🔗 Central AI Service: using "
            f"{function_name}()"
        )

        return _execute_service_function(
            function,
            prompt,
        )

    # =====================================================
    # OPTIONAL SERVICE CLASSES
    # =====================================================

    service_classes = [
        "CentralAIService",
        "AIService",
        "GeminiService",
    ]

    for class_name in service_classes:

        service_class = getattr(
            central_ai,
            class_name,
            None,
        )

        if service_class is None:
            continue

        try:

            service_instance = service_class()

        except TypeError as error:

            raise RuntimeError(
                f"Found {class_name}, but it could not "
                f"be initialized automatically: {error}"
            ) from error

        for function_name in candidate_functions:

            function = getattr(
                service_instance,
                function_name,
                None,
            )

            if not callable(function):
                continue

            print(
                f"🔗 Central AI Service: "
                f"{class_name}.{function_name}()"
            )

            return _execute_service_function(
                function,
                prompt,
            )

    # =====================================================
    # NOTHING FOUND
    # =====================================================

    available = [
        name
        for name in dir(central_ai)
        if not name.startswith("_")
    ]

    raise RuntimeError(
        "Could not find a compatible structured-generation "
        "function in services/ai_service.py.\n\n"
        f"Available public names: {available}\n\n"
        "Expected one of:\n"
        "generate_structured()\n"
        "generate_structured_output()\n"
        "generate_json()\n"
    )


# =========================================================
# 14. EXECUTE CENTRAL AI FUNCTION
# =========================================================

def _execute_service_function(
    function,
    prompt: str,
) -> RiskReport:

    try:

        signature = inspect.signature(
            function
        )

        parameters = signature.parameters

        kwargs: Dict[str, Any] = {}

        # -------------------------------------------------
        # Prompt parameter
        # -------------------------------------------------

        if "prompt" in parameters:

            kwargs["prompt"] = prompt

        elif "input" in parameters:

            kwargs["input"] = prompt

        elif "text" in parameters:

            kwargs["text"] = prompt

        elif "user_prompt" in parameters:

            kwargs["user_prompt"] = prompt

        else:

            response = function(
                prompt
            )

            return _normalize_risk_response(
                response
            )

        # -------------------------------------------------
        # Response schema/model
        # -------------------------------------------------

        schema_json = (
            RiskReport.model_json_schema()
        )

        if "response_model" in parameters:

            kwargs["response_model"] = (
                RiskReport
            )

        elif "output_model" in parameters:

            kwargs["output_model"] = (
                RiskReport
            )

        elif "schema" in parameters:

            kwargs["schema"] = RiskReport

        elif "model_schema" in parameters:

            kwargs["model_schema"] = (
                schema_json
            )

        elif "response_schema" in parameters:

            kwargs["response_schema"] = (
                schema_json
            )

        elif "output_schema" in parameters:

            kwargs["output_schema"] = (
                schema_json
            )

        # -------------------------------------------------
        # Execute
        # -------------------------------------------------

        response = function(
            **kwargs
        )

        # -------------------------------------------------
        # Protect against async service
        # -------------------------------------------------

        if inspect.iscoroutine(
            response
        ):

            raise RuntimeError(
                "Central AI Service returned a coroutine. "
                "The Risk Agent expects a synchronous "
                "service method."
            )

        # -------------------------------------------------
        # Normalize
        # -------------------------------------------------

        try:

            return _normalize_risk_response(
                response
            )

        except ValidationError as error:

            print(
                "❌ Central AI Service returned an invalid "
                "RiskReport structure."
            )

            raise RuntimeError(
                "Invalid structured risk output received "
                "from Central AI Service."
            ) from error

    except ValidationError:

        raise

    except RuntimeError:

        raise

    except Exception as error:

        raise RuntimeError(
            "Risk Agent could not execute the "
            f"Central AI Service: {error}"
        ) from error


# =========================================================
# 15. LOCAL DETERMINISTIC FALLBACK
# =========================================================

def _build_fallback_report(
    product: str,
    risk_data: Dict[str, Any],
) -> RiskReport:
    """
    Local fallback used when Gemini is unavailable.

    The deterministic score remains authoritative.
    """

    risks: List[RiskItem] = []

    risk_counter = 1

    # =====================================================
    # PRIMARY DOSSIER GAPS
    # =====================================================

    for issue in risk_data[
        "dossier_missing"
    ]:

        canonical = _canonical_issue(
            issue
        )

        # -----------------------------------------------
        # Category and severity
        # -----------------------------------------------

        if canonical == "export certificate":

            category = "COMPLIANCE"
            severity = "HIGH"

        elif canonical == "material origin":

            category = "TRACEABILITY"
            severity = "HIGH"

        elif canonical == "batch id":

            category = "TRACEABILITY"
            severity = "HIGH"

        elif canonical == "energy record":

            category = "EVIDENCE"
            severity = "MEDIUM"

        else:

            category = "EVIDENCE"
            severity = "MEDIUM"

        # -----------------------------------------------
        # Human review
        # -----------------------------------------------

        requires_review = (
            canonical == "export certificate"
        )

        # -----------------------------------------------
        # Fallback risk
        # -----------------------------------------------

        risks.append(
            RiskItem(
                risk_id=(
                    f"RISK-{risk_counter:02d}"
                ),

                category=category,

                severity=severity,

                issue=(
                    f"Missing evidence: {issue}"
                ),

                trigger=(
                    f"Product dossier explicitly lists "
                    f"'{issue}' as missing."
                ),

                affected_area=(
                    "Export readiness and "
                    "evidence completeness"
                ),

                rationale=(
                    "The primary dossier does not contain "
                    "the required evidence item."
                ),

                recommended_mitigation=(
                    f"Collect and attach the missing evidence "
                    f"for '{issue}' before final "
                    "export-readiness assessment."
                ),

                human_review_required=(
                    requires_review
                ),
            )
        )

        risk_counter += 1

    # =====================================================
    # HUMAN REVIEW RISK
    # =====================================================

    if risk_data[
        "human_review_required"
    ]:

        # Only add a separate human-review item when the
        # dossier does NOT already contain an export
        # certificate gap.

        export_gap_exists = any(
            _canonical_issue(item)
            == "export certificate"
            for item in risk_data[
                "dossier_missing"
            ]
        )

        if not export_gap_exists:

            risks.append(
                RiskItem(
                    risk_id=(
                        f"RISK-{risk_counter:02d}"
                    ),

                    category="COMPLIANCE",

                    severity="HIGH",

                    issue=(
                        "Destination-market requirements "
                        "require human review."
                    ),

                    trigger=(
                        "Compliance Agent explicitly requested "
                        "additional human review."
                    ),

                    affected_area=(
                        "Market-specific compliance decision"
                    ),

                    rationale=(
                        "The supplied evidence is insufficient "
                        "for a final regulatory determination."
                    ),

                    recommended_mitigation=(
                        "Review the applicable official "
                        "destination-market requirements "
                        "and confirm the exact obligations."
                    ),

                    human_review_required=True,
                )
            )

    # =====================================================
    # PRIORITY ACTIONS
    # =====================================================

    actions: List[str] = []

    for issue in risk_data[
        "dossier_missing"
    ]:

        actions.append(
            f"Collect missing evidence: {issue}."
        )

    if risk_data[
        "human_review_required"
    ]:

        actions.append(
            "Perform human review of "
            "destination-market requirements."
        )

    if not actions:

        actions.append(
            "Perform final evidence and "
            "compliance validation."
        )

    # =====================================================
    # DECISION SUMMARY
    # =====================================================

    decision_summary = (
        f"Deterministic risk assessment for "
        f"{product}: "
        f"{risk_data['overall_risk']} with score "
        f"{risk_data['score']}/100. "
        "The score is calculated from documented "
        "evidence and readiness signals using "
        "TraceX deterministic risk rules rather "
        "than an arbitrary AI-generated score."
    )

    return RiskReport(
        product=product,

        overall_risk=(
            risk_data["overall_risk"]
        ),

        risk_score=(
            risk_data["score"]
        ),

        risks=risks,

        top_priority_actions=actions,

        decision_summary=decision_summary,
    )


# =========================================================
# 16. PRODUCT IDENTITY CONSISTENCY
# =========================================================

def _sanitize_product_identity(
    report: RiskReport,
    product: str,
) -> RiskReport:
    """
    Ensure the final RiskReport consistently uses the exact
    canonical product identity extracted from the dossier.

    Gemini may occasionally mention "Not Specified" inside
    explanatory text even when the product is known.

    This post-processing layer prevents that inconsistency
    from reaching the Verification Agent.
    """

    canonical_product = str(
        product or "Unknown Product"
    ).strip()

    # -----------------------------------------------------
    # Always enforce structured product field.
    # -----------------------------------------------------

    report.product = canonical_product

    # -----------------------------------------------------
    # Text sanitizer
    # -----------------------------------------------------

    def sanitize_text(value: str) -> str:

        if not value:
            return value

        text = str(value)

        # Example:
        # Product is 'Not Specified'
        # ->
        # Product is 'Denim Pants'
        text = re.sub(
            r"(?i)(Product\s+is\s+)[\"']?Not Specified[\"']?",
            rf"\1'{canonical_product}'",
            text,
        )

        # Example:
        # Product: Not Specified
        text = re.sub(
            r"(?i)(Product\s*:\s*)Not Specified",
            rf"\1{canonical_product}",
            text,
        )

        # Example:
        # Product field is empty
        text = re.sub(
            r"(?i)(product\s+field\s+is\s+empty)",
            f"product identity is '{canonical_product}'",
            text,
        )

        # Example:
        # product is unspecified
        text = re.sub(
            r"(?i)(product\s+is\s+)(unspecified|unknown)",
            rf"\1'{canonical_product}'",
            text,
        )

        return text

    # -----------------------------------------------------
    # Sanitize decision summary
    # -----------------------------------------------------

    report.decision_summary = sanitize_text(
        report.decision_summary
    )

    # -----------------------------------------------------
    # Sanitize priority actions
    # -----------------------------------------------------

    report.top_priority_actions = [
        sanitize_text(action)
        for action in report.top_priority_actions
    ]

    # -----------------------------------------------------
    # Sanitize risk items
    # -----------------------------------------------------

    for risk_item in report.risks:

        risk_item.issue = sanitize_text(
            risk_item.issue
        )

        risk_item.trigger = sanitize_text(
            risk_item.trigger
        )

        risk_item.affected_area = sanitize_text(
            risk_item.affected_area
        )

        risk_item.rationale = sanitize_text(
            risk_item.rationale
        )

        risk_item.recommended_mitigation = sanitize_text(
            risk_item.recommended_mitigation
        )

    return report


# =========================================================
# 17. MAIN RISK AGENT
# =========================================================

def run_risk_agent(
    product_dossier: str,
    evidence_report: str,
    traceability_report: str,
    compliance_report: str,
) -> RiskReport:

    # =====================================================
    # STEP 1: DETERMINISTIC CALCULATION
    # =====================================================

    risk_data = (
        calculate_deterministic_risk(
            product_dossier=product_dossier,
            evidence_report=evidence_report,
            traceability_report=traceability_report,
            compliance_report=compliance_report,
        )
    )

    product = _extract_product(
        product_dossier
    )

    deterministic_score = risk_data[
        "score"
    ]

    deterministic_level = risk_data[
        "overall_risk"
    ]

    # =====================================================
    # PRINT SCORE
    # =====================================================

    print(
        f"\n📊 Deterministic Risk Score: "
        f"{deterministic_score}/100"
    )

    print(
        f"🚦 Deterministic Risk Level: "
        f"{deterministic_level}"
    )

    print(
        "\n📐 Score Breakdown:"
    )

    for item in risk_data[
        "score_breakdown"
    ]:

        print(
            f"   - {item['component']}: "
            f"+{item['points']}"
        )

    # =====================================================
    # STEP 2: AI EXPLANATION PROMPT
    # =====================================================

    prompt = f"""
You are the Risk Agent inside TraceX AI.

Your role is to explain and structure the risks associated
with an export product using the supplied evidence.

=========================================================
IMPORTANT ARCHITECTURE RULE
=========================================================

The numeric risk score and overall risk level have already
been calculated by TraceX's deterministic risk engine.

YOU MUST USE THESE EXACT VALUES.

Deterministic risk score:

{deterministic_score}

Deterministic overall risk:

{deterministic_level}

DO NOT:

- invent a different score
- recalculate the score
- override the score
- change the risk level

=========================================================
PRODUCT IDENTITY RULE
=========================================================

The canonical product identity is:

{product}

The structured `product` field MUST contain exactly this
value.

When referring to the product anywhere in the RiskReport,
use the exact canonical product identity above.

Never output:

- Not Specified
- Unknown Product
- an empty product
- a different product name

when the canonical product identity above is available.

=========================================================
PRODUCT
=========================================================

{product}

=========================================================
PRODUCT DOSSIER
=========================================================

{product_dossier}

=========================================================
EVIDENCE AGENT
=========================================================

{evidence_report}

=========================================================
TRACEABILITY AGENT
=========================================================

{traceability_report}

=========================================================
COMPLIANCE AGENT
=========================================================

{compliance_report}

=========================================================
DETERMINISTIC SCORE BREAKDOWN
=========================================================

{risk_data["score_breakdown"]}

=========================================================
RISK RULES
=========================================================

1. Use only supplied information.

2. Never invent:

   - regulations
   - certificates
   - supplier facts
   - product facts
   - customs outcomes
   - legal conclusions

3. Missing evidence creates an evidence/readiness risk.

4. Missing evidence does NOT automatically mean:

   - shipment rejection
   - illegality
   - customs refusal
   - market prohibition
   - failed clearance

5. Clearly distinguish:

   - TRACEABILITY
   - EVIDENCE
   - COMPLIANCE
   - DOCUMENTATION
   - DATA_QUALITY
   - OPERATIONAL

6. Every risk must include:

   - risk_id
   - category
   - severity
   - issue
   - trigger
   - affected_area
   - rationale
   - recommended_mitigation
   - human_review_required

7. Human review must be true whenever the supplied
   information is insufficient for a reliable regulatory
   or market-specific conclusion.

8. Do not double-count the same underlying issue merely
   because multiple upstream agents mention it.

9. Keep recommendations practical and exporter-focused.

10. The decision summary must state that the numeric score
    comes from TraceX deterministic evidence/risk rules.

11. Keep product identity consistent with the canonical
    product name provided above.

12. If any upstream agent contains an incorrect product
    name such as "Not Specified", do not repeat it.
    Use the canonical product identity from this prompt.

=========================================================
REQUIRED OUTPUT
=========================================================

Return ONLY a valid structured RiskReport.

Use EXACTLY:

overall_risk = "{deterministic_level}"

risk_score = {deterministic_score}

product = "{product}"

Do not modify these values.
"""

    # =====================================================
    # STEP 3: CENTRAL AI
    # =====================================================

    try:

        print(
            "\n🤖 Risk Agent → Central AI Service"
        )

        report = _call_central_ai(
            prompt
        )

        # -------------------------------------------------
        # Deterministic values remain authoritative.
        # -------------------------------------------------

        report.overall_risk = (
            deterministic_level
        )

        report.risk_score = (
            deterministic_score
        )

        # -------------------------------------------------
        # CRITICAL FIX:
        # Enforce canonical product identity everywhere.
        # -------------------------------------------------

        report = _sanitize_product_identity(
            report,
            product,
        )

        # -------------------------------------------------
        # Add deterministic explanation if absent.
        # -------------------------------------------------

        deterministic_note = (
            f"TraceX deterministic risk engine "
            f"calculated {deterministic_level} risk "
            f"at {deterministic_score}/100 from "
            f"documented evidence/readiness signals."
        )

        existing_summary = (
            report.decision_summary or ""
        )

        if deterministic_note.lower() not in (
            existing_summary
        ).lower():

            report.decision_summary = (
                existing_summary.strip()
                + " "
                + deterministic_note
            )

        # Run one final product sanitization after
        # adding the deterministic note.
        report = _sanitize_product_identity(
            report,
            product,
        )

        print(
            "\n✅ Risk Agent completed using "
            "Central AI Service."
        )

        return report

    # =====================================================
    # STEP 4: LOCAL FALLBACK
    # =====================================================

    except Exception as error:

        print(
            "\n⚠️ Central AI Risk generation unavailable."
        )

        print(
            f"   Reason: {error}"
        )

        print(
            "➡️ Using deterministic local fallback report."
        )

        return _build_fallback_report(
            product=product,
            risk_data=risk_data,
        )


# =========================================================
# 18. LOCAL TEST
# =========================================================

if __name__ == "__main__":

    product_dossier = """
Product: 100% Cotton T-Shirt

Supplier: ABC Textile Mills

Available evidence:

- Supplier registration document

- Cotton material declaration

- Lab test report

Missing information:

- Cotton farm/origin

- Manufacturing batch ID

- Energy consumption record

- Required export certificate

Destination market:

European Union

"""

    evidence_report = """
Overall evidence status: INCOMPLETE

Critical gaps:

- Energy consumption record

- Recycling information

- Required export certificate

"""

    traceability_report = """
Traceability status: PARTIALLY_TRACED

Gaps:

- Cotton farm / raw material origin is missing

- Manufacturing batch ID is missing

- Energy consumption record is missing

"""

    compliance_report = """
Overall status: GAPS_FOUND

Critical gaps:

- Missing manufacturing batch ID

- Missing cotton farm/origin evidence

- Missing required export certificate

Human review:

European Union specific market requirements require
additional review.

"""

    # =====================================================
    # TEST HEADER
    # =====================================================

    print("\n")

    print(
        "==============================================="
    )

    print(
        "          TRACEX AI - RISK AGENT"
    )

    print(
        "==============================================="
    )

    # =====================================================
    # RUN TEST
    # =====================================================

    try:

        report = run_risk_agent(
            product_dossier=product_dossier,
            evidence_report=evidence_report,
            traceability_report=traceability_report,
            compliance_report=compliance_report,
        )

        print(
            "\n-----------------------------------------------"
        )

        print(
            "RISK RESULT"
        )

        print(
            "-----------------------------------------------\n"
        )

        print(
            report.model_dump_json(
                indent=2
            )
        )

        print(
            "\n✅ Risk Agent executed successfully."
        )

    except Exception as error:

        print(
            "\n❌ Risk Agent failed."
        )

        print(
            f"Error: {error}"
        )

        sys.exit(1)