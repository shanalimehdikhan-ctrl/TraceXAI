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
# 3. RAG IMPORT
# =========================================================
try:
    from rag.retriever import retrieve_knowledge
except Exception as error:
    raise ImportError(
        "Could not import the RAG retriever.\n"
        "Please make sure this file exists:\n"
        "C:\\TraceXAI\\rag\\retriever.py"
    ) from error


# =========================================================
# 4. STRUCTURED OUTPUT MODELS
# =========================================================
class ComplianceCheck(BaseModel):

    requirement: str

    status: str = Field(
        description=(
            "One of: SATISFIED, GAP, UNCLEAR, HUMAN_REVIEW."
        )
    )

    evidence: str

    knowledge_source: str

    explanation: str


class ComplianceReport(BaseModel):

    product: str

    destination_market: str

    checks: List[ComplianceCheck]

    overall_status: str = Field(
        description=(
            "One of: READY, GAPS_FOUND, HUMAN_REVIEW."
        )
    )

    critical_gaps: List[str]

    recommended_actions: List[str]


# =========================================================
# 5. RESPONSE NORMALIZER
# =========================================================
def _normalize_compliance_response(
    response: Any,
) -> ComplianceReport:
    """
    Convert Central AI Service response into ComplianceReport.

    Supported response types:
        - ComplianceReport
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
        ComplianceReport,
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
            return ComplianceReport.model_validate(
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
        return ComplianceReport.model_validate(
            response
        )

    # -----------------------------------------------------
    # Gemini-style output_text object
    # -----------------------------------------------------
    output_text = getattr(
        response,
        "output_text",
        None,
    )

    if output_text:
        return ComplianceReport.model_validate_json(
            output_text
        )

    # -----------------------------------------------------
    # Raw JSON string
    # -----------------------------------------------------
    if isinstance(
        response,
        str,
    ):
        return ComplianceReport.model_validate_json(
            response
        )

    raise RuntimeError(
        "Central AI Service returned an unsupported "
        "Compliance Agent response format."
    )


# =========================================================
# 6. CENTRAL AI SERVICE CALLER
# =========================================================
def _call_central_ai(
    prompt: str,
) -> ComplianceReport:
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
# 7. EXECUTE CENTRAL SERVICE FUNCTION
# =========================================================
def _execute_service_function(
    function,
    prompt: str,
) -> ComplianceReport:

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

            return _normalize_compliance_response(
                response
            )

        # -------------------------------------------------
        # Structured output model/schema
        # -------------------------------------------------
        schema_json = (
            ComplianceReport.model_json_schema()
        )

        if "response_model" in parameters:

            kwargs["response_model"] = (
                ComplianceReport
            )

        elif "output_model" in parameters:

            kwargs["output_model"] = (
                ComplianceReport
            )

        elif "schema" in parameters:

            kwargs["schema"] = ComplianceReport

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
                "The Compliance Agent expects a "
                "synchronous service method."
            )

        # -------------------------------------------------
        # Normalize
        # -------------------------------------------------
        try:

            return _normalize_compliance_response(
                response
            )

        except ValidationError as error:

            print(
                "❌ Central AI Service returned an invalid "
                "ComplianceReport structure."
            )

            raise RuntimeError(
                "Invalid structured compliance output "
                "received from Central AI Service."
            ) from error

    except ValidationError:
        raise

    except RuntimeError:
        raise

    except Exception as error:

        raise RuntimeError(
            "Compliance Agent could not execute the "
            f"Central AI Service: {error}"
        ) from error


# =========================================================
# 8. RAG CONTEXT BUILDER
# =========================================================
def _build_knowledge_context(
    retrieved: List[Dict[str, Any]],
) -> str:
    """
    Convert RAG retrieval results into grounded prompt context.
    """

    if not retrieved:

        return (
            "NO RELEVANT KNOWLEDGE WAS RETRIEVED.\n"
            "Human review is required because the supplied "
            "knowledge base does not contain enough information."
        )

    context_blocks = []

    for index, item in enumerate(
        retrieved,
        start=1,
    ):

        source = item.get(
            "source",
            "Unknown Source",
        )

        document = item.get(
            "document",
            "",
        )

        distance = item.get(
            "distance",
            None,
        )

        if distance is not None:

            block = (
                f"RESULT {index}\n"
                f"SOURCE: {source}\n"
                f"DISTANCE: {distance}\n"
                f"KNOWLEDGE:\n{document}"
            )

        else:

            block = (
                f"RESULT {index}\n"
                f"SOURCE: {source}\n"
                f"KNOWLEDGE:\n{document}"
            )

        context_blocks.append(
            block
        )

    return "\n\n".join(
        context_blocks
    )


# =========================================================
# 9. LOCAL FALLBACK
# =========================================================
def _build_fallback_report(
    product_dossier: str,
    retrieved: List[Dict[str, Any]],
) -> ComplianceReport:
    """
    Conservative fallback when Central AI is unavailable.

    IMPORTANT:
    This fallback does not invent compliance requirements.
    It simply marks the assessment for human review.
    """

    product = "Unknown Product"
    destination_market = "Unknown Market"

    # -----------------------------------------------------
    # Product extraction
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
            "destination market:"
        ):

            destination_market = stripped.split(
                ":",
                1,
            )[1].strip()

    # -----------------------------------------------------
    # Retrieved knowledge source names
    # -----------------------------------------------------
    sources = []

    for item in retrieved:

        source = item.get(
            "source",
            "Unknown Source",
        )

        if source not in sources:
            sources.append(source)

    knowledge_source = (
        ", ".join(sources)
        if sources
        else "No knowledge source retrieved"
    )

    # -----------------------------------------------------
    # Conservative fallback check
    # -----------------------------------------------------
    check = ComplianceCheck(
        requirement=(
            "Destination-market and dossier-specific "
            "compliance assessment"
        ),
        status="HUMAN_REVIEW",
        evidence=(
            "Automated compliance assessment was unavailable; "
            "no unsupported conclusion has been made."
        ),
        knowledge_source=knowledge_source,
        explanation=(
            "The Central AI Service was unavailable during "
            "assessment. Human review is required before "
            "making a final compliance decision."
        ),
    )

    return ComplianceReport(
        product=product,
        destination_market=destination_market,
        checks=[check],
        overall_status="HUMAN_REVIEW",
        critical_gaps=[
            "Automated compliance assessment unavailable."
        ],
        recommended_actions=[
            "Retry the compliance assessment.",
            "Perform human review using the available "
            "official requirements and supplied evidence.",
        ],
    )


# =========================================================
# 10. COMPLIANCE AGENT
# =========================================================
def run_compliance_agent(
    product_dossier: str,
) -> ComplianceReport:

    # =====================================================
    # STEP 1 — RAG RETRIEVAL
    # =====================================================
    print(
        "\n🔎 Compliance Agent: "
        "querying RAG knowledge base..."
    )

    retrieval_query = f"""
Evaluate evidence, traceability, documentation, and
export-readiness requirements for the following product
dossier.

Use only knowledge relevant to the supplied dossier.

PRODUCT DOSSIER:
{product_dossier}
"""

    try:

        retrieved = retrieve_knowledge(
            retrieval_query,
            n_results=4,
        )

    except Exception as error:

        print(
            "⚠️ RAG retrieval failed."
        )

        print(
            f"   Reason: {error}"
        )

        retrieved = []

    print(
        f"📚 Compliance Agent: retrieved "
        f"{len(retrieved)} knowledge result(s)."
    )

    # =====================================================
    # STEP 2 — BUILD GROUNDED CONTEXT
    # =====================================================
    knowledge_context = (
        _build_knowledge_context(
            retrieved
        )
    )

    print(
        "🧠 Compliance Agent: "
        "preparing grounded assessment..."
    )

    # =====================================================
    # STEP 3 — GROUNDED PROMPT
    # =====================================================
    prompt = f"""
You are the Compliance Agent inside TraceX AI.

Your purpose is to assess an export product dossier against
the information available in the supplied product dossier
and the retrieved TraceX knowledge base.

=========================================================
CORE PRINCIPLE
=========================================================

TraceX AI must prefer evidence-based uncertainty over
invented legal or regulatory conclusions.

You are NOT allowed to invent:
- regulations
- certificates
- supplier facts
- product facts
- destination-market obligations
- customs outcomes
- legal requirements
- penalties

Use HUMAN_REVIEW whenever the supplied information is not
enough to reach a reliable conclusion.

=========================================================
SOURCE PRIORITY
=========================================================

Use ONLY these two sources:

1. PRODUCT DOSSIER
2. RETRIEVED TRACE X KNOWLEDGE BASE

Do not use outside information.

The product dossier is the primary evidence source.

The knowledge base provides supporting contextual
requirements and explanations.

If the knowledge base does not contain enough information,
use HUMAN_REVIEW.

=========================================================
STATUS DEFINITIONS
=========================================================

SATISFIED:
The requirement is explicitly supported by the supplied
product dossier and relevant knowledge.

GAP:
The requirement appears relevant based on retrieved
knowledge, but the necessary evidence is missing from the
product dossier.

UNCLEAR:
Some information exists, but it is insufficient to confirm
compliance.

HUMAN_REVIEW:
A reliable conclusion requires information outside the
supplied dossier/knowledge base, official destination-market
verification, legal interpretation, or additional evidence.

=========================================================
GROUNDING RULES
=========================================================

1. Every check must identify its evidence.

2. Every knowledge-based claim must identify its source.

3. Do not treat missing evidence as proof of illegality.

4. Do not claim:
   - customs rejection
   - shipment rejection
   - market prohibition
   - failed clearance
   unless that conclusion is explicitly supported by the
   supplied knowledge.

5. Separate:
   - evidence gap
   - traceability gap
   - compliance gap
   - legal conclusion

6. If a requirement is mentioned in the knowledge base but
   the product dossier lacks the corresponding evidence,
   use GAP.

7. If the requirement itself cannot be reliably established
   from the knowledge base, use HUMAN_REVIEW.

8. Do not invent additional requirements simply because the
   destination market is the European Union.

9. Keep explanations concise and exporter-focused.

=========================================================
PRODUCT DOSSIER
=========================================================

{product_dossier}

=========================================================
RETRIEVED TRACE X KNOWLEDGE
=========================================================

{knowledge_context}

=========================================================
FINAL TASK
=========================================================

Generate a structured ComplianceReport.

The report must contain:

- product
- destination_market
- checks
- overall_status
- critical_gaps
- recommended_actions

For every check include:

- requirement
- status
- evidence
- knowledge_source
- explanation

Use HUMAN_REVIEW whenever the available evidence or
knowledge is insufficient for a reliable final conclusion.

Return ONLY the structured ComplianceReport.
"""

    # =====================================================
    # STEP 4 — CENTRAL AI SERVICE
    # =====================================================
    try:

        print(
            "🚀 Compliance Agent: "
            "sending grounded request to Central AI Service..."
        )

        report = _call_central_ai(
            prompt
        )

        # -------------------------------------------------
        # Basic consistency enforcement
        # -------------------------------------------------
        # Ensure product is grounded in dossier if possible.
        dossier_product = "Unknown Product"

        for line in product_dossier.splitlines():

            stripped = line.strip()

            if stripped.lower().startswith(
                "product:"
            ):

                dossier_product = (
                    stripped.split(
                        ":",
                        1,
                    )[1].strip()
                )

                break

        if dossier_product != "Unknown Product":
            report.product = dossier_product

        # -------------------------------------------------
        # If no RAG knowledge was retrieved and the model
        # somehow produced a confident status, force human
        # review for safety.
        # -------------------------------------------------
        if not retrieved:

            report.overall_status = (
                "HUMAN_REVIEW"
            )

            if (
                "RAG knowledge base returned no relevant "
                "knowledge." 
                not in report.critical_gaps
            ):

                report.critical_gaps.append(
                    "RAG knowledge base returned no relevant knowledge."
                )

            report.recommended_actions.insert(
                0,
                "Perform human review using verified "
                "destination-market requirements."
            )

            for check in report.checks:

                if check.status == "SATISFIED":

                    check.status = (
                        "HUMAN_REVIEW"
                    )

                    check.explanation = (
                        check.explanation.strip()
                        + " Final confirmation requires "
                        "verified knowledge because no "
                        "relevant RAG result was retrieved."
                    )

        print(
            "\n✅ Compliance Agent completed using "
            "Central AI Service + RAG."
        )

        return report

    # =====================================================
    # STEP 5 — FALLBACK
    # =====================================================
    except Exception as error:

        print(
            "\n⚠️ Central AI Compliance generation unavailable."
        )

        print(
            f"   Reason: {error}"
        )

        print(
            "➡️ Using conservative local fallback."
        )

        return _build_fallback_report(
            product_dossier=product_dossier,
            retrieved=retrieved,
        )


# =========================================================
# 11. LOCAL TEST
# =========================================================
if __name__ == "__main__":

    sample_dossier = """
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

    print("\n")
    print(
        "==============================================="
    )
    print(
        "       TRACEX AI - COMPLIANCE AGENT"
    )
    print(
        "==============================================="
    )

    try:

        report = run_compliance_agent(
            sample_dossier
        )

        print(
            "\n-----------------------------------------------"
        )

        print(
            "COMPLIANCE RESULT"
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
            "\n✅ Compliance Agent + RAG executed successfully."
        )

    except Exception as error:

        print(
            "\n❌ Compliance Agent failed."
        )

        print(
            f"Error: {error}"
        )

        sys.exit(1)