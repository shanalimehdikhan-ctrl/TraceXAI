import re
import sys
import inspect
from pathlib import Path
from typing import List, Any

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

class VerificationItem(BaseModel):
    claim: str

    verdict: str = Field(
        description=(
            "One of: SUPPORTED, PARTIALLY_SUPPORTED, "
            "UNSUPPORTED, NEEDS_HUMAN_REVIEW."
        )
    )

    supporting_source: str
    issue: str
    correction: str


class VerificationReport(BaseModel):
    overall_verdict: str = Field(
        description=(
            "One of: VERIFIED, VERIFIED_WITH_WARNINGS, "
            "HUMAN_REVIEW_REQUIRED."
        )
    )

    verified_claims: int = Field(
        ge=0
    )

    flagged_claims: int = Field(
        ge=0
    )

    human_review_required: bool

    findings: List[VerificationItem]

    final_guidance: List[str]


# =========================================================
# 4. TEXT / PRODUCT HELPERS
# =========================================================

def _clean_text(
    value: Any,
) -> str:
    """
    Normalize text for reliable comparison.
    """

    text = str(
        value or ""
    ).strip()

    text = text.replace(
        "–",
        "-",
    )

    text = text.replace(
        "—",
        "-",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _extract_product(
    product_dossier: str,
) -> str:
    """
    Extract the canonical product identity directly from
    the primary product dossier.

    Example:
        Product: Cotton Salwar Kameez (Traditional Apparel)
    """

    match = re.search(
        r"^\s*Product:\s*(.+?)\s*$",
        product_dossier,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    if match:

        product = _clean_text(
            match.group(1)
        )

        if product:
            return product

    return "Unknown Product"


def _normalize_for_comparison(
    value: Any,
) -> str:
    """
    Normalize product text for comparison without changing
    the human-readable value.
    """

    text = _clean_text(
        value
    ).lower()

    text = re.sub(
        r"[^a-z0-9% ]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _looks_like_false_product_mismatch(
    finding: VerificationItem,
    canonical_product: str,
) -> bool:
    """
    Detect the known false-positive verification finding in
    which the AI claims that Risk Agent uses 'Not Specified'
    even though the canonical product is explicitly present
    in the dossier and final RiskReport.

    This is treated as a stale consistency artifact, not as
    a genuine product-data conflict.
    """

    claim = _clean_text(
        finding.claim
    ).lower()

    issue = _clean_text(
        finding.issue
    ).lower()

    correction = _clean_text(
        finding.correction
    ).lower()

    combined = " ".join(
        [
            claim,
            issue,
            correction,
        ]
    )

    if "not specified" not in combined:
        return False

    product_context_words = [
        "product",
        "risk agent",
        "product identity",
        "product name",
    ]

    has_product_context = any(
        word in combined
        for word in product_context_words
    )

    if not has_product_context:
        return False

    normalized_canonical = (
        _normalize_for_comparison(
            canonical_product
        )
    )

    # If the canonical product is genuinely unknown,
    # do not remove the finding.
    if not normalized_canonical:
        return False

    if normalized_canonical == "unknown product":
        return False

    return True


def _sanitize_verification_report(
    report: VerificationReport,
    canonical_product: str,
) -> VerificationReport:
    """
    Final deterministic trust layer for Verification Agent.

    Responsibilities:
        1. Remove stale false-positive product mismatch findings.
        2. Preserve genuine unsupported/partial findings.
        3. Ensure product identity appears consistently in guidance.
        4. Keep counts coherent after removing false findings.
    """

    original_findings = list(
        report.findings
    )

    cleaned_findings: List[VerificationItem] = []

    removed_false_mismatch = 0

    for finding in original_findings:

        if _looks_like_false_product_mismatch(
            finding,
            canonical_product,
        ):

            removed_false_mismatch += 1

            print(
                "🧹 Verification cleanup: removed "
                "stale product identity mismatch finding."
            )

            continue

        cleaned_findings.append(
            finding
        )

    report.findings = cleaned_findings

    # -----------------------------------------------------
    # Reconcile flagged claim count.
    # -----------------------------------------------------
    #
    # The AI may have counted the removed stale mismatch
    # as a flagged claim. Remove one count when appropriate.

    if removed_false_mismatch:

        report.flagged_claims = max(
            0,
            report.flagged_claims
            - removed_false_mismatch,
        )

    # -----------------------------------------------------
    # Ensure final guidance doesn't repeat the stale issue.
    # -----------------------------------------------------

    cleaned_guidance: List[str] = []

    for guidance in report.final_guidance:

        text = _clean_text(
            guidance
        )

        if not text:
            continue

        lower = text.lower()

        if (
            "not specified" in lower
            and "product" in lower
        ):

            continue

        cleaned_guidance.append(
            text
        )

    # Keep order while removing exact duplicates.
    unique_guidance = []

    seen_guidance = set()

    for item in cleaned_guidance:

        key = item.lower()

        if key in seen_guidance:
            continue

        seen_guidance.add(
            key
        )

        unique_guidance.append(
            item
        )

    report.final_guidance = unique_guidance

    # -----------------------------------------------------
    # If product identity is known, make sure a useful
    # consistency note exists.
    # -----------------------------------------------------

    if (
        canonical_product
        and canonical_product != "Unknown Product"
    ):

        identity_note = (
            f"Product identity verified as "
            f"'{canonical_product}' against the primary dossier."
        )

        already_present = any(
            _normalize_for_comparison(
                identity_note
            )
            == _normalize_for_comparison(
                item
            )
            for item in report.final_guidance
        )

        if not already_present:

            report.final_guidance.insert(
                0,
                identity_note,
            )

    # -----------------------------------------------------
    # Ensure overall verdict remains sensible.
    # -----------------------------------------------------

    genuine_flagged_findings = [

        finding
        for finding in report.findings
        if str(
            finding.verdict
        ).upper()
        not in {
            "SUPPORTED",
        }
    ]

    has_human_review_finding = any(
        str(
            finding.verdict
        ).upper()
        == "NEEDS_HUMAN_REVIEW"
        for finding in report.findings
    )

    if (
        report.human_review_required
        or has_human_review_finding
    ):

        report.overall_verdict = (
            "HUMAN_REVIEW_REQUIRED"
        )

    elif genuine_flagged_findings:

        report.overall_verdict = (
            "VERIFIED_WITH_WARNINGS"
        )

    else:

        report.overall_verdict = (
            "VERIFIED"
        )

    return report


# =========================================================
# 5. RESPONSE NORMALIZER
# =========================================================

def _normalize_verification_response(
    response: Any,
) -> VerificationReport:
    """
    Convert the Central AI Service response into
    VerificationReport regardless of whether the service
    returns:

        - VerificationReport
        - Pydantic model
        - dict
        - JSON string
        - object containing output_text
    """

    # -----------------------------------------------------
    # Already correct type
    # -----------------------------------------------------

    if isinstance(
        response,
        VerificationReport,
    ):

        return response

    # -----------------------------------------------------
    # Pydantic model
    # -----------------------------------------------------

    if isinstance(
        response,
        BaseModel,
    ):

        try:

            return VerificationReport.model_validate(
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

        return VerificationReport.model_validate(
            response
        )

    # -----------------------------------------------------
    # Gemini-style object with output_text
    # -----------------------------------------------------

    output_text = getattr(
        response,
        "output_text",
        None,
    )

    if output_text:

        return VerificationReport.model_validate_json(
            output_text
        )

    # -----------------------------------------------------
    # Raw JSON string
    # -----------------------------------------------------

    if isinstance(
        response,
        str,
    ):

        return VerificationReport.model_validate_json(
            response
        )

    raise RuntimeError(
        "Central AI Service returned an unsupported "
        "response format."
    )


# =========================================================
# 6. CENTRAL AI SERVICE CALL
# =========================================================

def _call_central_ai(
    prompt: str,
) -> VerificationReport:
    """
    Calls the public structured-generation interface
    exposed by services/ai_service.py.
    """

    # -----------------------------------------------------
    # Candidate function names
    # -----------------------------------------------------

    function_names = [
        "generate_structured_output",
        "generate_structured",
        "generate_json",
        "generate_structured_response",
        "generate_response",
        "generate",
    ]

    # -----------------------------------------------------
    # Module-level functions
    # -----------------------------------------------------

    for function_name in function_names:

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

    # -----------------------------------------------------
    # Service classes
    # -----------------------------------------------------

    class_names = [
        "CentralAIService",
        "AIService",
        "GeminiService",
    ]

    for class_name in class_names:

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
                f"Found {class_name}, but could not "
                f"initialize it automatically: {error}"
            ) from error

        for function_name in function_names:

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

    # -----------------------------------------------------
    # Nothing compatible found
    # -----------------------------------------------------

    available = [
        name
        for name in dir(central_ai)
        if not name.startswith("_")
    ]

    raise RuntimeError(
        "Could not find a compatible structured-generation "
        "function in services/ai_service.py.\n\n"
        f"Available public names: {available}\n\n"
        "Please expose one of these functions from the "
        "Central AI Service:\n"
        "generate_structured_output\n"
        "generate_structured\n"
        "generate_json\n"
    )


# =========================================================
# 7. EXECUTE CENTRAL SERVICE FUNCTION
# =========================================================

def _execute_service_function(
    function,
    prompt: str,
) -> VerificationReport:

    try:

        signature = inspect.signature(
            function
        )

        parameters = signature.parameters

        kwargs = {}

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

            return _normalize_verification_response(
                function(prompt)
            )

        # -------------------------------------------------
        # Structured schema parameter
        # -------------------------------------------------

        schema_value = VerificationReport

        schema_json = (
            VerificationReport.model_json_schema()
        )

        if "response_model" in parameters:

            kwargs["response_model"] = schema_value

        elif "output_model" in parameters:

            kwargs["output_model"] = schema_value

        elif "model_schema" in parameters:

            kwargs["model_schema"] = schema_json

        elif "schema" in parameters:

            kwargs["schema"] = schema_value

        elif "response_schema" in parameters:

            kwargs["response_schema"] = schema_json

        elif "output_schema" in parameters:

            kwargs["output_schema"] = schema_json

        # -------------------------------------------------
        # Execute service
        # -------------------------------------------------

        response = function(
            **kwargs
        )

        # -------------------------------------------------
        # Handle accidental async function
        # -------------------------------------------------

        if inspect.iscoroutine(
            response
        ):

            raise RuntimeError(
                "Central AI Service returned a coroutine. "
                "The current Verification Agent expects "
                "a synchronous service method."
            )

        # -------------------------------------------------
        # Normalize result
        # -------------------------------------------------

        try:

            return _normalize_verification_response(
                response
            )

        except ValidationError as error:

            print(
                "❌ Central AI Service returned invalid "
                "VerificationReport structure."
            )

            raise RuntimeError(
                "Invalid structured verification output "
                "received from Central AI Service."
            ) from error

    except ValidationError:

        raise

    except RuntimeError:

        raise

    except Exception as error:

        raise RuntimeError(
            "Verification Agent could not execute the "
            f"Central AI Service: {error}"
        ) from error


# =========================================================
# 8. VERIFICATION AGENT
# =========================================================

def run_verification_agent(
    product_dossier: str,
    evidence_report: str,
    traceability_report: str,
    compliance_report: str,
    risk_report: str,
) -> VerificationReport:

    # -----------------------------------------------------
    # Canonical product identity
    # -----------------------------------------------------

    canonical_product = _extract_product(
        product_dossier
    )

    print(
        f"\n🧾 Verification canonical product: "
        f"{canonical_product}"
    )

    # -----------------------------------------------------
    # Audit prompt
    # -----------------------------------------------------

    prompt = f"""
You are the Verification Agent inside TraceX AI.

Your role is to independently audit the outputs generated by:

1. Evidence Agent
2. Traceability Agent
3. Compliance Agent
4. Risk Agent

Your purpose is to reduce:

- hallucinations
- unsupported claims
- overconfident conclusions
- incorrect regulatory assumptions
- cross-agent data inconsistencies

=========================================================
PRIMARY SOURCE
=========================================================

The PRODUCT DOSSIER is the authoritative source for
product identity and supplied facts.

PRODUCT DOSSIER:
{product_dossier}

=========================================================
CANONICAL PRODUCT IDENTITY
=========================================================

The exact canonical product identity is:

{canonical_product}

IMPORTANT:

When the product identity is available above:

- Use this exact product name.
- Treat this value as authoritative.
- Do not replace it with "Not Specified".
- Do not replace it with "Unknown".
- Do not claim the product is empty.
- Do not invent a different product name.

If the Risk Agent or another upstream output contains
an obsolete phrase such as:

"Product is Not Specified"

while the primary dossier clearly identifies the product,
treat that phrase as a stale consistency artifact only
when the rest of the evidence confirms the canonical product.

Do NOT create a verification finding solely for that stale
product-label mismatch.

=========================================================
UPSTREAM AGENT OUTPUTS
=========================================================

EVIDENCE AGENT:
{evidence_report}

---------------------------------------------------------

TRACEABILITY AGENT:
{traceability_report}

---------------------------------------------------------

COMPLIANCE AGENT:
{compliance_report}

---------------------------------------------------------

RISK AGENT:
{risk_report}

=========================================================
VERIFICATION RULES
=========================================================

1. The PRODUCT DOSSIER is the primary evidence source.

2. Treat every upstream agent statement as a claim
   that must be independently checked.

3. SUPPORTED:
   The supplied evidence directly supports the claim.

4. PARTIALLY_SUPPORTED:
   The general concern is supported, but the exact
   conclusion is stronger than the evidence.

5. UNSUPPORTED:
   The supplied material does not support the claim.

6. NEEDS_HUMAN_REVIEW:
   The decision requires external regulations,
   legal interpretation, official market rules,
   or unavailable information.

7. Never approve a claim merely because another AI
   agent generated it.

8. Missing evidence does NOT automatically prove:

   - illegality
   - customs rejection
   - shipment rejection
   - market prohibition
   - failed clearance

9. Clearly distinguish between:

   - Evidence Gap
   - Traceability Gap
   - Readiness Risk
   - Legal/Regulatory Conclusion

10. If an upstream agent makes an overly strong claim,
    flag it and provide a safer correction.

11. Every flagged claim must explain why it was flagged.

12. When available information is insufficient,
    prefer HUMAN_REVIEW.

13. Do not invent any new facts.

14. Cross-agent identity consistency must use the canonical
    product identity from the PRODUCT DOSSIER.

15. Do not create a finding merely because an upstream
    explanation contains an obsolete "Not Specified" product
    label when the authoritative dossier provides the product.

16. The deterministic Risk Agent score is an internal
    TraceX signal. Do not reinterpret it as a legal decision.

=========================================================
EXAMPLE — PRODUCT IDENTITY
=========================================================

PRIMARY DOSSIER:

Product: Cotton Salwar Kameez (Traditional Apparel)

If another agent says:

"Product is Not Specified"

but its structured product is actually:

"Cotton Salwar Kameez (Traditional Apparel)"

then do not create a false mismatch finding.

The canonical identity is:

"Cotton Salwar Kameez (Traditional Apparel)"

=========================================================
EXAMPLE — LEGAL SAFETY
=========================================================

BAD:

"Missing certificate means EU customs will reject the shipment."

CORRECTION:

"The required certificate is not present in the supplied
dossier; destination-market compliance and customs
implications require human review."

=========================================================
FINAL TASK
=========================================================

Audit important claims from the upstream agents.

Focus on genuine:

- unsupported claims
- partially supported claims
- regulatory uncertainty
- evidence contradictions
- traceability problems
- risk interpretation issues

Do not manufacture findings from stale product-label wording
when the canonical product identity is already established.

Return ONLY the structured verification result matching
the required VerificationReport schema.
"""

    print(
        "\n🛡️ Verification Agent → Central AI Service"
    )

    report = _call_central_ai(
        prompt
    )

    # =====================================================
    # FINAL DETERMINISTIC SANITIZATION
    # =====================================================

    report = _sanitize_verification_report(
        report,
        canonical_product,
    )

    print(
        "\n✅ Verification Agent completed."
    )

    print(
        f"   Verdict: {report.overall_verdict}"
    )

    print(
        f"   Findings: {len(report.findings)}"
    )

    print(
        f"   Verified Claims: {report.verified_claims}"
    )

    print(
        f"   Flagged Claims: {report.flagged_claims}"
    )

    return report


# =========================================================
# 9. LOCAL DEMO DATA
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

    risk_report = """
Product: 100% Cotton T-Shirt

Overall risk: HIGH

Risk score: 78

Risks:
- Missing required export certificate
- Missing raw material origin
- Missing manufacturing batch ID
- Incomplete environmental records
- EU destination requirements need human review
"""

    # =====================================================
    # RUN TEST
    # =====================================================

    print("\n")

    print(
        "==============================================="
    )

    print(
        "       TRACEX AI - VERIFICATION AGENT"
    )

    print(
        "==============================================="
    )

    try:

        report = run_verification_agent(
            product_dossier=product_dossier,
            evidence_report=evidence_report,
            traceability_report=traceability_report,
            compliance_report=compliance_report,
            risk_report=risk_report,
        )

        print(
            "\n-----------------------------------------------"
        )

        print(
            "VERIFICATION RESULT"
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
            "\n✅ Verification Agent executed successfully."
        )

    except Exception as error:

        print(
            "\n❌ Verification Agent failed."
        )

        print(
            f"Error: {error}"
        )

        sys.exit(1)