"""Ask CloudPilot: grounded, structured answers.

Figures in answers always come from the deterministic engines (cards). The
optional LLM may only rephrase the narrative around them.
"""
from __future__ import annotations

import json
import os
import re

SYSTEM_PROMPT = (
    "You are CloudPilot, a cautious cloud cost analysis copilot. Answer ONLY from the supplied JSON context. "
    "Never invent resources, figures or savings; quote numbers exactly as given. Distinguish facts from assumptions. "
    "State clearly when information is missing. Never recommend destructive changes without verification and approval. "
    "Data is synthetic demo data. Keep answers under 120 words; structured cards with figures are shown separately."
)


def _rec_card(r: dict, dataset_id: str) -> dict:
    return {
        "type": "recommendation",
        "id": r["id"],
        "title": r["title"],
        "resource_id": r["resource_id"],
        "service": r["service"],
        "monthly_savings": r["savings"]["monthly"],
        "savings_formula": r["savings"]["formula"],
        "risk_level": r["risk"]["level"],
        "confidence_level": r["confidence"]["level"],
        "priority_score": r["priority"]["score"],
        "status": r.get("status", "open"),
        "why": r["summary"],
        "next_step": r["suggested_action"],
        "verify": r["verify_before_acting"][:2],
        "missing_evidence": r["confidence"]["missing_evidence"],
        "source": f"Synthetic resource inventory · {r['resource_id']} · {dataset_id}",
    }


def _anomaly_card(a: dict, dataset_id: str) -> dict:
    return {
        "type": "anomaly",
        "id": a["id"],
        "service": a["service"],
        "anomaly_type": a["type_label"],
        "severity": a["severity"],
        "status": a.get("status", "open"),
        "baseline": a["baseline"]["value"],
        "baseline_method": f"{a['baseline']['method']} ({a['baseline']['observation_window']['months']} months)",
        "deviation_percent": a["deviation"]["percent"],
        "change_percent": a["change_percent"],
        "previous_cost": a["previous_cost"],
        "current_cost": a["current_cost"],
        "difference": round(a["current_cost"] - a["previous_cost"], 2),
        "period": f"{a['previous_month']} → {a['current_month']}",
        "note": "Unusual spend is not proof of waste or of a specific cause.",
        "source": f"Synthetic billing data · {dataset_id}",
    }


def _find_rec(q: str, recs: list[dict]):
    for r in recs:
        if r["id"].lower() in q or r["resource_id"].lower() in q:
            return r
    return None


def _rules_answer(q: str, dash: dict, recs: list[dict], anoms: list[dict], dataset_id: str) -> tuple[str, list[dict]]:
    open_recs = [r for r in recs if r["status"] in ("open", "investigating", "planned")]

    specific = _find_rec(q, recs)
    if specific:
        c = specific["confidence"]
        missing = f" Missing evidence: {', '.join(c['missing_evidence'])}." if c["missing_evidence"] else ""
        return (f"CloudPilot flagged {specific['resource_id']} because: {specific['detected']} "
                f"Priority {specific['priority']['score']} ({specific['priority']['level']}), "
                f"{c['level'].lower()} confidence, {specific['risk']['level'].lower()} operational risk.{missing}",
                [_rec_card(specific, dataset_id)])

    if "dismiss" in q:
        dismissed = [r for r in recs if r["status"] == "dismissed"]
        if not dismissed:
            return "You have not dismissed any recommendations yet.", []
        return ("Dismissed recommendations: " + "; ".join(
            f"{r['resource_id']} ({r['lifecycle'].get('reason_label') or 'no reason'})" for r in dismissed) + ".",
            [_rec_card(r, dataset_id) for r in dismissed])

    if "high" in q and "risk" in q:
        high = [r for r in recs if r["risk"]["level"] == "High"]
        if not high:
            return "No recommendations are currently rated high operational risk.", []
        return (f"{len(high)} recommendation(s) carry high operational risk. Validate them carefully before acting.",
                [_rec_card(r, dataset_id) for r in high])

    if "anomal" in q or "spike" in q or "growth" in q or ("why" in q and "ec2" in q):
        if not anoms:
            return "No anomalies were detected this month. This does not guarantee spending is normal.", []
        named = [x for x in anoms if x["service"].lower() in q]
        a = named[0] if named else anoms[0]
        related = [r for r in open_recs if r["service"] == a["service"]]
        text = (f"{a['severity']} severity · {a['type_label'].lower()}: {a['summary']} "
                f"Month-over-month it changed {a['change_percent']:+}% ({a['previous_month']} → {a['current_month']}). "
                "Unusual spend is not proof of a cause. Start with the resource-level breakdown for that month.")
        others = [x for x in anoms if x is not a]
        if others:
            text += f" {len(others)} other anomaly(ies) were detected this month."
        if related:
            text += f" {len(related)} open {a['service']} recommendation(s) may be related."
        return text, [_anomaly_card(a, dataset_id)] + [_rec_card(r, dataset_id) for r in related[:2]]

    if any(w in q for w in ("first", "priorit", "start", "best", "top")) or \
       any(w in q for w in ("recommend", "save", "saving", "optimi", "idle", "unused", "investigate")):
        if not open_recs:
            return "There are no open recommendations in the current demo inventory.", []
        if any(w in q for w in ("first", "priorit", "start", "best", "top")):
            top = open_recs[0]
            return (f"Start with {top['resource_id']}: it has the highest priority score ({top['priority']['score']}), "
                    "which combines savings, confidence, business impact, ease and risk.", [_rec_card(top, dataset_id)])
        total = sum(r["savings"]["monthly"] for r in open_recs)
        return (f"{len(open_recs)} active opportunities, estimated ${total:,.2f}/month in total (estimates, not guaranteed). "
                "Ranked by priority score:", [_rec_card(r, dataset_id) for r in open_recs[:3]])

    if any(w in q for w in ("increase", "spend", "bill", "cost", "service")):
        top = sorted(dash["service_breakdown"].items(), key=lambda x: x[1], reverse=True)[:3]
        cards = [_anomaly_card(a, dataset_id) for a in anoms[:1]]
        return (f"In {dash['month']} spend was ${dash['total_spend']:,.2f} vs ${dash['previous_spend']:,.2f} the month before "
                f"({dash['change_percent']:+}%). Largest services: "
                + ", ".join(f"{s} (${v:,.2f})" for s, v in top)
                + ". This shows where to investigate, not the cause.", cards)

    return ("I can explain spend changes, anomalies and recommendations. Try 'What should I investigate first?', "
            "'Show me high-risk recommendations' or 'Why was i-demo-01 flagged?'.", [])


def answer(question: str, dash: dict, recs: list[dict], anoms: list[dict], dataset_id: str) -> dict:
    q = re.sub(r"\s+", " ", question.lower())
    text, cards = _rules_answer(q, dash, recs, anoms, dataset_id)
    sources = sorted({c["source"] for c in cards}) or [f"Synthetic demo dataset · {dataset_id}"]

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            context = {
                "dataset_id": dataset_id,
                "month": dash["month"], "total_spend": dash["total_spend"], "previous_spend": dash["previous_spend"],
                "service_breakdown": dash["service_breakdown"], "anomalies": anoms,
                "recommendations": [_rec_card(r, dataset_id) for r in recs],
                "cards_shown_to_user": cards,
            }
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Context: {json.dumps(context)}\n\nQuestion: {question}"},
                ],
            )
            return {"answer": response.choices[0].message.content, "cards": cards, "sources": sources,
                    "mode": "llm_grounded_demo"}
        except Exception:
            pass
    return {"answer": text, "cards": cards, "sources": sources, "mode": "grounded_rules"}
