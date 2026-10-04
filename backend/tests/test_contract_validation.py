"""与 Vitest 运行同一输入语料，补足 JSON Schema 字段比较无法检测的校验和默认值。"""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.shared_models import MODELS

FIXTURES = Path(__file__).resolve().parents[2] / "frontend/packages/shared/fixtures"
CASES = json.loads((FIXTURES / "validation-cases.json").read_text(encoding="utf-8"))
CONTEXT = json.loads((FIXTURES / "interview-context.sample.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_validation_corpus(case):
    base = CONTEXT
    for key in case.get("base_path", "").split("."):
        if key:
            base = base[int(key)] if isinstance(base, list) else base[key]
    payload = deepcopy(base) if case.get("base_path") else {}
    payload.update(case.get("set", {}))
    for key in case.get("remove", []):
        payload.pop(key, None)
    model = MODELS[case["schema"]]
    if not case["valid"]:
        with pytest.raises(ValidationError):
            model.model_validate(payload)
    else:
        result = model.model_validate(payload).model_dump(mode="json")
        for key, expected in case.get("expected", {}).items():
            assert result[key] == expected
