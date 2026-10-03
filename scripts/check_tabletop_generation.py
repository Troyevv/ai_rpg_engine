"""Run four real authoring requests against an already configured RPG server.

Uses server-side credentials. Creates drafts, never starts games or repairs output.
Prints diagnostics and draft IDs, not raw definitions or provider credentials.
"""

import argparse
import json

import requests

IDEAS = [
    "Мрачное фэнтези: охотник расследует исчезновения в шахтёрском городе.",
    "Городское расследование: пропавший архивариус и соперничающие гильдии.",
    "Подземелье с несколькими NPC и фракциями, у каждой свои цели.",
    "Приключение с большим количеством секретов и отношений NPC: заговор при дворе.",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--provider", required=True, choices=["local", "deepseek", "compatible"]
    )
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    config = {"provider": args.provider, "model": args.model, "max_tokens": 16000}
    counts = {"VALID": 0, "INVALID": 0, "ERROR": 0}
    for idea in IDEAS:
        try:
            response = requests.post(
                args.url.rstrip("/") + "/api/tabletop/generate",
                json={"options": {"idea": idea}, "config": config},
                timeout=(10, 900),
            )
            body = response.json()
            valid = (
                response.status_code == 200 and body.get("generation_status") == "VALID"
            )
            invalid = response.status_code == 409 and bool(
                body.get("validation_issues")
            )
            status = "VALID" if valid else "INVALID" if invalid else "ERROR"
            report = {
                "idea": idea,
                "provider": args.provider,
                "model": args.model,
                "status": status,
                "http_status": response.status_code,
                "draft_id": body.get("id") if valid else body.get("draft_id"),
                "stage": body.get("stage"),
                "issues": body.get("validation_issues", []),
            }
            if status == "ERROR":
                report["message"] = (
                    "Запрос не завершил проверку кампании; проверь настройки и журнал сервера."
                )
        except (requests.RequestException, ValueError):
            status = "ERROR"
            report = {
                "idea": idea,
                "status": status,
                "message": "Сервер недоступен или вернул не-JSON ответ.",
            }
        counts[status] += 1
        print(json.dumps(report, ensure_ascii=False), flush=True)
    print(json.dumps({"totals": counts}, ensure_ascii=False))
    return 1 if counts["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
