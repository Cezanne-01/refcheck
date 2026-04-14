from __future__ import annotations
import json
from refcheck.schema.models import DraftReport


def export_json(report: DraftReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )
