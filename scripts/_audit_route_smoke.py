"""
Throwaway audit harness: exercise every HTTP route against the offline demo
provider and assert the status codes / honesty fields, including the failure
paths (missing run, bad ids, GET on a POST-only endpoint, malformed CSV).

Usage:
  python scripts/_audit_route_smoke.py
"""
import io
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ["LLM_PROVIDER"] = "demo"

import src.config  # noqa: F401  (loads .env)

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

FAILURES = []
CHECKS = 0


def check(label, condition, detail=""):
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        FAILURES.append(f"{label} :: {detail}")


def main():
    print("\n--- health / registry ---")
    r = client.get("/api/health")
    check("GET /api/health -> 200", r.status_code == 200, r.text[:200])

    r = client.get("/api/normalizer/registry")
    check("GET /api/normalizer/registry -> 200", r.status_code == 200, r.text[:200])

    r = client.get("/openapi.json")
    check("GET /openapi.json -> 200", r.status_code == 200, r.text[:200])

    print("\n--- method guards ---")
    for path in ("/api/runs/validate", "/api/runs/upload"):
        r = client.get(path)
        check(f"GET {path} -> 405", r.status_code == 405, f"got {r.status_code}")

    print("\n--- validation failure paths ---")
    r = client.post("/api/runs/validate", files={})
    check("POST /api/runs/validate with no files -> 200 report", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        b = r.json()
        check("  no files -> valid is False", b.get("valid") is False, json.dumps(b)[:300])

    bad_adj = io.BytesIO(b"adjustment_id,note\nADJ1,nope\n")
    r = client.post("/api/runs/validate", files={"adjustments": ("adjustments.csv", bad_adj, "text/csv")})
    check("POST validate with unparseable adjustments -> valid False",
          r.status_code == 200 and r.json().get("sources", {}).get("adjustments", {}).get("valid") is False
          and r.json().get("valid") is False,
          r.text[:300])

    bad = io.BytesIO(b"not,a,valid\nheader,row,here\n")
    r = client.post(
        "/api/runs/validate",
        files={
            "payments": ("payments.csv", bad, "text/csv"),
        },
    )
    check("POST /api/runs/validate malformed payments -> 4xx/200-with-invalid",
          r.status_code in (200, 400, 422), f"got {r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        body = r.json()
        check("  malformed payments not reported valid",
              body.get("valid") is not True, json.dumps(body)[:300])

    print("\n--- unknown run id on every run-scoped route ---")
    ghost = "run_does_not_exist_zzz"
    for suffix in ("/metrics", "/exceptions", "/transactions", "/audit",
                   "/report", "/export/csv", "/diagnostics/data-integrity",
                   "/transactions/TXN001"):
        r = client.get(f"/api/runs/{ghost}{suffix}")
        check(f"GET /api/runs/<ghost>{suffix} -> 404", r.status_code == 404, f"got {r.status_code}")

    r = client.get(f"/api/runs/{ghost}/stream")
    ok = r.status_code == 200 and "run_error" in r.text
    check("GET /api/runs/<ghost>/stream -> run_error event", ok, r.text[:200])

    print("\n--- unknown evaluation group ---")
    for suffix in ("", "/status"):
        r = client.get(f"/api/evaluations/ghost_group{suffix}")
        check(f"GET /api/evaluations/ghost_group{suffix} -> 404", r.status_code == 404, f"got {r.status_code}")

    print("\n--- synthetic end-to-end run ---")
    r = client.post("/api/runs")
    check("POST /api/runs -> 201", r.status_code == 201, r.text[:300])
    if r.status_code != 201:
        return
    run_id = r.json()["run_id"]
    print(f"  run_id = {run_id}")

    r = client.get("/api/runs")
    check("GET /api/runs -> 200 list", r.status_code == 200 and isinstance(r.json(), list), r.text[:200])

    r = client.get(f"/api/runs/{run_id}/metrics")
    check("GET metrics -> 200", r.status_code == 200, r.text[:200])
    m = r.json() if r.status_code == 200 else {}
    total = m.get("total_records")
    check("metrics.total_records > 0", bool(total), str(total))
    check("metrics carries not_evaluated", "not_evaluated" in m, sorted(m)[:20])
    check("metrics carries degraded_cases", "degraded_cases" in m, sorted(m)[:20])
    check("demo run reports DEMO mode", str(m.get("llm_mode", "")).upper() == "DEMO", str(m.get("llm_mode")))
    check("explicit demo is not mislabelled as degraded", m.get("llm_degraded") is False, str(m.get("llm_degraded")))
    check("accounting identity: reconciled + exceptions == total",
          (m.get("initial_reconciled", 0) + m.get("initial_exceptions", 0)) == total,
          f"{m.get('initial_reconciled')} + {m.get('initial_exceptions')} != {total}")
    check("phase2 identity: auto + human + not_evaluated == exceptions",
          (m.get("ai_auto_resolved", 0) + m.get("human_review", 0) + (m.get("not_evaluated") or 0))
          == m.get("initial_exceptions", -1),
          f"{m.get('ai_auto_resolved')}+{m.get('human_review')}+{m.get('not_evaluated')} != {m.get('initial_exceptions')}")

    r = client.get(f"/api/runs/{run_id}/exceptions")
    check("GET exceptions -> 200", r.status_code == 200, r.text[:200])
    exceptions = r.json() if r.status_code == 200 else []
    check("exception count matches metrics",
          len(exceptions) == m.get("initial_exceptions"),
          f"{len(exceptions)} vs {m.get('initial_exceptions')}")

    r = client.get(f"/api/runs/{run_id}/transactions")
    check("GET transactions -> 200", r.status_code == 200, r.text[:200])
    txns = r.json() if r.status_code == 200 else []
    if isinstance(txns, dict):
        txns = txns.get("transactions", [])
    check("transaction count matches total_records", len(txns) == total, f"{len(txns)} vs {total}")

    if txns:
        tid = txns[0].get("transaction_id")
        r = client.get(f"/api/runs/{run_id}/transactions/{tid}")
        check(f"GET transactions/{tid} -> 200", r.status_code == 200, r.text[:200])

    r = client.get(f"/api/runs/{run_id}/audit")
    check("GET audit -> 200", r.status_code == 200, r.text[:200])

    r = client.get(f"/api/runs/{run_id}/report")
    check("GET report -> 200", r.status_code == 200, r.text[:200])

    r = client.get(f"/api/runs/{run_id}/diagnostics/data-integrity")
    check("GET diagnostics/data-integrity -> 200", r.status_code == 200, r.text[:200])

    r = client.get(f"/api/runs/{run_id}/export/csv")
    check("GET export/csv -> 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        body = r.text
        cd = r.headers.get("content-disposition", "")
        check("export filename has no CR/LF", "\r" not in cd and "\n" not in cd, repr(cd))
        rows = [ln for ln in body.splitlines() if ln.strip()]
        check("export row count == records + header", len(rows) == total + 1, f"{len(rows)} vs {total + 1}")
        check("no raw formula-leading cell in export",
              not any(cell.startswith(("=", "@")) for ln in rows[1:] for cell in ln.split(",")),
              "found a cell starting with = or @")

    r = client.get(f"/api/runs/{run_id}/stream")
    check("GET stream (replay) -> 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        check("replay carries run_completed", "run_completed" in r.text, r.text[:300])
        for field in ("not_evaluated", "degraded_cases", "has_ground_truth", "total_records",
                      "llm_mode", "llm_degraded"):
            check(f"replay carries {field}", field in r.text, r.text[:400])

    print("\n--- upload path with real CSV bytes ---")
    # Canonical schemas, matching src/generator.py's DictWriter fieldnames.
    payments = (
        "transaction_id,merchant_id,amount,date,status\n"
        "TXN001,M1,1000.00,2026-01-01,CAPTURED\n"
        "TXN002,M2,2000.00,2026-01-02,CAPTURED\n"
    )
    ledger = (
        "transaction_id,gross_amount,fee,net_amount,date,status\n"
        "TXN001,1000.00,30.00,970.00,2026-01-01,POSTED\n"
        "TXN002,2000.00,60.00,1940.00,2026-01-02,POSTED\n"
    )
    bank = (
        "bank_reference,transaction_id,credited_amount,date\n"
        "B1,TXN001,970.00,2026-01-02\n"
        "B2,TXN002,1900.00,2026-01-03\n"
    )
    adjustments = (
        "transaction_id,adjustment_type,amount,reason,date,reference\n"
        "TXN002,CHARGEBACK,40.00,Chargeback fee,2026-01-03,ADJ1\n"
    )
    files = {
        "payments": ("payments.csv", io.BytesIO(payments.encode()), "text/csv"),
        "ledger": ("ledger.csv", io.BytesIO(ledger.encode()), "text/csv"),
        "bank": ("bank.csv", io.BytesIO(bank.encode()), "text/csv"),
        "adjustments": ("adjustments.csv", io.BytesIO(adjustments.encode()), "text/csv"),
    }
    r = client.post("/api/runs/upload", files=files)
    check("POST /api/runs/upload -> 201", r.status_code == 201, r.text[:400])
    if r.status_code == 201:
        up = r.json()
        up_id = up["run_id"]
        check("upload run has 2 records", up.get("total_records") == 2, json.dumps(up)[:300])
        check("upload run reports has_ground_truth False",
              up.get("has_ground_truth") in (False, None), str(up.get("has_ground_truth")))
        r2 = client.get(f"/api/runs/{up_id}/metrics")
        check("upload run metrics -> 200", r2.status_code == 200, r2.text[:200])
        if r2.status_code == 200:
            m2 = r2.json()
            check("no ground truth -> phase2_accuracy is None",
                  m2.get("phase2_accuracy") is None, str(m2.get("phase2_accuracy")))
            check("no ground truth -> precision is None",
                  m2.get("auto_resolution_precision") is None, str(m2.get("auto_resolution_precision")))

    print("\n--- async upload/start + SSE ---")
    files = {
        "payments": ("payments.csv", io.BytesIO(payments.encode()), "text/csv"),
        "ledger": ("ledger.csv", io.BytesIO(ledger.encode()), "text/csv"),
        "bank": ("bank.csv", io.BytesIO(bank.encode()), "text/csv"),
        "adjustments": ("adjustments.csv", io.BytesIO(adjustments.encode()), "text/csv"),
    }
    r = client.post("/api/runs/upload/start", files=files)
    check("POST /api/runs/upload/start -> 202", r.status_code == 202, r.text[:400])
    if r.status_code == 202:
        async_id = r.json().get("run_id")
        check("upload/start returns run_id", bool(async_id), r.text[:200])
        with client.stream("GET", f"/api/runs/{async_id}/stream") as s:
            seen = []
            for raw in s.iter_lines():
                if raw and raw.startswith("event:"):
                    seen.append(raw.split(":", 1)[1].strip())
                if seen and seen[-1] in ("run_completed", "run_error"):
                    break
            print(f"  stream events: {seen}")
            check("stream reaches a terminal event",
                  bool(seen) and seen[-1] in ("run_completed", "run_error"), str(seen))
            check("stream emits phase1_completed", "phase1_completed" in seen, str(seen))
            check("no duplicate phase1_started",
                  seen.count("phase1_started") <= 1, str(seen))
            check("no duplicate run_completed",
                  seen.count("run_completed") <= 1, str(seen))

    print("\n--- evaluations ---")
    r = client.post("/api/evaluations", json={"runs": 2, "cases_per_run": 4, "provider": "demo"})
    check("POST /api/evaluations -> 2xx", 200 <= r.status_code < 300, f"{r.status_code} {r.text[:300]}")
    if 200 <= r.status_code < 300:
        body = r.json()
        gid = body.get("group_id") or body.get("evaluation_group_id")
        check("evaluation returns a group id", bool(gid), json.dumps(body)[:300])
        if gid:
            r2 = client.get(f"/api/evaluations/{gid}")
            check("GET /api/evaluations/<gid> -> 200", r2.status_code == 200, r2.text[:300])
            r3 = client.get(f"/api/evaluations/{gid}/status")
            check("GET /api/evaluations/<gid>/status -> 200", r3.status_code == 200, r3.text[:300])

    print(f"\n=== {CHECKS - len(FAILURES)}/{CHECKS} checks passed ===")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
