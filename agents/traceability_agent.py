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
class TraceNode(BaseModel):
    entity_type: str = Field(
        description=(
            "One of: SUPPLIER, MATERIAL, PRODUCT, EVIDENCE."
        )
    )

    entity_name: str

    status: str = Field(
        description=(
            "One of: VERIFIED, MISSING, UNCLEAR."
        )
    )

    source: str

    notes: str


class TraceabilityReport(BaseModel):
    product: str

    supplier: str

    trace_chain: List[TraceNode]

    traceability_status: str = Field(
        description=(
            "One of: FULLY_TRACED, PARTIALLY_TRACED, "
            "NOT_TRACED, HUMAN_REVIEW."
        )
    )

    gaps: List[str]


# =========================================================
# 4. RESPONSE NORMALIZER
# =========================================================
def _normalize_traceability_response(
    response: Any,
) -> TraceabilityReport:
    """
    Convert Central AI Service response into
    TraceabilityReport.

    Supported:
        - TraceabilityReport
        - Pydantic model
        - dict
        - JSON string
        - object with output_text
    """

    # -----------------------------------------------------
    # Already correct type
    # -----------------------------------------------------
    if isinstance(
        response,
        TraceabilityReport,
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
            return TraceabilityReport.model_validate(
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
        return TraceabilityReport.model_validate(
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
        return TraceabilityReport.model_validate_json(
            output_text
        )

    # -----------------------------------------------------
    # JSON string
    # -----------------------------------------------------
    if isinstance(
        response,
        str,
    ):
        return TraceabilityReport.model_validate_json(
            response
        )

    raise RuntimeError(
        "Central AI Service returned an unsupported "
        "Traceability Agent response format."
    )


# =========================================================
# 5. CENTRAL AI SERVICE CALLER
# =========================================================
def _call_central_ai(
    prompt: str,
) -> TraceabilityReport:
    """
    Locate and execute the structured-generation function
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
) -> TraceabilityReport:

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

            return _normalize_traceability_response(
                response
            )

        # -------------------------------------------------
        # Structured output model/schema
        # -------------------------------------------------
        schema_json = (
            TraceabilityReport.model_json_schema()
        )

        if "response_model" in parameters:

            kwargs["response_model"] = (
                TraceabilityReport
            )

        elif "output_model" in parameters:

            kwargs["output_model"] = (
                TraceabilityReport
            )

        elif "schema" in parameters:

            kwargs["schema"] = TraceabilityReport

        elif "model_schema" in parameters:

            kwargs["model_schema"] = schema_json

        elif "response_schema" in parameters:

            kwargs["response_schema"] = schema_json

        elif "output_schema" in parameters:

            kwargs["output_schema"] = schema_json

        # -------------------------------------------------
        # Execute
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
                "The Traceability Agent expects a "
                "synchronous service method."
            )

        # -------------------------------------------------
        # Normalize response
        # -------------------------------------------------
        try:

            return _normalize_traceability_response(
                response
            )

        except ValidationError as error:

            print(
                "❌ Central AI Service returned an invalid "
                "TraceabilityReport structure."
            )

            raise RuntimeError(
                "Invalid structured traceability output "
                "received from Central AI Service."
            ) from error

    except ValidationError:
        raise

    except RuntimeError:
        raise

    except Exception as error:

        raise RuntimeError(
            "Traceability Agent could not execute the "
            f"Central AI Service: {error}"
        ) from error


# =========================================================
# 7. TRACEABILITY AGENT
# =========================================================
def run_traceability_agent(
    product_dossier: str,
) -> TraceabilityReport:

    # =====================================================
    # GROUNDED PROMPT
    # =====================================================
    prompt = f"""
You are the Traceability Agent inside TraceX AI.

Your job is to construct a factual traceability chain from
the supplied export product dossier.

=========================================================
TRACEABILITY CHAIN
=========================================================

Build this logical chain:

SUPPLIER
   ↓
MATERIAL
   ↓
PRODUCT
   ↓
EVIDENCE

=========================================================
STRICT GROUNDING RULES
=========================================================

1. Use ONLY information explicitly present in the
   PRODUCT DOSSIER.

2. Never invent:
   - supplier names
   - material origins
   - farms
   - factories
   - production batches
   - certificates
   - environmental records
   - evidence
   - dates
   - quantities

3. Do not infer a fact simply because it would be
   typical in a supply chain.

4. Every node must have a source describing where the
   information came from.

5. Use these node statuses:

   VERIFIED:
   The dossier explicitly supports the node.

   MISSING:
   The node or expected linkage is not provided.

   UNCLEAR:
   The dossier mentions something related to the node
   but the information is insufficient to verify it.

6. Identify actual traceability gaps.

7. Do not confuse:
   - missing evidence
   - legal non-compliance
   - customs rejection
   - shipment rejection

8. Missing traceability evidence does NOT automatically
   mean the product is illegal or rejected.

9. Keep the report factual, concise, and suitable for
   an exporter dashboard.

=========================================================
TRACEABILITY STATUS
=========================================================

Use:

FULLY_TRACED:
The relevant chain from supplier through material,
product, and supporting evidence is adequately supported.

PARTIALLY_TRACED:
Some important links or evidence are missing.

NOT_TRACED:
The supplied dossier does not provide enough information
to establish a meaningful traceability chain.

HUMAN_REVIEW:
The information is ambiguous enough that human review
is required before making a reliable traceability decision.

=========================================================
NODE RULES
=========================================================

SUPPLIER:
Use the explicit supplier name from the dossier.

MATERIAL:
Use the explicit material/composition information.

PRODUCT:
Use the explicit product name.

EVIDENCE:
Create evidence nodes ONLY for evidence explicitly listed
in the dossier.

If an important traceability linkage is explicitly listed
under missing information, mark the relevant node as
MISSING or UNCLEAR rather than inventing the missing value.

=========================================================
PRODUCT DOSSIER
=========================================================

{product_dossier}

=========================================================
FINAL TASK
=========================================================

Generate a structured TraceabilityReport containing:

- product
- supplier
- trace_chain
- traceability_status
- gaps

Every TraceNode must contain:

- entity_type
- entity_name
- status
- source
- notes

Return ONLY the structured TraceabilityReport.
"""

    print(
        "\n🧭 Traceability Agent → Central AI Service"
    )

    return _call_central_ai(
        prompt
    )


# =========================================================
# 8. LOCAL FALLBACK
# =========================================================
def _build_fallback_report(
    product_dossier: str,
) -> TraceabilityReport:
    """
    Conservative local fallback.

    No new facts are invented.
    """

    product = "Unknown Product"
    supplier = "Unknown Supplier"

    # -----------------------------------------------------
    # Extract product/supplier
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
    # Fallback chain
    # -----------------------------------------------------
    trace_chain = [
        TraceNode(
            entity_type="SUPPLIER",
            entity_name=supplier,
            status="VERIFIED"
            if supplier != "Unknown Supplier"
            else "UNCLEAR",
            source="Product Dossier",
            notes=(
                "Supplier information was extracted "
                "from the supplied dossier."
            ),
        ),
        TraceNode(
            entity_type="PRODUCT",
            entity_name=product,
            status="VERIFIED"
            if product != "Unknown Product"
            else "UNCLEAR",
            source="Product Dossier",
            notes=(
                "Product information was extracted "
                "from the supplied dossier."
            ),
        ),
    ]

    return TraceabilityReport(
        product=product,
        supplier=supplier,
        trace_chain=trace_chain,
        traceability_status="HUMAN_REVIEW",
        gaps=[
            (
                "Automated traceability assessment was "
                "unavailable."
            )
        ],
    )


# =========================================================
# 9. SAFE TRACEABILITY EXECUTION
# =========================================================
def run_traceability_agent_safe(
    product_dossier: str,
) -> TraceabilityReport:
    """
    Execute Traceability Agent with a conservative fallback
    when the Central AI Service is unavailable.
    """

    try:

        report = run_traceability_agent(
            product_dossier
        )

        print(
            "\n✅ Traceability Agent completed using "
            "Central AI Service."
        )

        return report

    except Exception as error:

        print(
            "\n⚠️ Central AI Traceability generation unavailable."
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

Material:
100% Cotton

Available evidence:
- Supplier registration document
- Cotton material declaration
- Lab test report

Missing information:
- Cotton farm/origin
- Manufacturing batch ID
- Energy consumption record

Destination market:
European Union
"""

    print("\n")
    print(
        "==============================================="
    )

    print(
        "       TRACEX AI - TRACEABILITY AGENT"
    )

    print(
        "==============================================="
    )

    try:

        report = run_traceability_agent_safe(
            sample_dossier
        )

        print(
            "\n-----------------------------------------------"
        )

        print(
            "TRACEABILITY RESULT"
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
            "\n✅ Traceability Agent executed successfully."
        )

    except Exception as error:

        print(
            "\n❌ Traceability Agent failed."
        )

        print(
            f"Error: {error}"
        )

        sys.exit(1)