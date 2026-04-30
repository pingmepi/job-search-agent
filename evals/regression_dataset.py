"""Curated regression dataset for inbox pipeline checks."""

from __future__ import annotations

from typing import Any

RegressionCase = dict[str, Any]


REGRESSION_CASES: list[RegressionCase] = [
    {
        "id": "text_ai_pm_core",
        "description": "Standard AI PM JD with clear skills and responsibilities.",
        "input_mode": "text",
        "raw_text": (
            "Company: Nimbus Labs\n"
            "Role: AI Product Manager\n"
            "Location: Remote\n"
            "Responsibilities: Define AI product strategy, partner with engineering and design, "
            "ship experimentation roadmap.\n"
            "Requirements: 5+ years product management, SQL, Python, A/B testing, stakeholder management.\n"
            "Description: Build AI-powered workflow automation for enterprise users."
        ),
        "selected_collateral": ["email", "linkedin"],
        "tags": ["happy_path", "ai_pm"],
        "expected": {
            "task_outcome_in": ["success", "partial"],
            "compile_success": True,
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
            "min_keyword_coverage": 0.4,
        },
    },
    {
        "id": "text_growth_pm_core",
        "description": "Standard Growth PM JD with funnel and experiment terms.",
        "input_mode": "text",
        "raw_text": (
            "Company: Helio Commerce\n"
            "Role: Growth Product Manager\n"
            "Location: Bengaluru\n"
            "Responsibilities: Improve activation and retention, design growth experiments, "
            "monitor conversion funnel.\n"
            "Requirements: Product analytics, experimentation, lifecycle messaging, SQL.\n"
            "Description: Own growth roadmap for B2C mobile app."
        ),
        "selected_collateral": ["email"],
        "tags": ["happy_path", "growth"],
        "expected": {
            "task_outcome_in": ["success", "partial"],
            "compile_success": True,
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
            "min_keyword_coverage": 0.35,
        },
    },
    {
        "id": "text_tpm_platform_core",
        "description": "Technical PM role with platform and API responsibilities.",
        "input_mode": "text",
        "raw_text": (
            "Company: Orbit Stack\n"
            "Role: Technical Product Manager\n"
            "Location: Hyderabad\n"
            "Responsibilities: Define API platform roadmap, prioritize reliability improvements, "
            "align with infra and security.\n"
            "Requirements: APIs, distributed systems, stakeholder management, metrics ownership.\n"
            "Description: Build developer platform products for internal engineering teams."
        ),
        "selected_collateral": ["linkedin"],
        "tags": ["happy_path", "tpm"],
        "expected": {
            "task_outcome_in": ["success", "partial"],
            "compile_success": True,
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
            "min_keyword_coverage": 0.3,
        },
    },
    {
        "id": "text_founders_office_core",
        "description": "Founder's office style role with operations and GTM scope.",
        "input_mode": "text",
        "raw_text": (
            "Company: Arcline AI\n"
            "Role: Founder's Office\n"
            "Location: Mumbai\n"
            "Responsibilities: Run cross-functional initiatives, support GTM planning, "
            "drive weekly business cadence.\n"
            "Requirements: Structured problem solving, data analysis, communication, execution ownership.\n"
            "Description: Work closely with founders on strategic initiatives."
        ),
        "selected_collateral": ["email", "referral"],
        "tags": ["happy_path", "founders_office"],
        "expected": {
            "task_outcome_in": ["success", "partial"],
            "compile_success": True,
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
            "min_keyword_coverage": 0.3,
        },
    },
    {
        "id": "edge_sparse_jd",
        "description": "Sparse JD with missing structure should still avoid fail outcome.",
        "input_mode": "text",
        "raw_text": "Looking for Product Manager. Startup. Good communication. Apply soon.",
        "selected_collateral": ["email"],
        "tags": ["edge_case", "sparse_jd"],
        "expected": {
            "task_outcome_in": ["partial", "success"],
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
        },
    },
    {
        "id": "edge_noisy_text",
        "description": "Noisy pseudo-OCR text to validate parser resilience.",
        "input_mode": "text",
        "raw_text": (
            "C0mpany:: N1mbl3 Labs ### R0le?? Product M@nager\n"
            "RESP0NSIBILIT1ES -- lead team, build roadmap, worK with engg\n"
            "Reqs: 3+ yrs PM / SQL / expt; Loc:: rem0te"
        ),
        "selected_collateral": ["linkedin"],
        "tags": ["edge_case", "noisy_input"],
        "expected": {
            "task_outcome_in": ["partial", "success"],
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
        },
    },
    {
        "id": "edge_long_jd",
        "description": "Long JD text to pressure test mutation and condense paths.",
        "input_mode": "text",
        "raw_text": (
            "Company: Delta Grid\nRole: Senior Product Manager\nLocation: Remote\n"
            + "Responsibilities: "
            + " ".join(
                [
                    "Own roadmap, partner with engineering, define metrics, align stakeholders."
                    for _ in range(40)
                ]
            )
            + "\nRequirements: Product strategy, analytics, experimentation, communication."
        ),
        "selected_collateral": ["email", "linkedin", "referral"],
        "tags": ["edge_case", "long_jd"],
        "expected": {
            "task_outcome_in": ["success", "partial"],
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
        },
    },
    {
        "id": "edge_missing_company_role_labels",
        "description": "Description-first JD without explicit company/role labels.",
        "input_mode": "text",
        "raw_text": (
            "We are hiring for a product role to scale onboarding and retention for our fintech app. "
            "You will run experiments, partner with design and data, and own north-star metrics."
        ),
        "selected_collateral": ["email"],
        "tags": ["edge_case", "missing_fields"],
        "expected": {
            "task_outcome_in": ["partial", "success"],
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
        },
    },
    {
        "id": "edge_out_of_scope_pt_sales_engineer",
        "description": (
            "Portuguese Sales Engineer JD that the candidate is not aligned with — "
            "regression for run-144b1afaef4a where the pipeline silently rebranded "
            "the candidate as Technical Sales Engineer. Should now early-exit as "
            "out_of_scope (zero fit-score across all templates)."
        ),
        "input_mode": "text",
        "raw_text": (
            "Vaga: Engenheiro De Vendas\n"
            "Localização: São Paulo, Brasil\n"
            "Responsabilidades: realizar demonstrações técnicas para clientes, "
            "trabalhar próximo aos times comerciais, traduzir requisitos de "
            "clientes em soluções, dar suporte pós-venda e participar de "
            "negociações com stakeholders. Quota anual de vendas. Cold calling, "
            "prospecção, fechamento de contratos B2B.\n"
            "Requisitos: experiência em vendas técnicas, relacionamento com clientes, "
            "fluência em português e inglês."
        ),
        "selected_collateral": ["email"],
        "tags": ["edge_case", "out_of_scope", "non_english"],
        "expected": {
            "task_outcome_in": ["out_of_scope", "fail", "partial"],
            "max_forbidden_claims": 0,
            "max_edit_scope_violations": 0,
        },
    },
]


def get_regression_cases() -> list[RegressionCase]:
    """Return a copy of canonical regression cases."""
    return list(REGRESSION_CASES)
