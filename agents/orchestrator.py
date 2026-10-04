import sys
import time
import json
from pathlib import Path
from typing import TypedDict, List


from langgraph.graph import StateGraph, START, END


# =========================================================
# 1. PROJECT ROOT
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =========================================================
# 2. IMPORT AGENTS
# =========================================================
from agents.evidence_agent import (
    run_evidence_agent_safe,
)

from agents.traceability_agent import (
    run_traceability_agent_safe,
)

from agents.compliance_agent import (
    run_compliance_agent,
)

from agents.risk_agent import (
    run_risk_agent,
)

from agents.verification_agent import (
    run_verification_agent,
    VerificationReport,
)


# =========================================================
# 3. IMPORT DIGITAL PRODUCT PASSPORT
# =========================================================
from tools.passport_generator import (
    generate_passport,
    passport_to_json,
    save_passport_json,
)


# =========================================================
# 4. SHARED LANGGRAPH STATE
# =========================================================
class TraceXState(TypedDict, total=False):

    # -----------------------------------------------------
    # Primary input
    # -----------------------------------------------------
    product_dossier: str

    # -----------------------------------------------------
    # Agent outputs
    # -----------------------------------------------------
    evidence_report: str
    traceability_report: str
    compliance_report: str
    risk_report: str
    verification_report: str

    # -----------------------------------------------------
    # Product output
    # -----------------------------------------------------
    passport_report: str

    # -----------------------------------------------------
    # Workflow tracking
    # -----------------------------------------------------
    current_stage: str

    completed_stages: List[str]

    workflow_errors: List[str]

    verification_fallback_used: bool

    execution_time_seconds: float


# =========================================================
# 5. STATE HELPERS
# =========================================================
def _completed_stage_update(
    state: TraceXState,
    stage_name: str,
) -> dict:

    previous = state.get(
        "completed_stages",
        [],
    )

    completed = list(previous)

    if stage_name not in completed:
        completed.append(stage_name)

    return {
        "completed_stages": completed,
        "current_stage": f"{stage_name} completed",
    }


def _error_update(
    state: TraceXState,
    stage_name: str,
    error: Exception,
) -> dict:

    previous_errors = state.get(
        "workflow_errors",
        [],
    )

    errors = list(previous_errors)

    errors.append(
        f"{stage_name}: {error}"
    )

    return {
        "workflow_errors": errors,
        "current_stage": f"{stage_name} encountered an error",
    }


# =========================================================
# 6. EVIDENCE NODE
# =========================================================
def evidence_node(
    state: TraceXState,
):

    print(
        "\n🔎 [1/6] Evidence Agent started..."
    )

    try:

        report = run_evidence_agent_safe(
            state["product_dossier"]
        )

        print(
            "✅ Evidence Agent completed."
        )

        update = {
            "evidence_report": (
                report.model_dump_json(
                    indent=2
                )
            ),
        }

        update.update(
            _completed_stage_update(
                state,
                "Evidence",
            )
        )

        return update

    except Exception as error:

        print(
            "\n❌ Evidence Agent failed."
        )

        print(
            f"   Error: {error}"
        )

        update = _error_update(
            state,
            "Evidence",
            error,
        )

        update["evidence_report"] = (
            '{"status":"ERROR",'
            '"message":"Evidence Agent failed."}'
        )

        return update


# =========================================================
# 7. TRACEABILITY NODE
# =========================================================
def traceability_node(
    state: TraceXState,
):

    print(
        "\n🔗 [2/6] Traceability Agent started..."
    )

    try:

        report = run_traceability_agent_safe(
            state["product_dossier"]
        )

        print(
            "✅ Traceability Agent completed."
        )

        update = {
            "traceability_report": (
                report.model_dump_json(
                    indent=2
                )
            ),
        }

        update.update(
            _completed_stage_update(
                state,
                "Traceability",
            )
        )

        return update

    except Exception as error:

        print(
            "\n❌ Traceability Agent failed."
        )

        print(
            f"   Error: {error}"
        )

        update = _error_update(
            state,
            "Traceability",
            error,
        )

        update["traceability_report"] = (
            '{"status":"ERROR",'
            '"message":"Traceability Agent failed."}'
        )

        return update


# =========================================================
# 8. COMPLIANCE NODE
# =========================================================
def compliance_node(
    state: TraceXState,
):

    print(
        "\n📚 [3/6] Compliance Agent + RAG started..."
    )

    try:

        report = run_compliance_agent(
            state["product_dossier"]
        )

        print(
            "✅ Compliance Agent + RAG completed."
        )

        update = {
            "compliance_report": (
                report.model_dump_json(
                    indent=2
                )
            ),
        }

        update.update(
            _completed_stage_update(
                state,
                "Compliance",
            )
        )

        return update

    except Exception as error:

        print(
            "\n❌ Compliance Agent failed."
        )

        print(
            f"   Error: {error}"
        )

        update = _error_update(
            state,
            "Compliance",
            error,
        )

        update["compliance_report"] = (
            '{"status":"ERROR",'
            '"message":"Compliance Agent failed."}'
        )

        return update


# =========================================================
# 9. RISK NODE
# =========================================================
def risk_node(
    state: TraceXState,
):

    print(
        "\n🚨 [4/6] Risk Agent started..."
    )

    try:

        report = run_risk_agent(
            product_dossier=(
                state["product_dossier"]
            ),
            evidence_report=(
                state.get(
                    "evidence_report",
                    "",
                )
            ),
            traceability_report=(
                state.get(
                    "traceability_report",
                    "",
                )
            ),
            compliance_report=(
                state.get(
                    "compliance_report",
                    "",
                )
            ),
        )

        print(
            "✅ Risk Agent completed."
        )

        update = {
            "risk_report": (
                report.model_dump_json(
                    indent=2
                )
            ),
        }

        update.update(
            _completed_stage_update(
                state,
                "Risk",
            )
        )

        return update

    except Exception as error:

        print(
            "\n❌ Risk Agent failed."
        )

        print(
            f"   Error: {error}"
        )

        update = _error_update(
            state,
            "Risk",
            error,
        )

        update["risk_report"] = (
            '{"status":"ERROR",'
            '"message":"Risk Agent failed."}'
        )

        return update


# =========================================================
# 10. VERIFICATION NODE
# =========================================================
def verification_node(
    state: TraceXState,
):

    print(
        "\n🛡️ [5/6] Verification Agent started..."
    )

    try:

        report = run_verification_agent(
            product_dossier=(
                state["product_dossier"]
            ),
            evidence_report=(
                state.get(
                    "evidence_report",
                    "",
                )
            ),
            traceability_report=(
                state.get(
                    "traceability_report",
                    "",
                )
            ),
            compliance_report=(
                state.get(
                    "compliance_report",
                    "",
                )
            ),
            risk_report=(
                state.get(
                    "risk_report",
                    "",
                )
            ),
        )

        print(
            "✅ Verification Agent completed."
        )

        update = {
            "verification_report": (
                report.model_dump_json(
                    indent=2
                )
            ),
            "verification_fallback_used": False,
        }

        update.update(
            _completed_stage_update(
                state,
                "Verification",
            )
        )

        return update

    except Exception as error:

        print(
            "\n⚠️ Verification Agent could not "
            "complete automated AI verification."
        )

        print(
            f"   Error: {error}"
        )

        print(
            "➡️ Creating conservative HUMAN_REVIEW result."
        )

        fallback_report = VerificationReport(
            overall_verdict=(
                "HUMAN_REVIEW_REQUIRED"
            ),
            verified_claims=0,
            flagged_claims=0,
            human_review_required=True,
            findings=[],
            final_guidance=[
                (
                    "Automated Verification Agent was "
                    "unavailable."
                ),
                (
                    "Do not treat upstream agent outputs "
                    "as independently verified."
                ),
                (
                    "Perform human review before making "
                    "a final export-readiness decision."
                ),
            ],
        )

        update = {
            "verification_report": (
                fallback_report.model_dump_json(
                    indent=2
                )
            ),
            "verification_fallback_used": True,
        }

        error_update = _error_update(
            state,
            "Verification",
            error,
        )

        update.update(
            error_update
        )

        update["current_stage"] = (
            "Verification completed with human-review fallback"
        )

        return update


# =========================================================
# 11. DIGITAL PRODUCT PASSPORT NODE
# =========================================================
def passport_node(
    state: TraceXState,
):

    print(
        "\n📘 [6/6] Digital Product Passport started..."
    )

    try:

        # -------------------------------------------------
        # Convert JSON strings from agents into dictionaries
        # -------------------------------------------------
        evidence_data = json.loads(
            state.get(
                "evidence_report",
                "{}",
            )
        )

        traceability_data = json.loads(
            state.get(
                "traceability_report",
                "{}",
            )
        )

        compliance_data = json.loads(
            state.get(
                "compliance_report",
                "{}",
            )
        )

        risk_data = json.loads(
            state.get(
                "risk_report",
                "{}",
            )
        )

        verification_data = json.loads(
            state.get(
                "verification_report",
                "{}",
            )
        )

        # -------------------------------------------------
        # Generate passport
        # -------------------------------------------------
        passport = generate_passport(
            evidence=evidence_data,
            traceability=traceability_data,
            compliance=compliance_data,
            risk=risk_data,
            verification=verification_data,
        )

        passport_json = passport_to_json(
            passport
        )

        # -------------------------------------------------
        # Save generated passport
        # -------------------------------------------------
        output_path = (
            PROJECT_ROOT
            / "data"
            / "generated_passport.json"
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        save_passport_json(
            passport,
            str(output_path),
        )

        print(
            "✅ Digital Product Passport generated."
        )

        print(
            f"📁 Saved to: {output_path}"
        )

        # -------------------------------------------------
        # Useful demo summary
        # -------------------------------------------------
        risk_section = passport.get(
            "risk",
            {},
        )

        readiness = passport.get(
            "export_readiness",
            {},
        )

        verification_section = passport.get(
            "verification",
            {},
        )

        evidence_gaps = passport.get(
            "evidence_gaps",
            [],
        )

        actions = passport.get(
            "priority_actions",
            [],
        )

        print(
            "\n📊 Passport Summary:"
        )

        print(
            f"   Product: "
            f"{passport.get('product_identity', {}).get('name', 'Unknown')}"
        )

        print(
            f"   Risk: "
            f"{risk_section.get('score', 'N/A')}/100 "
            f"{risk_section.get('level', 'UNKNOWN')}"
        )

        print(
            f"   Export Readiness: "
            f"{readiness.get('status', 'UNKNOWN')}"
        )

        print(
            f"   Verification: "
            f"{verification_section.get('status', 'UNKNOWN')}"
        )

        print(
            f"   Evidence Gaps: "
            f"{len(evidence_gaps)}"
        )

        print(
            f"   Priority Actions: "
            f"{len(actions)}"
        )

        update = {
            "passport_report": passport_json,
        }

        update.update(
            _completed_stage_update(
                state,
                "Passport",
            )
        )

        return update

    except Exception as error:

        print(
            "\n❌ Digital Product Passport failed."
        )

        print(
            f"   Error: {error}"
        )

        update = _error_update(
            state,
            "Passport",
            error,
        )

        update["passport_report"] = (
            json.dumps(
                {
                    "status": "ERROR",
                    "message": (
                        "Digital Product Passport "
                        "generation failed."
                    ),
                },
                indent=2,
            )
        )

        return update


# =========================================================
# 12. BUILD LANGGRAPH
# =========================================================
def build_tracex_graph():

    workflow = StateGraph(
        TraceXState
    )

    # -----------------------------------------------------
    # Nodes
    # -----------------------------------------------------
    workflow.add_node(
        "evidence_agent",
        evidence_node,
    )

    workflow.add_node(
        "traceability_agent",
        traceability_node,
    )

    workflow.add_node(
        "compliance_agent",
        compliance_node,
    )

    workflow.add_node(
        "risk_agent",
        risk_node,
    )

    workflow.add_node(
        "verification_agent",
        verification_node,
    )

    workflow.add_node(
        "passport_generator",
        passport_node,
    )

    # -----------------------------------------------------
    # Sequential flow
    # -----------------------------------------------------
    workflow.add_edge(
        START,
        "evidence_agent",
    )

    workflow.add_edge(
        "evidence_agent",
        "traceability_agent",
    )

    workflow.add_edge(
        "traceability_agent",
        "compliance_agent",
    )

    workflow.add_edge(
        "compliance_agent",
        "risk_agent",
    )

    workflow.add_edge(
        "risk_agent",
        "verification_agent",
    )

    workflow.add_edge(
        "verification_agent",
        "passport_generator",
    )

    workflow.add_edge(
        "passport_generator",
        END,
    )

    return workflow.compile()


# =========================================================
# 13. DEMO DOSSIER
# =========================================================
DEMO_DOSSIER = """
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
- Required export certificate

Destination market:
European Union
"""


# =========================================================
# 14. PRINT FINAL SUMMARY
# =========================================================
def print_final_summary(
    final_state: TraceXState,
    elapsed: float,
):

    print("\n")
    print(
        "================================================"
    )

    print(
        "          TRACEX AI — FINAL SUMMARY"
    )

    print(
        "================================================"
    )

    print(
        f"\nExecution time: {elapsed:.1f} seconds"
    )

    # -----------------------------------------------------
    # Completed stages
    # -----------------------------------------------------
    completed = final_state.get(
        "completed_stages",
        [],
    )

    print(
        "\nCompleted stages:"
    )

    if completed:

        for stage in completed:
            print(
                f"   ✅ {stage}"
            )

    else:

        print(
            "   None"
        )

    # -----------------------------------------------------
    # Errors
    # -----------------------------------------------------
    errors = final_state.get(
        "workflow_errors",
        [],
    )

    if errors:

        print(
            "\nWorkflow warnings/errors:"
        )

        for error in errors:

            print(
                f"   ⚠️ {error}"
            )

    else:

        print(
            "\nWorkflow errors: None ✅"
        )

    # -----------------------------------------------------
    # Verification fallback
    # -----------------------------------------------------
    verification_fallback = (
        final_state.get(
            "verification_fallback_used",
            False,
        )
    )

    print(
        "\nVerification fallback used: "
        f"{'YES ⚠️' if verification_fallback else 'NO ✅'}"
    )


# =========================================================
# 15. RUN COMPLETE WORKFLOW
# =========================================================
if __name__ == "__main__":

    print("\n")

    print(
        "================================================"
    )

    print(
        "       TRACEX AI — MULTI-AGENT WORKFLOW"
    )

    print(
        "================================================"
    )

    print(
        "\nWorkflow:"
    )

    print(
        "Evidence"
        " → "
        "Traceability"
        " → "
        "Compliance + RAG"
        " → "
        "Risk"
        " → "
        "Verification"
        " → "
        "Digital Product Passport"
    )

    print(
        "\nArchitecture:"
    )

    print(
        "LangGraph → Specialized Agents "
        "→ Central AI Service → RAG "
        "→ Deterministic Risk → Verification "
        "→ Passport"
    )

    print(
        "\nStarting workflow..."
    )

    # -----------------------------------------------------
    # Build graph
    # -----------------------------------------------------
    graph = build_tracex_graph()

    # -----------------------------------------------------
    # Initial state
    # -----------------------------------------------------
    initial_state: TraceXState = {
        "product_dossier": DEMO_DOSSIER,
        "current_stage": "Workflow started",
        "completed_stages": [],
        "workflow_errors": [],
        "verification_fallback_used": False,
    }

    # -----------------------------------------------------
    # Start timer
    # -----------------------------------------------------
    started_at = time.time()

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------
    final_state = graph.invoke(
        initial_state
    )

    # -----------------------------------------------------
    # Execution time
    # -----------------------------------------------------
    elapsed = (
        time.time()
        - started_at
    )

    final_state[
        "execution_time_seconds"
    ] = round(
        elapsed,
        2,
    )

    # =====================================================
    # RESULTS
    # =====================================================

    print("\n")

    print(
        "================================================"
    )

    print(
        "          TRACEX AI — FINAL RESULT"
    )

    print(
        "================================================"
    )

    print(
        f"\nExecution time: "
        f"{elapsed:.1f} seconds"
    )

    # -----------------------------------------------------
    # Evidence
    # -----------------------------------------------------
    print(
        "\n---------------- EVIDENCE ----------------"
    )

    print(
        final_state.get(
            "evidence_report",
            "No evidence report generated.",
        )
    )

    # -----------------------------------------------------
    # Traceability
    # -----------------------------------------------------
    print(
        "\n---------------- TRACEABILITY ----------------"
    )

    print(
        final_state.get(
            "traceability_report",
            "No traceability report generated.",
        )
    )

    # -----------------------------------------------------
    # Compliance
    # -----------------------------------------------------
    print(
        "\n---------------- COMPLIANCE + RAG ----------------"
    )

    print(
        final_state.get(
            "compliance_report",
            "No compliance report generated.",
        )
    )

    # -----------------------------------------------------
    # Risk
    # -----------------------------------------------------
    print(
        "\n---------------- RISK ----------------"
    )

    print(
        final_state.get(
            "risk_report",
            "No risk report generated.",
        )
    )

    # -----------------------------------------------------
    # Verification
    # -----------------------------------------------------
    print(
        "\n---------------- VERIFICATION ----------------"
    )

    print(
        final_state.get(
            "verification_report",
            "No verification report generated.",
        )
    )

    # -----------------------------------------------------
    # Passport
    # -----------------------------------------------------
    print(
        "\n---------------- DIGITAL PRODUCT PASSPORT ----------------"
    )

    print(
        final_state.get(
            "passport_report",
            "No passport generated.",
        )
    )

    # =====================================================
    # FINAL SUMMARY
    # =====================================================
    print_final_summary(
        final_state=final_state,
        elapsed=elapsed,
    )

    # =====================================================
    # WORKFLOW STATUS
    # =====================================================
    print("\n")

    print(
        "================================================"
    )

    if final_state.get(
        "verification_fallback_used",
        False,
    ):

        print(
            "⚠️ TRACEX AI WORKFLOW COMPLETED "
            "WITH HUMAN-REVIEW FALLBACK"
        )

    elif final_state.get(
        "workflow_errors",
        [],
    ):

        print(
            "⚠️ TRACEX AI WORKFLOW COMPLETED "
            "WITH WARNINGS"
        )

    else:

        print(
            "✅ TRACEX AI MULTI-AGENT WORKFLOW + "
            "PASSPORT COMPLETED"
        )

    print(
        "================================================"
    )