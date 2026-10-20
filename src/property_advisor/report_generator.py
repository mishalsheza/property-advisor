"""Report Generation Tool.

Generates the final, human-approved investment report in three formats:
reports/<name>.json, reports/<name>.md, reports/<name>.pdf.

This is only ever called AFTER human approval — never from
inside the graph itself (report["status"] must be "approved").
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_TITLE = "Property Alpha AI — Indian Property Investment Advisory Report"

DECISION_COLORS = {
    "BUY": colors.HexColor("#1e7e34"),
    "HOLD": colors.HexColor("#b8860b"),
    "AVOID": colors.HexColor("#c82333"),
}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "report"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_inr(value: Any) -> str:
    try:
        return f"INR {float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_appreciation_source(market: dict[str, Any]) -> str:
    if market.get("appreciation_source") == "rbi_hpi":
        provisional = ", provisional" if market.get("hpi_provisional") else ""
        return f"RBI HPI, {market.get('hpi_city')} (city-level), {market.get('hpi_window')}{provisional}"
    return f"synthetic mock data — {market.get('appreciation_source', 'mock')}"


def _fmt_loan(loan: dict[str, Any]) -> str:
    if not loan:
        return "N/A"
    return (
        f"{loan.get('loan_to_value_ratio', 0) * 100:g}% LTV, {loan.get('interest_rate_pct')}% interest, "
        f"{loan.get('loan_tenure_years')} yrs, EMI {_fmt_inr(loan.get('monthly_emi_inr'))}/month"
    )


def _fmt_evidence(item: dict[str, Any]) -> str:
    return f"{item.get('statement', '')} ({item.get('metric')}={item.get('cited_value')})"


def _fmt_unverified(claim: dict[str, Any]) -> str:
    return f"{claim.get('statement', '')} [{claim.get('metric')}: {claim.get('reason')}]"


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def _write_json(report: dict[str, Any], path: str, generated_at: str) -> None:
    payload = {**report, "generated_at": generated_at}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------


def _render_markdown(report: dict[str, Any], generated_at: str) -> str:
    rec = report.get("recommendation", {})
    metrics = report.get("investment_metrics", {})
    risk = report.get("risk_assessment", {})
    guardrail = report.get("guardrail_result", {})
    human = report.get("human_decision", {})
    property_data = report.get("property_data", {})
    market_data = report.get("market_data", {})

    lines = [
        f"# {PROJECT_TITLE}",
        "",
        f"**Generated:** {generated_at}",
        "",
        "## Request",
        f"- **Property address:** {report.get('property_address')}",
        f"- **Budget:** {_fmt_inr(report.get('budget_inr'))}",
        f"- **Investment strategy:** {report.get('investment_strategy')}",
        f"- **Investment horizon:** {report.get('investment_horizon_years')} years",
        "",
        "## Property Summary",
        f"- City / Locality: {property_data.get('city', 'N/A')} / {property_data.get('locality', 'N/A')}",
        f"- Property type: {property_data.get('property_type', 'N/A')}",
        f"- Price: {_fmt_inr(property_data.get('price_inr', 'N/A'))}",
        f"- Area: {property_data.get('area_sqft', 'N/A')} sq ft",
        f"- Amenities: {', '.join(property_data.get('amenities', [])) or 'N/A'}",
        "",
        "## Market Summary",
        f"- Appreciation rate: {market_data.get('appreciation_rate_5yr_pct', 'N/A')}%/yr — {_fmt_appreciation_source(market_data)}",
        f"- Demand index: {market_data.get('demand_index', 'N/A')} / Supply index: {market_data.get('supply_index', 'N/A')}",
        f"- Avg rental yield: {market_data.get('rental_yield_avg_pct', 'N/A')}%",
        f"- RERA-registered projects: {market_data.get('rera_registered_projects_pct', 'N/A')}%",
        "" if market_data else "_No market data was available for this locality._",
        "",
        "## Financial Metrics",
        f"- Total return on price (unlevered view) over {metrics.get('horizon_years', 'N/A')} years: {metrics.get('roi_pct', 'N/A')}%",
        f"- Return on equity over {metrics.get('horizon_years', 'N/A')} years: {metrics.get('roe_pct', 'N/A')}% "
        f"({metrics.get('roe_annualised_pct', 'N/A')}%/yr) on equity of {_fmt_inr(metrics.get('equity_invested_inr', 'N/A'))} "
        f"(down payment {_fmt_inr(metrics.get('down_payment_inr', 'N/A'))} + stamp duty & registration "
        f"{_fmt_inr(metrics.get('stamp_duty_registration_inr', 'N/A'))}; principal repaid {_fmt_inr(metrics.get('principal_repaid_inr', 'N/A'))})",
        f"- Rental yield: {metrics.get('rental_yield_pct', 'N/A')}%",
        f"- Cap rate: {metrics.get('cap_rate_pct', 'N/A')}%",
        f"- Operating cash flow (before loan), per year: {_fmt_inr(metrics.get('operating_cash_flow_inr', 'N/A'))}",
        f"- Cash flow after EMI, per year: {_fmt_inr(metrics.get('annual_cash_flow_inr', 'N/A'))}",
        f"- Break-even (years): {metrics.get('break_even_years', 'N/A')}",
        f"- Loan assumptions: {_fmt_loan(metrics.get('loan_assumptions', {}))}",
        f"- Strong appreciation evidence: {metrics.get('strong_appreciation_evidence', 'N/A')}",
        "",
        "## Risk Assessment",
        f"- Risk score: {risk.get('risk_score', 'N/A')} / 100",
        f"- Data quality confidence: {risk.get('data_quality_confidence', 'N/A')}",
        f"- Factors: {json.dumps(risk.get('factors', {}))}",
        "",
        "## Recommendation",
        f"### Decision: {rec.get('decision', 'N/A')}",
        f"**Confidence:** {rec.get('confidence_score', 'N/A')}",
        "",
        f"{rec.get('justification', '')}",
        "",
        "### Supporting Evidence",
        *([f"- {_fmt_evidence(e)}" for e in rec.get("supporting_evidence", [])] or ["- None provided"]),
        "",
        "### Unverified Claims",
        *([f"- {_fmt_unverified(c)}" for c in report.get("unverified_claims", [])] or ["- None"]),
        "",
        "## Guardrail Result",
        f"- Status: {guardrail.get('status', 'N/A')}",
        "### Reasons",
        *([f"- {r}" for r in guardrail.get("reasons", [])] or ["- None flagged"]),
        "",
        "## Evidence Sources (RAG)",
        *([f"- {s}" for s in report.get("evidence_sources", [])] or ["- None"]),
        "",
        "## Human Approval Decision",
        f"- Approved: {human.get('approved', 'N/A')}",
        f"- Feedback: {human.get('feedback') or 'N/A'}",
        "",
        f"_Report generated by Property Alpha AI on {generated_at}._",
    ]
    return "\n".join(lines)


def _write_markdown(report: dict[str, Any], path: str, generated_at: str) -> None:
    with open(path, "w") as f:
        f.write(_render_markdown(report, generated_at))


# --------------------------------------------------------------------------
# PDF (ReportLab)
# --------------------------------------------------------------------------


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    table = Table(rows, colWidths=[5.5 * cm, 10.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
            ]
        )
    )
    return table


def _write_pdf(report: dict[str, Any], path: str, generated_at: str) -> None:
    rec = report.get("recommendation", {})
    metrics = report.get("investment_metrics", {})
    risk = report.get("risk_assessment", {})
    guardrail = report.get("guardrail_result", {})
    human = report.get("human_decision", {})
    property_data = report.get("property_data", {})
    market_data = report.get("market_data", {})

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=14)
    decision = rec.get("decision", "N/A")
    decision_style = ParagraphStyle(
        "decision",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=DECISION_COLORS.get(decision, colors.black),
    )

    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    elements: list[Any] = [
        Paragraph(PROJECT_TITLE, h1),
        Paragraph(f"Generated: {generated_at}", body),
        Spacer(1, 8),
        _kv_table(
            [
                ("Property address", str(report.get("property_address", "N/A"))),
                ("Budget", _fmt_inr(report.get("budget_inr"))),
                ("Investment strategy", str(report.get("investment_strategy", "N/A"))),
                ("Investment horizon", f"{report.get('investment_horizon_years', 'N/A')} years"),
            ]
        ),
        Paragraph("Property Summary", h2),
        _kv_table(
            [
                ("City / Locality", f"{property_data.get('city', 'N/A')} / {property_data.get('locality', 'N/A')}"),
                ("Property type", str(property_data.get("property_type", "N/A"))),
                ("Price", _fmt_inr(property_data.get("price_inr", "N/A"))),
                ("Area", f"{property_data.get('area_sqft', 'N/A')} sq ft"),
                ("Amenities", ", ".join(property_data.get("amenities", [])) or "N/A"),
            ]
        ),
        Paragraph("Market Summary", h2),
        _kv_table(
            [
                ("Appreciation rate", f"{market_data.get('appreciation_rate_5yr_pct', 'N/A')}%/yr — {_fmt_appreciation_source(market_data)}"),
                ("Demand / Supply index", f"{market_data.get('demand_index', 'N/A')} / {market_data.get('supply_index', 'N/A')}"),
                ("Avg rental yield", f"{market_data.get('rental_yield_avg_pct', 'N/A')}%"),
                ("RERA-registered projects", f"{market_data.get('rera_registered_projects_pct', 'N/A')}%"),
            ]
            if market_data
            else [("Market data", "Not available for this locality")]
        ),
        Paragraph("Financial Metrics", h2),
        _kv_table(
            [
                (f"Total return on price (unlevered view) over {metrics.get('horizon_years', 'N/A')} years", f"{metrics.get('roi_pct', 'N/A')}%"),
                (
                    f"Return on equity over {metrics.get('horizon_years', 'N/A')} years",
                    f"{metrics.get('roe_pct', 'N/A')}% ({metrics.get('roe_annualised_pct', 'N/A')}%/yr) on equity of "
                    f"{_fmt_inr(metrics.get('equity_invested_inr', 'N/A'))}",
                ),
                ("Rental yield", f"{metrics.get('rental_yield_pct', 'N/A')}%"),
                ("Cap rate", f"{metrics.get('cap_rate_pct', 'N/A')}%"),
                ("Operating cash flow (before loan), per year", _fmt_inr(metrics.get("operating_cash_flow_inr", "N/A"))),
                ("Cash flow after EMI, per year", _fmt_inr(metrics.get("annual_cash_flow_inr", "N/A"))),
                ("Break-even", f"{metrics.get('break_even_years', 'N/A')} years"),
                ("Loan assumptions", _fmt_loan(metrics.get("loan_assumptions", {}))),
                ("Strong appreciation evidence", str(metrics.get("strong_appreciation_evidence", "N/A"))),
            ]
        ),
        Paragraph("Risk Assessment", h2),
        _kv_table(
            [
                ("Risk score", f"{risk.get('risk_score', 'N/A')} / 100"),
                ("Data quality confidence", str(risk.get("data_quality_confidence", "N/A"))),
                ("Factors", json.dumps(risk.get("factors", {}))),
            ]
        ),
        Paragraph("Recommendation", h2),
        Paragraph(f"Decision: {decision}", decision_style),
        Paragraph(f"Confidence: {rec.get('confidence_score', 'N/A')}", body),
        Spacer(1, 4),
        Paragraph(rec.get("justification", ""), body),
        Spacer(1, 6),
        Paragraph(
            "Supporting evidence: "
            + ("; ".join(_fmt_evidence(e) for e in rec.get("supporting_evidence", [])) or "None provided"),
            body,
        ),
        Paragraph(
            "Unverified claims: "
            + ("; ".join(_fmt_unverified(c) for c in report.get("unverified_claims", [])) or "None"),
            body,
        ),
        Paragraph("Guardrail Result", h2),
        Paragraph(f"Status: {guardrail.get('status', 'N/A')}", body),
        Paragraph("Reasons: " + ("; ".join(guardrail.get("reasons", [])) or "None flagged"), body),
        Paragraph("Evidence Sources (RAG)", h2),
        Paragraph(", ".join(report.get("evidence_sources", [])) or "None", body),
        Paragraph("Human Approval Decision", h2),
        _kv_table(
            [
                ("Approved", str(human.get("approved", "N/A"))),
                ("Feedback", human.get("feedback") or "N/A"),
                ("Timestamp", generated_at),
            ]
        ),
    ]
    doc.build(elements)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def generate_reports(
    report: dict[str, Any], output_dir: str = "reports", base_name: str | None = None
) -> dict[str, str]:
    """Generate report.json / report.md / report.pdf (or <base_name>.* if
    given) under output_dir. Only valid for an approved final report."""
    if report.get("status") != "approved":
        raise ValueError("Refusing to generate a report for a recommendation that was not human-approved.")

    import os

    os.makedirs(output_dir, exist_ok=True)
    name = base_name or slugify(str(report.get("property_address", "report")))
    generated_at = _timestamp()

    paths = {
        "json": os.path.join(output_dir, f"{name}.json"),
        "md": os.path.join(output_dir, f"{name}.md"),
        "pdf": os.path.join(output_dir, f"{name}.pdf"),
    }

    _write_json(report, paths["json"], generated_at)
    _write_markdown(report, paths["md"], generated_at)
    _write_pdf(report, paths["pdf"], generated_at)

    return paths
