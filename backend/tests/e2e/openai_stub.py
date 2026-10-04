"""Offline stand-in for the OpenAI Responses API, used only by the end-to-end test.

    cd backend && .venv/bin/python -m tests.e2e.openai_stub --port 8765

The backend reaches it through ``OPENAI_BASE_URL=http://127.0.0.1:8765/v1``, so the
real ``OpenAILLMClient``, output validation, claim validation and trace recording all
run unchanged; only the network peer is fake. It is test code and never ships in
``app/``.

It answers ``POST /v1/responses`` deterministically by reading the JSON it is sent:
an Evidence Bundle gets a brief, an action-proposal context gets an
``open_investigation`` draft. It cites only IDs present in that input and words the
deployment as temporal proximity, never cause. ``GET /health`` is a readiness probe.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

STUB_MODEL = "e2e-stub"
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _user_payload(body: dict[str, Any]) -> dict[str, Any]:
    for message in body.get("input", []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):  # content parts
                content = "".join(part.get("text", "") for part in content)
            return dict(json.loads(content))
    raise ValueError("No user message in the request.")


def _top_contributor(bundle: dict[str, Any], anomaly_id: str) -> dict[str, Any] | None:
    ranked = [c for c in bundle.get("contributors", []) if c["anomaly_evidence_id"] == anomaly_id]
    ranked.sort(key=lambda c: (c["family_key"] != "region+customer_tier", c["rank"]))
    return ranked[0] if ranked else None


def draft_brief(bundle: dict[str, Any]) -> dict[str, Any]:
    """A grounded brief built only from the bundle's own IDs and deterministic text."""
    anomalies = sorted(
        bundle.get("anomalies", []),
        key=lambda a: (_SEVERITY_RANK.get(a["severity"], 9), a["evidence_id"]),
    )
    if not anomalies:
        return {
            "headline": "No anomalies in the latest window",
            "summary": "The evidence bundle shows no detected anomalies to report.",
            "claims": [],
            "attention_items": [],
        }
    top = anomalies[0]
    claims: list[dict[str, Any]] = [
        {
            "claim_type": "observation",
            "text": f"{top['label']}: {top['explanation']}",
            "evidence_ids": [top["evidence_id"], top["metric_evidence_id"]],
        }
    ]
    contributor = _top_contributor(bundle, top["evidence_id"])
    if contributor is not None:
        claims.append(
            {
                "claim_type": "observation",
                "text": contributor["statement"],
                "evidence_ids": [contributor["evidence_id"]],
            }
        )
    for event in bundle.get("related_events", [])[:1]:
        claims.append(
            {
                "claim_type": "inference",
                "text": (
                    f'The event "{event["title"]}" occurred near this window and coincided '
                    "with the increase; the timing warrants investigation."
                ),
                "evidence_ids": [event["evidence_id"], top["evidence_id"]],
            }
        )
    return {
        "headline": f"{top['label']} warrants investigation",
        "summary": (
            f"{len(anomalies)} anomaly(ies) were detected in the latest window; the most "
            f"severe is {top['severity']}."
        ),
        "claims": claims,
        "attention_items": ["Review the top contributing segment and the nearby timeline event."],
    }


def draft_action(context: dict[str, Any]) -> dict[str, Any]:
    allowed: list[str] = context["allowed_evidence_ids"]
    cited = [i for i in allowed if i.startswith("ANOM-")][:1]
    cited += [i for i in allowed if i.startswith("SEG-")][:1]
    cited += [i for i in allowed if i.startswith("EVT-")][:1]
    return {
        "action_type": "open_investigation",
        "title": "Investigate the elevated Billing support volume",
        "description": (
            "Review Billing tickets in the analysis window, concentrating on the top "
            "contributing segment and the deployment that occurred near the window start."
        ),
        "rationale": (
            "The cited anomaly and segment show where the increase is concentrated; the "
            "deployment coincided with it and warrants investigation."
        ),
        "investigation_steps": [
            "Sample Billing tickets from the top contributing segment.",
            "Compare ticket subjects before and after the deployment time.",
            "Confirm with the release owner whether the deployment touched billing flows.",
        ],
        "evidence_ids": cited,
    }


def respond(body: dict[str, Any]) -> dict[str, Any]:
    payload = _user_payload(body)
    output = draft_action(payload) if "brief_id" in payload else draft_brief(payload)
    text = json.dumps(output)
    return {
        "id": "resp_e2e_stub",
        "object": "response",
        "created_at": 0,
        "model": body.get("model", STUB_MODEL),
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_e2e_stub",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": len(json.dumps(payload)) // 4,
            "output_tokens": len(text) // 4,
            "total_tokens": (len(json.dumps(payload)) + len(text)) // 4,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path.rstrip("/") == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        if self.path.rstrip("/") != "/v1/responses":
            self._send(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            self._send(200, respond(json.loads(self.rfile.read(length))))
        except (ValueError, KeyError) as exc:
            self._send(400, {"error": {"message": f"stub could not answer: {type(exc).__name__}"}})

    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # keep test output quiet; requests carry no secrets but need no echo


def make_server(port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), _Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline OpenAI Responses stub (tests only).")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"OpenAI stub listening on http://127.0.0.1:{args.port}/v1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
