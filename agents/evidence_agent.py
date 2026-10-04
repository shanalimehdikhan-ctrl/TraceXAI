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
        "C:\\TraceXAI\\services\\ai_service.py"
    ) from error


# =========================================================
# 3. STRUCTURED OUTPUT MODELS
# =========================================================
class EvidenceItem(BaseModel):

    item: str = Field(
        description="Name of the evidence or information found."
    )

    status: str = Field(
        description=(
            "One of: VERIFIED, MISSING, UNCLEAR."
        )
    )

    source: str = Field(
        description=(
            "Document or data source where the evidence "
            "came from."
        )
    )

    notes: str = Field(
        description=(
            "Short explanation supporting the finding."
        )
    )


class EvidenceReport(BaseModel):

    product: str

    supplier: str

    evidence_items: List[EvidenceItem]

    overall_evidence_status: str = Field(
        description=(
            "One of: COMPLETE, INCOMPLETE, "
            "PARTIALLY_VERIFIED, HUMAN_REVIEW."
        )
    )

    critical_gaps: List[str]


# =========================================================
# 4. RESPONSE NORMALIZER
# =========================================================
def _normalize_evidence_response(
    response: Any,
) -> EvidenceReport:
    """
    Convert the Central AI Service response into
    EvidenceReport.

    Supported response formats:
        - EvidenceReport
        - Any Pydantic model
        - dict
        - JSON string
        - object with output_text
    """

    # -----------------------------------------------------
    # Already correct type
    # -----------------------------------------------------
    if isinstance(
        response,
        EvidenceReport,
    ):
        return response

    # -----------------------------------------------------
    # Generic Pydantic model
    # -----------------------------------------------------
    if isinstance(
        response,
        BaseModel,
    ):

        try:
            return EvidenceReport.model_validate(
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

        return EvidenceReport.model_validate(
            response
        )

    # -----------------------------------------------------
    # Object with output_text
    # -----------------------------------------------------
    output_text = getattr(
        response,
        "output_text",
        None,
    )

    if output_text:

        return EvidenceReport.model_validate_json(
            output_text
        )

    # -----------------------------------------------------
    # Raw JSON string
    # -----------------------------------------------------
    if isinstance(
        response,
        str,
    ):

        return EvidenceReport.model_validate_json(
            response
        )

    raise RuntimeError(
        "Central AI Service returned an unsupported "
        "Evidence Agent response format."
    )


# =========================================================
# 5. CENTRAL AI SERVICE CALLER
# =========================================================
def _call_central_ai(
    prompt: str,
) -> EvidenceReport:
    """
    Locate and execute a structured-generation function
    exposed by services/ai_service.py.
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
    # MODULE-LEVEL FUNCTIONS
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
    # NOTHING COMPATIBLE FOUND
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
# 6. EXECUTE CENTRAL SERVICE FUNCTION
# =========================================================
def _execute_service_function(
    function,
    prompt: str,
) -> EvidenceReport:

    try:

        signature = inspect.signature(
            function
        )

        parameters = signature.parameters

        kwargs: Dict[str, Any] = {}

        # -------------------------------------------------
        # Prompt argument
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

            return _normalize_evidence_response(
                response
            )

        # -------------------------------------------------
        # Structured output model/schema
        # -------------------------------------------------
        schema_json = (
            EvidenceReport.model_json_schema()
        )

        if "response_model" in parameters:

            kwargs["response_model"] = (
                EvidenceReport
            )

        elif "output_model" in parameters:

            kwargs["output_model"] = (
                EvidenceReport
            )

        elif "schema" in parameters:

            kwargs["schema"] = EvidenceReport

        elif "model_schema" in parameters:

            kwargs["model_schema"] = schema_json

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
        # Async protection
        # -------------------------------------------------
        if inspect.iscoroutine(
            response
        ):

            raise RuntimeError(
                "Central AI Service returned a coroutine. "
                "The Evidence Agent expects a "
                "synchronous service method."
            )

        # -------------------------------------------------
        # Normalize
        # -------------------------------------------------
        try:

            return _normalize_evidence_response(
                response
            )

        except ValidationError as error:

            print(
                "❌ Central AI Service returned an invalid "
                "EvidenceReport structure."
            )

            raise RuntimeError(
                "Invalid structured evidence output "
                "received from Central AI Service."
            ) from error

    except ValidationError:
        raise

    except RuntimeError:
        raise

    except Exception as error:

        raise RuntimeError(
            "Evidence Agent could not execute the "
            f"Central AI Service: {error}"
        ) from error


# =========================================================
# 7. LOCAL FALLBACK
# =========================================================
def _build_fallback_report(
    product_dossier: str,
) -> EvidenceReport:
    """
    Conservative local fallback.

    No new evidence is invented.
    """

    product = "Unknown Product"
    supplier = "Unknown Supplier"

    # -----------------------------------------------------
    # Extract product and supplier
    # -----------------------------------------------------
    for line in product_dossier.splitlines():

        stripped = line.strip()

        if stripped.lower().startswith(
            "product:"
        ):

            product = stripped.split(
                ":",
                1,
            )[1].strip()

        elif stripped.lower().startswith(
            "supplier:"
        ):

            supplier = stripped.split(
                ":",
                1,
            )[1].strip()

    # -----------------------------------------------------
    # Basic fallback items
    # -----------------------------------------------------
    evidence_items: List[EvidenceItem] = []

    if product != "Unknown Product":

        evidence_items.append(
            EvidenceItem(
                item=product,
                status="VERIFIED",
                source="Product Dossier",
                notes=(
                    "Product name is explicitly present "
                    "in the supplied dossier."
                ),
            )
        )

    if supplier != "Unknown Supplier":

        evidence_items.append(
            EvidenceItem(
                item=supplier,
                status="VERIFIED",
                source="Product Dossier",
                notes=(
                    "Supplier name is explicitly present "
                    "in the supplied dossier."
                ),
            )
        )

    # -----------------------------------------------------
    # Conservative overall result
    # -----------------------------------------------------
    return EvidenceReport(
        product=product,
        supplier=supplier,
        evidence_items=evidence_items,
        overall_evidence_status="HUMAN_REVIEW",
        critical_gaps=[
            (
                "Automated evidence assessment was "
                "unavailable."
            )
        ],
    )


# =========================================================
# 8. EVIDENCE AGENT
# =========================================================
def run_evidence_agent(
    product_dossier: str,
) -> EvidenceReport:

    # =====================================================
    # GROUNDED PROMPT
    # =====================================================
    prompt = f"""
You are the Evidence Agent inside TraceX AI.

Your job is to analyze the supplied export product dossier
and identify what evidence is present, missing, or unclear.

=========================================================
CORE PRINCIPLE
=========================================================

Use ONLY information explicitly present in the
PRODUCT DOSSIER.

Never invent evidence.

Never infer a certificate, record, supplier fact, test result,
origin, production record, or compliance status that is not
explicitly supported by the dossier.

=========================================================
STATUS DEFINITIONS
=========================================================

VERIFIED:
The evidence or information is explicitly present and
clearly supported by the dossier.

MISSING:
The dossier explicitly identifies the item as not provided,
missing, or absent.

UNCLEAR:
The dossier mentions the item, but the supplied information
is insufficient to verify it.

=========================================================
IMPORTANT SAFETY RULE
=========================================================

Do NOT turn a missing item into a legal conclusion.

For example:

BAD:
"Certificate missing, therefore shipment is illegal."

GOOD:
"Required export certificate is not present in the supplied
dossier."

Missing evidence is an evidence gap, not automatic proof
of non-compliance.

=========================================================
EXTRACTION RULES
=========================================================

Extract:

1. Product identity
2. Supplier identity
3. Material information
4. Available evidence
5. Missing information
6. Other explicitly stated evidence-related information

Every EvidenceItem must contain:

- item
- status
- source
- notes

The source should identify where the evidence was found,
such as:

- Product Dossier - Product
- Product Dossier - Supplier
- Product Dossier - Material
- Product Dossier - Available evidence
- Product Dossier - Missing information

=========================================================
OVERALL STATUS
=========================================================

Use:

COMPLETE:
The dossier provides the required evidence with no major
documented evidence gaps.

INCOMPLETE:
Important evidence is explicitly missing.

PARTIALLY_VERIFIED:
Some evidence is verified, while other information is
unclear or incomplete.

HUMAN_REVIEW:
The dossier is too ambiguous to make a reliable automated
assessment.

=========================================================
CRITICAL GAPS
=========================================================

Include the important missing or unclear items.

Do NOT invent additional gaps.

Do NOT add legal conclusions.

=========================================================
PRODUCT DOSSIER
=========================================================

{product_dossier}

=========================================================
FINAL TASK
=========================================================

Generate a structured EvidenceReport containing:

- product
- supplier
- evidence_items
- overall_evidence_status
- critical_gaps

Return ONLY the structured EvidenceReport.
"""

    print(
        "\n🔎 Evidence Agent → Central AI Service"
    )

    return _call_central_ai(
        prompt
    )


# =========================================================
# 9. SAFE EXECUTION
# =========================================================
def run_evidence_agent_safe(
    product_dossier: str,
) -> EvidenceReport:
    """
    Run the Evidence Agent with a conservative fallback
    if Central AI is unavailable.
    """

    try:

        report = run_evidence_agent(
            product_dossier
        )

        print(
            "\n✅ Evidence Agent completed using "
            "Central AI Service."
        )

        return report

    except Exception as error:

        print(
            "\n⚠️ Central AI Evidence generation unavailable."
        )

        print(
            f"   Reason: {error}"
        )

        print(
            "➡️ Using conservative local fallback."
        )

        return _build_fallback_report(
            product_dossier
        )


# =========================================================
# 10. LOCAL TEST
# =========================================================
if __name__ == "__main__":

    sample_dossier = """
Product: 100% Cotton T-Shirt
Supplier: ABC Textile Mills

Available evidence:
- Supplier registration document
- Cotton material declaration
- Lab test report

Not provided:
- Energy consumption record
- Recycling information
- One required export certificate

Destination market:
European Union
"""

    print("\n")
    print(
        "==============================================="
    )

    print(
        "          TRACEX AI - EVIDENCE AGENT"
    )

    print(
        "==============================================="
    )

    try:

        report = run_evidence_agent_safe(
            sample_dossier
        )

        print(
            "\n-----------------------------------------------"
        )

        print(
            "EVIDENCE RESULT"
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
            "\n✅ Evidence Agent executed successfully."
        )

    except Exception as error:

        print(
            "\n❌ Evidence Agent failed."
        )

        print(
            f"Error: {error}"
        )

        sys.exit(1)