import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Tuple

import streamlit as st
from pypdf import PdfReader

from agents.orchestrator import (
    build_tracex_graph,
    TraceXState,
    DEMO_DOSSIER,
)


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="TraceX AI — Export Intelligence",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# CUSTOM CSS
# =========================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 3rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }

    .subtitle {
        font-size: 1.15rem;
        opacity: 0.75;
        margin-bottom: 1.5rem;
    }

    .metric-card {
        padding: 1rem;
        border-radius: 14px;
        border: 1px solid rgba(128,128,128,0.25);
        min-height: 120px;
    }

    .section-title {
        font-size: 1.4rem;
        font-weight: 700;
        margin-top: 1rem;
        margin-bottom: 0.7rem;
    }

    .status-box {
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,0.25);
        margin-bottom: 1rem;
    }

    .pipeline-step {
        padding: 0.55rem 0.8rem;
        border-radius: 10px;
        border: 1px solid rgba(128,128,128,0.25);
        margin-bottom: 0.45rem;
    }

    .small-muted {
        opacity: 0.65;
        font-size: 0.9rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SESSION STATE
# =========================================================

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if "source_name" not in st.session_state:
    st.session_state.source_name = "Demo Export Case"


# =========================================================
# HELPERS
# =========================================================

def clean_text(value: Any) -> str:
    """
    Convert a value to clean single-line text.
    """
    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def extract_pdf_text(uploaded_file) -> str:
    """
    Extract selectable text from an uploaded PDF.
    """

    try:
        uploaded_file.seek(0)

        pdf_bytes = uploaded_file.read()

        reader = PdfReader(
            BytesIO(pdf_bytes)
        )

        pages = []

        for page in reader.pages:

            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""

            if text.strip():
                pages.append(text.strip())

        return "\n\n".join(pages)

    except Exception as error:

        raise RuntimeError(
            f"Could not read PDF: {error}"
        ) from error


def read_uploaded_source(uploaded_file) -> Tuple[str, str]:
    """
    Return:
        extracted_text
        source_name
    """

    source_name = uploaded_file.name

    suffix = Path(
        source_name
    ).suffix.lower()

    if suffix == ".pdf":

        text = extract_pdf_text(
            uploaded_file
        )

    elif suffix in {
        ".txt",
        ".md",
    }:

        uploaded_file.seek(0)

        raw = uploaded_file.read()

        if isinstance(raw, bytes):

            text = raw.decode(
                "utf-8",
                errors="ignore",
            )

        else:

            text = str(raw)

    else:

        raise ValueError(
            "Supported files are PDF, TXT and MD."
        )

    return text.strip(), source_name


def extract_labeled_value(
    text: str,
    labels: list[str],
) -> str:
    """
    Extract an explicitly labeled value from the source document.

    Examples:
        Product: Denim Pants
        Supplier: NoorTex Garments
        Material: Spun Yarn
        Destination Market: European Union

    IMPORTANT:
    This function only extracts explicit labels.
    It does not guess.
    """

    if not text:
        return ""

    label_pattern = "|".join(
        re.escape(label)
        for label in labels
    )

    pattern = re.compile(
        rf"(?im)^\s*(?:{label_pattern})\s*[:\-]\s*(.+?)\s*$"
    )

    match = pattern.search(text)

    if not match:
        return ""

    value = clean_text(
        match.group(1)
    )

    if value.lower() in {
        "not specified",
        "not provided",
        "unknown",
        "n/a",
        "na",
        "none",
        "not available",
    }:

        return "Not Specified"

    return value


def resolve_uploaded_field(
    user_value: str,
    extracted_text: str,
    labels: list[str],
) -> str:
    """
    Priority:
        1. Explicit user-entered value
        2. Explicitly labeled value from source
        3. Not Specified

    No inference is performed.
    """

    user_value = clean_text(
        user_value
    )

    if user_value:
        return user_value

    source_value = extract_labeled_value(
        extracted_text,
        labels,
    )

    if source_value:
        return source_value

    return "Not Specified"


def build_uploaded_dossier(
    product_name: str,
    supplier_name: str,
    material: str,
    destination_market: str,
    missing_information: str,
    extracted_text: str,
) -> str:
    """
    Convert uploaded-document information into the
    normalized dossier format expected by TraceX agents.

    The dossier follows strict evidence-first rules:
        - User-entered values are explicit metadata.
        - Source-labeled values are accepted.
        - Missing values become "Not Specified".
        - No destination/supplier/product fact is guessed.
    """

    normalized_product = resolve_uploaded_field(
        product_name,
        extracted_text,
        [
            "Product",
            "Product Name",
            "Product Type",
        ],
    )

    normalized_supplier = resolve_uploaded_field(
        supplier_name,
        extracted_text,
        [
            "Supplier",
            "Supplier Name",
            "Manufacturer",
        ],
    )

    normalized_material = resolve_uploaded_field(
        material,
        extracted_text,
        [
            "Material",
            "Material Composition",
            "Composition",
            "Fabric",
            "Fiber",
            "Fibre",
        ],
    )

    normalized_destination = resolve_uploaded_field(
        destination_market,
        extracted_text,
        [
            "Destination",
            "Destination Market",
            "Target Market",
            "Export Market",
            "Market",
        ],
    )

    missing_lines = []

    for line in missing_information.splitlines():

        cleaned = clean_text(
            line
        )

        cleaned = re.sub(
            r"^[\-\*\u2022]\s*",
            "",
            cleaned,
        )

        if cleaned:
            missing_lines.append(
                f"- {cleaned}"
            )

    if not missing_lines:

        missing_lines = [
            "- No missing information was explicitly provided by the uploader."
        ]

    source_excerpt = extracted_text[
        :30000
    ].strip()

    dossier = f"""
TraceX AI — NORMALIZED UPLOADED EXPORT DOSSIER

Source:
Uploaded document

Evidence handling rules:
- Use only information supported by the uploaded document or explicitly entered by the user.
- Do not invent product, supplier, material, destination, origin, batch, certificate, or compliance facts.
- If information is absent or cannot be established, mark it as Not Specified, UNCLEAR, MISSING, or HUMAN_REVIEW as appropriate.
- Missing evidence does not automatically mean the exporter is legally non-compliant.
- Numeric risk must follow the deterministic TraceX risk engine.

Product:
{normalized_product}

Supplier:
{normalized_supplier}

Material:
{normalized_material}

Available evidence:
- Uploaded source document

Known Missing Information:
{chr(10).join(missing_lines)}

Destination market:
{normalized_destination}

Source document content:
{source_excerpt}
"""

    return dossier.strip()


def run_tracex_analysis(
    dossier: str,
) -> TraceXState:

    graph = build_tracex_graph()

    initial_state: TraceXState = {
        "product_dossier": dossier,
        "current_stage": "Workflow started",
        "completed_stages": [],
        "workflow_errors": [],
        "verification_fallback_used": False,
    }

    return graph.invoke(
        initial_state
    )


def parse_json(
    value: Any,
) -> Dict[str, Any]:

    if isinstance(value, dict):
        return value

    if not value:
        return {}

    try:
        return json.loads(value)
    except Exception:
        return {}


def risk_label(
    score: int,
) -> str:

    if score >= 80:
        return "CRITICAL"

    if score >= 50:
        return "HIGH"

    if score >= 25:
        return "MEDIUM"

    return "LOW"


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def get_passport_data(
    result: TraceXState,
) -> Dict[str, Any]:

    return parse_json(
        result.get(
            "passport_report",
            "{}",
        )
    )


def normalize_action_key(
    action: str,
) -> str:
    """
    Create a comparison key for action-plan deduplication.
    """

    if not action:
        return ""

    text = action.lower().strip()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    words = [
        word
        for word in text.split()
        if word not in {
            "the",
            "a",
            "an",
            "to",
            "for",
            "and",
            "of",
            "on",
            "with",
            "required",
        }
    ]

    return " ".join(words)


def action_similarity(
    left: str,
    right: str,
) -> float:
    """
    Lightweight word-set similarity for duplicate detection.
    """

    left_words = set(
        normalize_action_key(left).split()
    )

    right_words = set(
        normalize_action_key(right).split()
    )

    if not left_words or not right_words:
        return 0.0

    intersection = len(
        left_words.intersection(
            right_words
        )
    )

    union = len(
        left_words.union(
            right_words
        )
    )

    return intersection / union


def deduplicate_actions(
    actions: Any,
) -> list[Dict[str, Any]]:
    """
    Keep the first meaningful version of repeated action items.

    This is UI-side cleanup only; underlying agent output remains
    available in the raw passport JSON.
    """

    if not isinstance(
        actions,
        list,
    ):
        return []

    unique_actions = []

    for item in actions:

        if not isinstance(
            item,
            dict,
        ):
            continue

        action = clean_text(
            item.get(
                "action",
                "",
            )
        )

        if not action:
            continue

        duplicate = False

        for existing in unique_actions:

            existing_action = clean_text(
                existing.get(
                    "action",
                    "",
                )
            )

            if action.lower() == existing_action.lower():

                duplicate = True
                break

            if (
                len(action.split()) >= 5
                and len(existing_action.split()) >= 5
                and action_similarity(
                    action,
                    existing_action,
                ) >= 0.70
            ):

                duplicate = True
                break

        if not duplicate:

            unique_actions.append(
                item
            )

    return unique_actions


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        "## 🌐 TraceX AI"
    )

    st.caption(
        "Trace. Verify. Export."
    )

    st.divider()

    mode = st.radio(
        "Analysis Mode",
        [
            "Demo Case",
            "Upload Document",
        ],
        index=0,
    )

    st.divider()

    st.markdown(
        "### Architecture"
    )

    architecture_steps = [
        "Evidence Agent",
        "Traceability Agent",
        "Compliance + RAG",
        "Deterministic Risk",
        "Verification Agent",
        "Digital Product Passport",
    ]

    for index, step in enumerate(
        architecture_steps,
        start=1,
    ):

        st.markdown(
            f"""
            <div class="pipeline-step">
                <b>{index}.</b> {step}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    st.caption(
        "AI explanations are generated through the "
        "central AI service. Numeric risk is calculated "
        "by deterministic TraceX rules."
    )


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="main-title">TraceX AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="subtitle">
    Export Passport & Supply-Chain Intelligence
    </div>
    """,
    unsafe_allow_html=True,
)

st.info(
    "Turn fragmented export evidence into traceability, "
    "compliance insights, deterministic risk signals, "
    "verification and a digital product passport."
)


# =========================================================
# INPUT AREA
# =========================================================

dossier = None

if mode == "Demo Case":

    st.markdown(
        '<div class="section-title">🚀 Demo Export Case</div>',
        unsafe_allow_html=True,
    )

    st.write(
        "Use the built-in cotton T-shirt case for the "
        "fastest and most reliable live demonstration."
    )

    with st.expander(
        "View Demo Product Dossier"
    ):

        st.code(
            DEMO_DOSSIER,
            language="text",
        )

    use_demo = st.button(
        "🔍 Analyze Demo Case",
        type="primary",
        use_container_width=True,
    )

    if use_demo:

        dossier = DEMO_DOSSIER

        st.session_state.source_name = (
            "Demo Export Case"
        )


else:

    st.markdown(
        '<div class="section-title">📄 Upload Export Document</div>',
        unsafe_allow_html=True,
    )

    st.write(
        "Upload a text-based export document. TraceX will "
        "use explicit source evidence first and will not "
        "guess missing facts."
    )

    st.caption(
        "Tip: Leave product, supplier, material and destination "
        "blank when the document already contains these fields. "
        "TraceX will use explicitly labeled values from the source."
    )

    uploaded_file = st.file_uploader(
        "Upload a product or supplier document",
        type=[
            "pdf",
            "txt",
            "md",
        ],
        help=(
            "PDF, TXT and Markdown files are supported. "
            "PDF text is extracted automatically."
        ),
    )

    col1, col2 = st.columns(2)

    with col1:

        product_name = st.text_input(
            "Product Name (optional)",
            value="",
            placeholder="e.g. Denim Pants",
        )

        supplier_name = st.text_input(
            "Supplier Name (optional)",
            value="",
            placeholder="e.g. NoorTex Garments",
        )

    with col2:

        material = st.text_input(
            "Material (optional)",
            value="",
            placeholder="e.g. Spun Yarn",
        )

        destination_market = st.text_input(
            "Destination Market (optional)",
            value="",
            placeholder="Leave blank if not explicitly known",
        )

    missing_information = st.text_area(
        "Known Missing Information (optional, one item per line)",
        value="",
        placeholder=(
            "Example:\n"
            "Cotton farm/origin\n"
            "Manufacturing batch ID\n"
            "Required export certificate"
        ),
        height=130,
    )

    extracted_text = ""

    if uploaded_file is not None:

        try:

            extracted_text, source_name = (
                read_uploaded_source(
                    uploaded_file
                )
            )

            st.session_state.source_name = (
                source_name
            )

            st.success(
                f"Loaded: {source_name}"
            )

            if extracted_text:

                st.markdown(
                    "#### Extracted Content Preview"
                )

                st.text_area(
                    "Document text",
                    value=extracted_text[
                        :5000
                    ],
                    height=220,
                    disabled=True,
                )

            else:

                st.warning(
                    "No selectable text was found "
                    "in this file. Scanned-image PDFs "
                    "need an OCR/multimodal extraction "
                    "layer, which is not enabled in "
                    "this MVP."
                )

        except Exception as error:

            st.error(
                str(error)
            )

    analyze_upload = st.button(
        "🔍 Analyze Uploaded Document",
        type="primary",
        use_container_width=True,
    )

    if analyze_upload:

        if uploaded_file is None:

            st.warning(
                "Please upload a PDF, TXT or MD file first."
            )

        elif not extracted_text:

            st.warning(
                "The uploaded file contains no readable "
                "text. Use the Demo Case or a text-based "
                "PDF for this MVP."
            )

        else:

            dossier = build_uploaded_dossier(
                product_name=product_name,
                supplier_name=supplier_name,
                material=material,
                destination_market=destination_market,
                missing_information=missing_information,
                extracted_text=extracted_text,
            )

            # Helpful debugging/traceability view
            with st.expander(
                "🔍 View Normalized Dossier Sent to TraceX",
                expanded=False,
            ):

                st.code(
                    dossier,
                    language="text",
                )


# =========================================================
# ANALYZE
# =========================================================

if dossier:

    with st.spinner(
        "TraceX is running the multi-agent workflow..."
    ):

        try:

            result = run_tracex_analysis(
                dossier
            )

            st.session_state.analysis_result = (
                result
            )

        except Exception as error:

            st.error(
                f"TraceX analysis failed: {error}"
            )

            st.session_state.analysis_result = None


# =========================================================
# RESULTS
# =========================================================

result = st.session_state.analysis_result

if result is not None:

    passport = get_passport_data(
        result
    )

    product_identity = passport.get(
        "product_identity",
        {},
    )

    supplier = passport.get(
        "supplier",
        {},
    )

    material = passport.get(
        "material",
        {},
    )

    traceability = passport.get(
        "traceability",
        {},
    )

    compliance = passport.get(
        "compliance",
        {},
    )

    risk = passport.get(
        "risk",
        {},
    )

    verification = passport.get(
        "verification",
        {},
    )

    export_readiness = passport.get(
        "export_readiness",
        {},
    )

    evidence_matrix = passport.get(
        "evidence_matrix",
        {},
    )

    evidence_gaps = passport.get(
        "evidence_gaps",
        [],
    )

    priority_actions = deduplicate_actions(
        passport.get(
            "priority_actions",
            [],
        )
    )

    risk_score = safe_int(
        risk.get(
            "score",
            0,
        )
    )

    risk_level = risk.get(
        "level",
        risk_label(risk_score),
    )

    traceability_status = traceability.get(
        "status",
        "UNKNOWN",
    )

    compliance_status = compliance.get(
        "status",
        "UNKNOWN",
    )

    verification_status = verification.get(
        "status",
        "UNKNOWN",
    )

    readiness_status = export_readiness.get(
        "status",
        "UNKNOWN",
    )

    # =====================================================
    # RESULTS HEADER
    # =====================================================

    st.divider()

    st.markdown(
        '<div class="section-title">📊 Export Intelligence Result</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Source: {st.session_state.source_name}"
    )

    # =====================================================
    # PRODUCT SUMMARY
    # =====================================================

    product_col1, product_col2 = st.columns(2)

    with product_col1:

        st.markdown(
            f"### {product_identity.get('name', 'Unknown Product')}"
        )

        st.write(
            f"**Supplier:** "
            f"{supplier.get('name', 'Unknown Supplier')}"
        )

        st.write(
            f"**Material:** "
            f"{material.get('composition', 'Not provided')}"
        )

    with product_col2:

        st.write(
            f"**Traceability:** "
            f"{traceability_status}"
        )

        st.write(
            f"**Compliance:** "
            f"{compliance_status}"
        )

        st.write(
            f"**Export Readiness:** "
            f"{readiness_status}"
        )

    # =====================================================
    # METRICS
    # =====================================================

    metric1, metric2, metric3, metric4 = st.columns(4)

    with metric1:

        st.metric(
            "Risk Score",
            f"{risk_score}/100",
            risk_level,
        )

    with metric2:

        st.metric(
            "Evidence Gaps",
            len(evidence_gaps),
        )

    with metric3:

        verified_claims = safe_int(
            verification.get(
                "verified_claims",
                0,
            )
        )

        st.metric(
            "Verified Claims",
            verified_claims,
        )

    with metric4:

        human_review = verification.get(
            "human_review_required",
            False,
        )

        st.metric(
            "Human Review",
            "Required"
            if human_review
            else "Not Required",
        )

    # =====================================================
    # RISK VISUAL
    # =====================================================

    st.markdown(
        "### 🚨 Risk Assessment"
    )

    st.progress(
        min(
            max(risk_score, 0),
            100,
        )
    )

    st.write(
        risk.get(
            "explanation",
            "No risk explanation available.",
        )
    )

    # =====================================================
    # PASSPORT
    # =====================================================

    st.markdown(
        "### 📘 Digital Product Passport"
    )

    passport_col1, passport_col2 = st.columns(2)

    with passport_col1:

        st.markdown(
            "#### Product Identity"
        )

        st.write(
            f"**Product:** "
            f"{product_identity.get('name', 'Unknown')}"
        )

        st.write(
            f"**Supplier:** "
            f"{supplier.get('name', 'Unknown')}"
        )

        st.write(
            f"**Material:** "
            f"{material.get('composition', 'Unknown')}"
        )

        st.write(
            f"**Origin:** "
            f"{material.get('origin', 'Not verified')}"
        )

    with passport_col2:

        st.markdown(
            "#### Passport Status"
        )

        st.write(
            f"**Traceability:** "
            f"{traceability_status}"
        )

        st.write(
            f"**Compliance:** "
            f"{compliance_status}"
        )

        st.write(
            f"**Risk:** "
            f"{risk_score}/100 — {risk_level}"
        )

        st.write(
            f"**Verification:** "
            f"{verification_status}"
        )

    # =====================================================
    # EVIDENCE
    # =====================================================

    with st.expander(
        "🔎 Evidence Matrix",
        expanded=True,
    ):

        evidence_col1, evidence_col2 = (
            st.columns(2)
        )

        with evidence_col1:

            st.markdown(
                "#### ✅ Verified Evidence"
            )

            verified = evidence_matrix.get(
                "verified",
                [],
            )

            if verified:

                for item in verified:

                    st.success(
                        item
                    )

            else:

                st.write(
                    "No verified evidence found."
                )

        with evidence_col2:

            st.markdown(
                "#### ⚠️ Missing Evidence"
            )

            missing = evidence_matrix.get(
                "missing",
                [],
            )

            if missing:

                for item in missing:

                    st.warning(
                        item
                    )

            else:

                st.write(
                    "No missing evidence identified."
                )

    # =====================================================
    # TRACEABILITY
    # =====================================================

    with st.expander(
        "🔗 Supply-Chain Traceability",
        expanded=True,
    ):

        chain = traceability.get(
            "chain",
            [],
        )

        if chain:

            for item in chain:

                entity_type = item.get(
                    "entity_type",
                    "ENTITY",
                )

                entity_name = item.get(
                    "entity_name",
                    "Unknown",
                )

                status = item.get(
                    "status",
                    "UNKNOWN",
                )

                st.write(
                    f"**{entity_type}** → "
                    f"{entity_name} "
                    f"— `{status}`"
                )

        else:

            st.info(
                "No traceability chain available."
            )

    # =====================================================
    # COMPLIANCE
    # =====================================================

    with st.expander(
        "📚 Compliance + RAG Assessment",
        expanded=True,
    ):

        requirements = compliance.get(
            "requirements",
            [],
        )

        if requirements:

            for requirement in requirements:

                requirement_name = requirement.get(
                    "requirement",
                    "Requirement",
                )

                status = requirement.get(
                    "status",
                    "UNKNOWN",
                )

                explanation = requirement.get(
                    "explanation",
                    "",
                )

                if status == "SATISFIED":

                    st.success(
                        f"✅ {requirement_name}"
                    )

                elif status in {
                    "GAP",
                    "HUMAN_REVIEW",
                }:

                    st.warning(
                        f"⚠️ {requirement_name} — "
                        f"{status}"
                    )

                else:

                    st.info(
                        f"{requirement_name} — "
                        f"{status}"
                    )

                if explanation:

                    st.caption(
                        explanation
                    )

        else:

            st.info(
                "No compliance checks available."
            )

    # =====================================================
    # VERIFICATION
    # =====================================================

    with st.expander(
        "🛡️ Verification & Trust Layer",
        expanded=True,
    ):

        st.write(
            f"**Overall Verdict:** "
            f"{verification_status}"
        )

        st.write(
            f"**Verified Claims:** "
            f"{verification.get('verified_claims', 0)}"
        )

        st.write(
            f"**Flagged Claims:** "
            f"{verification.get('flagged_claims', 0)}"
        )

        if verification.get(
            "human_review_required",
            False,
        ):

            st.warning(
                "Human review is required for one or "
                "more findings."
            )

        findings = verification.get(
            "findings",
            [],
        )

        for index, finding in enumerate(
            findings,
            start=1,
        ):

            claim = finding.get(
                "claim",
                "",
            )

            verdict = finding.get(
                "verdict",
                "UNKNOWN",
            )

            st.markdown(
                f"**Finding {index}:** "
                f"`{verdict}`"
            )

            if claim:
                st.write(
                    claim
                )

            correction = finding.get(
                "correction",
                "",
            )

            if correction:
                st.caption(
                    f"Correction: {correction}"
                )

    # =====================================================
    # ACTION PLAN
    # =====================================================

    st.markdown(
        "### 🎯 Export Readiness Action Plan"
    )

    if priority_actions:

        for index, action_item in enumerate(
            priority_actions,
            start=1,
        ):

            priority = action_item.get(
                "priority",
                "MEDIUM",
            )

            action = action_item.get(
                "action",
                "",
            )

            reason = action_item.get(
                "reason",
                "",
            )

            st.markdown(
                f"**{index}. [{priority}]** {action}"
            )

            if reason:
                st.caption(
                    reason
                )

    else:

        st.success(
            "No outstanding priority actions."
        )

    # =====================================================
    # PIPELINE STATUS
    # =====================================================

    with st.expander(
        "⚙️ Agent Workflow Status",
        expanded=False,
    ):

        completed_stages = result.get(
            "completed_stages",
            [],
        )

        for stage in completed_stages:

            st.success(
                f"✅ {stage}"
            )

        errors = result.get(
            "workflow_errors",
            [],
        )

        if errors:

            for error in errors:

                st.warning(
                    error
                )

        else:

            st.success(
                "No workflow errors."
            )

        st.write(
            f"Verification fallback used: "
            f"{'YES' if result.get('verification_fallback_used', False) else 'NO'}"
        )

    # =====================================================
    # DOWNLOAD PASSPORT
    # =====================================================

    st.markdown(
        "### 📥 Passport Export"
    )

    passport_json = json.dumps(
        passport,
        indent=2,
        ensure_ascii=False,
    )

    st.download_button(
        label="Download Digital Product Passport (JSON)",
        data=passport_json,
        file_name="tracex_digital_product_passport.json",
        mime="application/json",
        use_container_width=True,
    )

    # =====================================================
    # RAW JSON
    # =====================================================

    with st.expander(
        "View Complete Passport JSON",
        expanded=False,
    ):

        st.json(
            passport
        )

else:

    # =====================================================
    # EMPTY STATE
    # =====================================================

    st.markdown(
        "## 👋 Welcome to TraceX AI"
    )

    st.write(
        "Choose **Demo Case** from the sidebar and "
        "click **Analyze Demo Case** to see the complete "
        "multi-agent export intelligence workflow."
    )

    st.markdown(
        """
        ### What TraceX does

        **Evidence → Traceability → Compliance + RAG
        → Deterministic Risk → Verification
        → Digital Product Passport**
        """
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.info(
            "🔎 **Evidence Intelligence**\n\n"
            "Identifies verified and missing evidence."
        )

    with col2:

        st.info(
            "🛡️ **Verification Layer**\n\n"
            "Audits important AI-generated conclusions."
        )

    with col3:

        st.info(
            "📘 **Digital Passport**\n\n"
            "Converts the analysis into a structured "
            "export passport."
        )