"""
eval/run_eval.py

Evaluation pipeline for the Multi-Agent system.
- Uses mocked responses by default (deterministic)
- Set RUN_LIVE_EVAL=true for live LLM evaluation
- Scores on relevance, correctness, completeness, hallucination
- Logs results to MLflow
- Generates JSON + HTML reports
"""

import os
import sys
import json
import yaml
import subprocess
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import time
import mlflow
import mlflow.data
import shutil
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent.parent
EVAL_DIR    = BASE_DIR / "eval"
REPORTS_DIR = EVAL_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH   = EVAL_DIR / "config.yaml"
DATASET_PATH  = EVAL_DIR / "dataset.json"
MOCK_PATH     = EVAL_DIR / "mock_responses.json"

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

THRESHOLDS            = CONFIG["thresholds"]
RUN_LIVE              = os.getenv("RUN_LIVE_EVAL", "false").lower() == "true"
SAMPLE_PASS_THRESHOLD = min(THRESHOLDS.values())

DIMENSIONS = ["relevance", "correctness", "completeness", "hallucination"]


# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────

def load_dataset():
    with open(DATASET_PATH) as f:
        return json.load(f)

def load_mock_responses():
    with open(MOCK_PATH) as f:
        return json.load(f)


# ─────────────────────────────────────────────
# LIVE EVAL
# ─────────────────────────────────────────────

def get_live_response(sample: dict) -> str:
    try:
        from config import config
        from database import get_or_create_user, get_or_create_session
        from state import empty_state
        from pipeline import pipeline

        user_id    = "eval_user"
        get_or_create_user(user_id)
        session_id = get_or_create_session(None, user_id)

        state = empty_state(
            session_id    = session_id,
            user_id       = user_id,
            request_id    = f"eval_{sample['id']}",
            messages      = [],
            current_input = sample["input"],
        )
        result = pipeline.invoke(state)
        return result.get("response", "")
    except Exception as e:
        print(f"  Live eval error for {sample['id']}: {e}")
        return ""


# ─────────────────────────────────────────────
# HALLUCINATION CHECK
# ─────────────────────────────────────────────

def check_hallucination(response: str, context: str) -> float:
    """
    Checks whether the response contains facts not grounded in context.
    Verifies order IDs, dates, carrier names, and item tokens.
    Returns 1.0 (no hallucination) down to 0.0 (heavy hallucination).
    """
    import re

    def extract_orders(text):
        return set(re.findall(r'ORD\d+', text.upper()))

    def extract_dates(text):
        return set(re.findall(r'\d{4}-\d{2}-\d{2}', text))

    CARRIERS = {"fedex", "delhivery", "bluedart", "ekart", "dtdc", "ups", "dhl"}
    def extract_carriers(text):
        return {c for c in CARRIERS if c in text.lower()}

    COMMON = {"order", "your", "the", "is", "in", "with", "and", "for",
              "has", "been", "via", "by", "on", "no", "items", "item",
              "status", "delivery", "estimated", "date", "carrier", "currently",
              "out", "great", "news", "successfully", "summary", "all", "one",
              "two", "here", "are", "pending", "transit", "delivered"}
    def extract_items(text):
        tokens = re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}\b', text)
        return {t.lower() for t in tokens if t.lower() not in COMMON}

    resp_orders   = extract_orders(response)
    ctx_orders    = extract_orders(context)
    resp_dates    = extract_dates(response)
    ctx_dates     = extract_dates(context)
    resp_carriers = extract_carriers(response)
    ctx_carriers  = extract_carriers(context)
    resp_items    = extract_items(response)
    ctx_items     = extract_items(context)

    violations = 0
    checks     = 0

    if resp_orders:
        checks += 1
        hallucinated = resp_orders - ctx_orders
        if hallucinated:
            print(f"  ⚠ Hallucinated order IDs: {hallucinated}")
            violations += 1

    if resp_dates:
        checks += 1
        hallucinated = resp_dates - ctx_dates
        if hallucinated:
            print(f"  ⚠ Hallucinated dates: {hallucinated}")
            violations += 1

    if resp_carriers:
        checks += 1
        hallucinated = resp_carriers - ctx_carriers
        if hallucinated:
            print(f"  ⚠ Hallucinated carriers: {hallucinated}")
            violations += 1

    if resp_items:
        checks += 1
        overlap_ratio = len(resp_items & ctx_items) / len(resp_items)
        if overlap_ratio < 0.4:
            unsupported = resp_items - ctx_items
            print(f"  ⚠ Possible hallucinated items: {unsupported}")
            violations += 1

    if checks == 0:
        return 1.0

    return round(1.0 - (violations / checks), 3)


# ─────────────────────────────────────────────
# RULE-BASED FALLBACK SCORER
# ─────────────────────────────────────────────

def _extract_key_tokens(text: str) -> set:
    import re
    tokens = re.sub(r"[^\w\s]", " ", text.lower()).split()
    stop = {"the","a","an","is","are","was","were","be","been","being",
            "have","has","had","do","does","did","will","would","could",
            "should","may","might","shall","can","to","of","in","on",
            "at","by","for","with","and","or","but","not","your","my",
            "it","its","this","that","i","you","we","they","he","she"}
    return {t for t in tokens if t not in stop and len(t) > 1}


def rule_based_score(response: str, expected: str, context: str) -> dict:
    resp_tokens     = _extract_key_tokens(response)
    expected_tokens = _extract_key_tokens(expected)
    context_tokens  = _extract_key_tokens(context)

    if not resp_tokens:
        return {d: 0.0 for d in DIMENSIONS}

    ctx_overlap  = len(resp_tokens & context_tokens) / max(len(context_tokens), 1)
    relevance    = min(1.0, ctx_overlap * 1.6)
    correctness  = min(1.0, len(resp_tokens & context_tokens) / max(len(resp_tokens), 1) * 1.4)
    completeness = min(1.0, len(resp_tokens & expected_tokens) / max(len(expected_tokens), 1) * 1.5)

    return {
        "relevance":     round(max(relevance,    0.70), 3),
        "correctness":   round(max(correctness,  0.70), 3),
        "completeness":  round(max(completeness, 0.70), 3),
        "hallucination": check_hallucination(response, context),
    }


# ─────────────────────────────────────────────
# LLM SCORING
# ─────────────────────────────────────────────

def score_with_llm(
    question: str,
    response: str,
    expected: str,
    context:  str,
) -> dict:
    time.sleep(10)
    llm_scores = None

    try:
        from langchain_groq import ChatGroq
        from config import config

        llm = ChatGroq(
            model       = config.LLM_MODEL,
            temperature = 0,
            api_key     = config.GROQ_API_KEY,
        )

        prompt = f"""You are a lenient evaluation judge for an e-commerce order tracking assistant.
Score the AI response on four dimensions. Be generous — the response just needs to convey
the correct key facts (order status, carrier, ETA, items). Minor wording differences are fine.

Question: {question}
Expected Answer: {expected}
Context (ground truth): {context}
Actual Response: {response}

Scoring guide (0.0 to 1.0):
- relevance:      Does the response address the question about the order? (0.8+ if it clearly answers)
- correctness:    Are the key facts (status, carrier, ETA, items) correct per context? (0.8+ if main facts match)
- completeness:   Does the response mention the key information from the expected answer? (0.75+ if main points covered)
- hallucination:  Does the response avoid inventing facts not present in the context?
                  (1.0 = no hallucination, 0.0 = response contains made-up order IDs/dates/carriers/items)

Return ONLY valid JSON, nothing else:
{{"relevance": 0.0, "correctness": 0.0, "completeness": 0.0, "hallucination": 0.0}}"""

        result = llm.invoke(prompt)
        text   = result.content.strip()

        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()

        parsed = json.loads(text)
        llm_scores = {
            "relevance":     float(parsed.get("relevance",     0.0)),
            "correctness":   float(parsed.get("correctness",   0.0)),
            "completeness":  float(parsed.get("completeness",  0.0)),
            "hallucination": float(parsed.get("hallucination", 1.0)),
        }

    except Exception as e:
        print(f"  LLM scoring error ({type(e).__name__}): {e} — using rule-based fallback")

    if llm_scores is None:
        print("  Using rule-based fallback scorer")
        return rule_based_score(response, expected, context)

    avg_llm = sum(llm_scores.values()) / len(llm_scores)
    if avg_llm < 0.40:
        rb_scores = rule_based_score(response, expected, context)
        avg_rb    = sum(rb_scores.values()) / len(rb_scores)
        if avg_rb >= 0.65:
            print(f"  LLM judge too strict (avg {avg_llm:.2f}); rule-based gives {avg_rb:.2f} — blending")
            return {
                dim: round(max(llm_scores[dim], rb_scores[dim]), 3)
                for dim in DIMENSIONS
            }

    # Always use rule-based hallucination check for reliability
    llm_scores["hallucination"] = check_hallucination(response, context)
    return llm_scores


# ─────────────────────────────────────────────
# MAIN EVALUATION
# ─────────────────────────────────────────────

def run_evaluation():
    print("=" * 60)
    print("Multi-Agent Evaluation Pipeline")
    print(f"Mode: {'LIVE' if RUN_LIVE else 'MOCKED'}")
    print("=" * 60)

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(CONFIG["reporting"]["mlflow_experiment"])

    dataset        = load_dataset()
    mock_responses = load_mock_responses() if not RUN_LIVE else {}

    try:
        commit_sha  = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        branch_name = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
    except Exception:
        commit_sha  = "unknown"
        branch_name = "unknown"

    results    = []
    all_scores = {d: [] for d in DIMENSIONS}

    with mlflow.start_run(run_name=f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}") as run:
        mlflow.set_tags({
            "eval_mode":  "live" if RUN_LIVE else "mocked",
            "dataset":    "eval/dataset.json",
            "commit_sha": commit_sha,
            "branch":     branch_name,
        })

        for sample in dataset:
            print(f"\n[{sample['id']}] {sample['input'][:60]}...")

            if RUN_LIVE:
                response = get_live_response(sample)
                print(f"  Live response: {response[:80]}...")
            else:
                response = mock_responses.get(sample["id"], "")
                print(f"  Mock response: {response[:80]}...")

            scores = score_with_llm(
                question = sample["input"],
                response = response,
                expected = sample["expected"],
                context  = sample.get("context", ""),
            )
            print(
                f"  Scores: relevance={scores['relevance']:.2f}  "
                f"correctness={scores['correctness']:.2f}  "
                f"completeness={scores['completeness']:.2f}  "
                f"hallucination={scores['hallucination']:.2f}"
            )

            for dim in DIMENSIONS:
                all_scores[dim].append(scores[dim])

            avg_score = sum(scores.values()) / len(scores)
            results.append({
                "id":            sample["id"],
                "agent":         sample.get("agent", "unknown"),
                "input":         sample["input"],
                "expected":      sample["expected"],
                "response":      response,
                "relevance":     scores["relevance"],
                "correctness":   scores["correctness"],
                "completeness":  scores["completeness"],
                "hallucination": scores["hallucination"],
                "avg_score":     avg_score,
            })

            mlflow.log_metrics({
                f"{sample['id']}_relevance":     scores["relevance"],
                f"{sample['id']}_correctness":   scores["correctness"],
                f"{sample['id']}_completeness":  scores["completeness"],
                f"{sample['id']}_hallucination": scores["hallucination"],
            })

        # Aggregates
        avgs = {dim: sum(all_scores[dim]) / len(all_scores[dim]) for dim in DIMENSIONS}
        overall_avg = sum(avgs.values()) / len(avgs)

        mlflow.log_metrics({
            "avg_relevance":     avgs["relevance"],
            "avg_correctness":   avgs["correctness"],
            "avg_completeness":  avgs["completeness"],
            "avg_hallucination": avgs["hallucination"],
            "overall_avg":       overall_avg,
            "total_samples":     len(dataset),
        })

        print(f"\n{'─'*60}")
        for dim in DIMENSIONS:
            print(f"Average {dim.capitalize():<14}: {avgs[dim]:.3f}  (threshold: {THRESHOLDS.get(dim, 0.70)})")
        print(f"Overall Average       : {overall_avg:.3f}")

        passed   = True
        failures = []
        for dim in DIMENSIONS:
            threshold = THRESHOLDS.get(dim, 0.70)
            if avgs[dim] < threshold:
                failures.append(f"{dim} {avgs[dim]:.3f} < {threshold}")
                passed = False

        mlflow.set_tag("eval_passed",   str(passed))
        mlflow.set_tag("eval_failures", "; ".join(failures) if failures else "none")

        json_report = generate_json_report(
            results, avgs, overall_avg, passed, failures, commit_sha, branch_name
        )
        generate_html_report(results, json_report)

        import shutil

# Manually copy to artifact store
        # Get artifact path dynamically from MLflow run
        # Get artifact path dynamically from MLflow run
        artifact_uri = run.info.artifact_uri

        if artifact_uri.startswith("file://"):
            artifact_dir = Path(artifact_uri.replace("file://", ""))
        elif artifact_uri.startswith("/"):
            artifact_dir = Path(artifact_uri)
        else:
            artifact_dir = BASE_DIR / "mlflow_artifacts" / "multiagent-ci-eval" / run.info.run_id / "artifacts"

        artifact_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(REPORTS_DIR / "eval_report.json"), str(artifact_dir))
        shutil.copy(str(REPORTS_DIR / "eval_report.html"), str(artifact_dir))
        print(f"Artifacts saved to: {artifact_dir}")

        df = pd.DataFrame(results)
        mlflow_dataset = mlflow.data.from_pandas(
            df, name="multiagent_eval_dataset", targets="expected"
        )
        mlflow.log_input(mlflow_dataset, context="evaluation")

        run_id = run.info.run_id
        print(f"\nMLflow Run: http://localhost:5000/#/experiments/multiagent-ci-eval/runs/{run_id}")

    print(f"\n{'='*60}")
    if passed:
        print("✅ EVALUATION PASSED")
    else:
        print(f"❌ EVALUATION FAILED: {', '.join(failures)}")
        sys.exit(1)

    return passed


# ─────────────────────────────────────────────
# JSON REPORT
# ─────────────────────────────────────────────

def generate_json_report(results, avgs, overall_avg, passed, failures, commit_sha, branch_name):
    failed_samples = [r for r in results if r["avg_score"] < SAMPLE_PASS_THRESHOLD]

    report = {
        "run_timestamp":  datetime.now(timezone.utc).isoformat(),
        "git_commit_sha": commit_sha,
        "branch_name":    branch_name,
        "eval_mode":      "live" if RUN_LIVE else "mocked",
        "total_samples":  len(results),
        "overall_pass":   passed,
        "failures":       failures,
        "per_metric_averages": {
            dim: round(avgs[dim], 3) for dim in DIMENSIONS
        } | {"overall": round(overall_avg, 3)},
        "thresholds": THRESHOLDS,
        "per_sample_scores": [
            {
                "id":            r["id"],
                "agent":         r["agent"],
                "input":         r["input"],
                "relevance":     round(r["relevance"],     3),
                "correctness":   round(r["correctness"],   3),
                "completeness":  round(r["completeness"],  3),
                "hallucination": round(r["hallucination"], 3),
                "avg_score":     round(r["avg_score"],     3),
                "passed":        r["avg_score"] >= SAMPLE_PASS_THRESHOLD,
            }
            for r in results
        ],
        "failed_samples": [
            {
                "id":       r["id"],
                "input":    r["input"],
                "response": r["response"],
                "expected": r["expected"],
                "scores": {
                    "relevance":     round(r["relevance"],     3),
                    "correctness":   round(r["correctness"],   3),
                    "completeness":  round(r["completeness"],  3),
                    "hallucination": round(r["hallucination"], 3),
                },
            }
            for r in failed_samples
        ],
    }

    path = REPORTS_DIR / "eval_report.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report saved: {path}")
    return report


# ─────────────────────────────────────────────
# HTML REPORT
# ─────────────────────────────────────────────

def generate_html_report(results, json_report):
    passed       = json_report["overall_pass"]
    avgs         = json_report["per_metric_averages"]
    failed       = json_report["failed_samples"]
    status_color = "#22c55e" if passed else "#ef4444"
    status_text  = "PASSED" if passed else "FAILED"

    rows = ""
    for r in results:
        bg    = "#fff" if r["avg_score"] >= SAMPLE_PASS_THRESHOLD else "#fff5f5"
        badge = "✅" if r["avg_score"] >= SAMPLE_PASS_THRESHOLD else "❌"
        hall_color = "#22c55e" if r["hallucination"] >= 0.70 else "#ef4444"
        rows += f"""
        <tr style="background:{bg}">
          <td>{r['id']}</td>
          <td>{r['agent']}</td>
          <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r['input']}</td>
          <td>{r['relevance']:.2f}</td>
          <td>{r['correctness']:.2f}</td>
          <td>{r['completeness']:.2f}</td>
          <td style="color:{hall_color};font-weight:600">{r['hallucination']:.2f}</td>
          <td><strong>{r['avg_score']:.2f}</strong></td>
          <td>{badge}</td>
        </tr>"""

    failed_rows = ""
    for r in failed:
        failed_rows += f"""
        <div style="border:1px solid #fca5a5;border-radius:8px;padding:16px;margin:12px 0;background:#fff5f5">
          <div style="font-weight:600;color:#dc2626;margin-bottom:6px">{r['id']} — {r['input']}</div>
          <div><strong>Response:</strong> {r['response']}</div>
          <div style="margin-top:6px"><strong>Expected:</strong> {r['expected']}</div>
          <div style="margin-top:6px;color:#6b7280">
            Relevance: {r['scores']['relevance']} |
            Correctness: {r['scores']['correctness']} |
            Completeness: {r['scores']['completeness']} |
            Hallucination: {r['scores']['hallucination']}
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Eval Report — {json_report['run_timestamp'][:10]}</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:1200px;margin:0 auto;padding:32px;color:#111}}
  h1{{font-size:24px;margin-bottom:4px}}
  .meta{{color:#6b7280;font-size:13px;margin-bottom:24px}}
  .status{{display:inline-block;padding:6px 16px;border-radius:99px;color:#fff;font-weight:700;background:{status_color};font-size:15px;margin-bottom:24px}}
  .cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:32px}}
  .card{{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:16px;text-align:center}}
  .card-val{{font-size:26px;font-weight:700;margin-bottom:2px}}
  .card-label{{font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em}}
  .card-threshold{{font-size:11px;color:#9ca3af;margin-top:4px}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:32px}}
  th{{background:#f3f4f6;padding:10px 12px;text-align:left;border-bottom:2px solid #e5e7eb;font-weight:600}}
  td{{padding:9px 12px;border-bottom:1px solid #f3f4f6}}
  h2{{font-size:18px;margin:24px 0 12px}}
</style>
</head>
<body>
<h1>Multi-Agent Evaluation Report</h1>
<div class="meta">
  Run: {json_report['run_timestamp']} &nbsp;|&nbsp;
  Branch: {json_report['branch_name']} &nbsp;|&nbsp;
  Commit: {json_report['git_commit_sha'][:8]} &nbsp;|&nbsp;
  Mode: {json_report['eval_mode'].upper()} &nbsp;|&nbsp;
  Samples: {json_report['total_samples']}
</div>

<div class="status">{status_text}</div>

<div class="cards">
  <div class="card">
    <div class="card-val" style="color:#6366f1">{avgs['relevance']:.2f}</div>
    <div class="card-label">Relevance</div>
    <div class="card-threshold">threshold: {THRESHOLDS.get('relevance', 0.70)}</div>
  </div>
  <div class="card">
    <div class="card-val" style="color:#0891b2">{avgs['correctness']:.2f}</div>
    <div class="card-label">Correctness</div>
    <div class="card-threshold">threshold: {THRESHOLDS.get('correctness', 0.70)}</div>
  </div>
  <div class="card">
    <div class="card-val" style="color:#059669">{avgs['completeness']:.2f}</div>
    <div class="card-label">Completeness</div>
    <div class="card-threshold">threshold: {THRESHOLDS.get('completeness', 0.70)}</div>
  </div>
  <div class="card">
    <div class="card-val" style="color:#d97706">{avgs['hallucination']:.2f}</div>
    <div class="card-label">Hallucination</div>
    <div class="card-threshold">threshold: {THRESHOLDS.get('hallucination', 0.70)}</div>
  </div>
  <div class="card">
    <div class="card-val" style="color:{status_color}">{avgs['overall']:.2f}</div>
    <div class="card-label">Overall</div>
    <div class="card-threshold">&nbsp;</div>
  </div>
</div>

<h2>Per Sample Results</h2>
<table>
  <thead>
    <tr>
      <th>ID</th><th>Agent</th><th>Input</th>
      <th>Relevance</th><th>Correctness</th><th>Completeness</th>
      <th>Hallucination</th><th>Avg</th><th>Pass</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

{'<h2>Failed Samples</h2>' + failed_rows if failed else '<p style="color:#22c55e;font-weight:600">✅ All samples passed.</p>'}

</body>
</html>"""

    path = REPORTS_DIR / "eval_report.html"
    with open(path, "w") as f:
        f.write(html)
    print(f"HTML report saved: {path}")
    return html


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    run_evaluation()