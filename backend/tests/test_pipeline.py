from app.schemas.imdb import FieldConfidence, VLMExtraction
from app.services import pipeline as P
from app.services.vlm import extractor


def test_pipeline_builds_item_name_from_vlm(monkeypatch, jpeg_bytes):
    fake = VLMExtraction(
        brand="Kivo",
        packaging_type="Sachet",
        weight_raw="70 g",
        fragrance_flavor="Tomato",
        category_type="Condiments",
        confidence=FieldConfidence(brand=0.9, packaging_type=0.8),
    )
    monkeypatch.setattr(extractor, "extract", lambda *a, **k: fake)
    res = P.run_pipeline(jpeg_bytes, use_enrichment=False)
    v = res["values"]
    assert v["brand"] == "Kivo"
    assert v["weight_value"] == 70.0 and v["weight_unit"] == "g"
    assert "KIVO" in v["item_name"] and "70G" in v["item_name"]
    assert res["source"]["brand"] == "vlm"
    assert res["vlm_error"] is None


def test_pipeline_survives_vlm_failure(monkeypatch, jpeg_bytes):
    def boom(*a, **k):
        raise RuntimeError("simulated 503")

    monkeypatch.setattr(extractor, "extract", boom)
    res = P.run_pipeline(jpeg_bytes, use_enrichment=False)
    # The pipeline must not crash; it records the error and returns a result.
    assert "simulated 503" in res["vlm_error"]
    assert res["values"].get("brand") is None


def test_vlm_schema_has_no_open_dicts():
    """Regression: Gemini structured output rejects open `additionalProperties`
    (this is the bug that made every extraction silently fail). The confidence
    field must be a fixed-property object, never an open dict."""
    schema = VLMExtraction.model_json_schema()
    fc = schema.get("$defs", {}).get("FieldConfidence", {})
    assert "properties" in fc and "brand" in fc["properties"]

    def has_open_additional(node) -> bool:
        if isinstance(node, dict):
            if isinstance(node.get("additionalProperties"), dict):
                return True
            return any(has_open_additional(v) for v in node.values())
        if isinstance(node, list):
            return any(has_open_additional(v) for v in node)
        return False

    assert not has_open_additional(schema)
