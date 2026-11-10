import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services import labeling_runtime
from services.recording_evidence import RecordingEvidenceError, seal_recording_evidence


def metric_catalog():
    category_by_prefix = {
        "voice": "voice",
        "vision": "vision",
        "content": "content",
        "empathy": "empathy",
        "gov": "governance",
    }
    units = {
        "voice.wpm": "WPM",
        "voice.filler_density": "%",
        "voice.prolonged_pause": "pausas",
        "voice.hesitation_pause": "pausas",
        "voice.phonation_ratio": "%",
        "voice.asr_confidence": "%",
        "vision.eye_contact": "%",
        "vision.posture": "%",
        "vision.sway_tolerance": "std",
        "content.red_line_cap": "pts",
        "empathy.victim_recog": "nivel",
        "gov.confidence_min": "%",
        "gov.borderline_delta": "pts",
        "gov.disparity_delta": "pts",
        "gov.random_sample": "%",
        "gov.agreement_target": "ratio",
    }
    thresholds = {
        "gov.borderline_delta": {"halfWidth": 2},
        "gov.disparity_delta": {"auditAt": 50},
    }
    return [
        {
            "metricKey": key,
            "categoryKey": category_by_prefix[key.split(".")[0]],
            "label": key,
            "unit": units[key],
            "publishedThresholds": thresholds.get(key, {}),
        }
        for key in sorted(labeling_runtime.EXPECTED_METRIC_KEYS)
    ]


def exact_material():
    report = {
        "clientId": "client-id",
        "sessionId": "session-id",
        "reportId": "report-id",
        "analysisJobId": "job-id",
        "rubricVersionId": "rubric-id",
        "overallScore": 82,
    }
    areas = [
        {"areaId": "a1", "areaKey": "expression", "aiValue": 80},
        {"areaId": "a2", "areaKey": "voice", "aiValue": 82},
        {"areaId": "a3", "areaKey": "coherence", "aiValue": 84},
        {"areaId": "a4", "areaKey": "empathy", "aiValue": 81},
    ]
    pipelines = {
        "voice": {
            "wpm_global": 141.2,
            "densidad_muletillas_pct": 1.2,
            "pausas_prolongadas": 1,
            "pausas_vacilacion": 2,
            "ratio_fonacion": 0.68,
            "words": [{"word": "hola", "confidence": 0.91}],
        },
        "vision": {
            "summary": {
                "eye_contact_pct": 76,
                "shoulder_stability_score": 83,
                "body_sway_std": 0.01,
            }
        },
        "content_judge": {"puntaje_global_100": 84},
        "fusion": {"reportId": "report-id"},
    }
    evidence = {
        "sealedPath": "labeling-evidence/session/job/hash.webm",
        "versionId": None,
        "sha256": "a" * 64,
        "etag": '"etag"',
        "contentType": "video/webm",
        "durationSeconds": 90.5,
    }
    return report, areas, pipelines, evidence


def test_snapshot_uses_original_sources_and_explicit_conversion():
    report, areas, pipelines, evidence = exact_material()
    result = labeling_runtime.build_labeling_snapshot(
        report=report,
        areas=areas,
        pipeline_results=pipelines,
        metric_catalog=metric_catalog(),
        evidence=evidence,
    )

    metrics = {item["metricKey"]: item for item in result["snapshot"]["metrics"]}
    assert result["sourceStatus"] == "complete"
    assert result["queueReason"] == "routine"
    assert metrics["voice.phonation_ratio"]["aiValue"] == 68
    assert metrics["voice.asr_confidence"]["aiValue"] == 91
    assert metrics["content.red_line_cap"]["availability"] == "not_emitted"
    assert metrics["empathy.victim_recog"]["editable"] is False
    assert result["snapshot"]["recording"]["sealedPath"] == evidence["sealedPath"]


def test_missing_original_metric_is_partial_never_defaulted():
    report, areas, pipelines, evidence = exact_material()
    del pipelines["voice"]["words"]
    result = labeling_runtime.build_labeling_snapshot(
        report=report,
        areas=areas,
        pipeline_results=pipelines,
        metric_catalog=metric_catalog(),
        evidence=evidence,
    )
    metric = next(
        item
        for item in result["snapshot"]["metrics"]
        if item["metricKey"] == "voice.asr_confidence"
    )
    assert result["sourceStatus"] == "partial"
    assert metric["aiValue"] is None
    assert metric["availability"] == "unknown"
    assert metric["editable"] is False


def test_invalid_or_mutable_evidence_is_rejected():
    report, areas, pipelines, evidence = exact_material()
    evidence["sealedPath"] = "recordings/session.webm"
    with pytest.raises(labeling_runtime.LabelingRuntimeError):
        labeling_runtime.build_labeling_snapshot(
            report=report,
            areas=areas,
            pipeline_results=pipelines,
            metric_catalog=metric_catalog(),
            evidence=evidence,
        )


class ResourceExistsError(Exception):
    pass


class FakeProperties:
    def __init__(self, content, metadata, content_type="video/webm"):
        self.size = len(content)
        self.metadata = metadata
        self.etag = '"etag-' + metadata["sha256"][:8] + '"'
        self.version_id = None
        self.content_type = content_type


class FakeBlobClient:
    def __init__(self, service, path):
        self.service = service
        self.path = path

    def upload_blob(self, stream, *, overwrite, metadata, **_kwargs):
        assert overwrite is False
        if self.path in self.service.items:
            raise ResourceExistsError()
        self.service.items[self.path] = (stream.read(), dict(metadata))

    def get_blob_properties(self):
        content, metadata = self.service.items[self.path]
        return FakeProperties(content, metadata)


class FakeBlobService:
    def __init__(self):
        self.items = {}

    def get_blob_client(self, *, container, blob):
        assert container == "recordings"
        return FakeBlobClient(self, blob)


def test_sealed_copy_is_idempotent_and_survives_source_overwrite(tmp_path):
    source = tmp_path / "source.webm"
    source.write_bytes(b"original-recording")
    service = FakeBlobService()
    kwargs = {
        "storage_connection_string": None,
        "container_name": "recordings",
        "source_blob_path": "recordings/session.webm",
        "local_path": source,
        "session_id": "10000000-0000-4000-8000-000000000001",
        "job_id": "20000000-0000-4000-8000-000000000001",
        "blob_service": service,
    }
    first = seal_recording_evidence(**kwargs)
    repeated = seal_recording_evidence(**kwargs)
    original_content = service.items[first["sealedPath"]][0]

    source.write_bytes(b"overwritten-source")
    second = seal_recording_evidence(**kwargs)

    assert repeated["sealedPath"] == first["sealedPath"]
    assert second["sealedPath"] != first["sealedPath"]
    assert service.items[first["sealedPath"]][0] == original_content


def test_existing_sealed_blob_with_wrong_metadata_fails(tmp_path):
    source = tmp_path / "source.webm"
    source.write_bytes(b"recording")
    service = FakeBlobService()
    result = seal_recording_evidence(
        storage_connection_string=None,
        container_name="recordings",
        source_blob_path="recordings/session.webm",
        local_path=source,
        session_id="10000000-0000-4000-8000-000000000001",
        job_id="20000000-0000-4000-8000-000000000001",
        blob_service=service,
    )
    content, metadata = service.items[result["sealedPath"]]
    metadata["sha256"] = "0" * 64
    with pytest.raises(RecordingEvidenceError):
        seal_recording_evidence(
            storage_connection_string=None,
            container_name="recordings",
            source_blob_path="recordings/session.webm",
            local_path=source,
            session_id="10000000-0000-4000-8000-000000000001",
            job_id="20000000-0000-4000-8000-000000000001",
            blob_service=service,
        )


class MaterialCursor:
    def __init__(self):
        self.case_id = None
        self.rows = []
        self.row = None
        self.inserts = 0

    def execute(self, statement, *params):
        normalized = " ".join(statement.split()).lower()
        if "from dbo.labeling_case" in normalized and "with (updlock,holdlock)" in normalized:
            self.row = (self.case_id,) if self.case_id else None
        elif "from dbo.report as r" in normalized:
            self.row = (
                "report-id",
                "session-id",
                "job-id",
                "rubric-id",
                82,
                "client-id",
                "2026-10-30T12:00:00Z",
            )
        elif "from dbo.area_score" in normalized:
            self.rows = [
                (area["areaId"], area["areaKey"], area["aiValue"])
                for area in exact_material()[1]
            ]
        elif "from dbo.analysis_pipeline_result" in normalized:
            self.rows = [
                (name, json.dumps(value))
                for name, value in sorted(exact_material()[2].items())
            ]
            for index, (name, raw) in enumerate(self.rows):
                if name == "fusion":
                    value = json.loads(raw)
                    value["recordingEvidence"] = exact_material()[3]
                    self.rows[index] = (name, json.dumps(value))
        elif "from dbo.rubric_metric_definition" in normalized:
            self.rows = [
                (
                    item["metricKey"],
                    item["categoryKey"],
                    item["label"],
                    item["unit"],
                    json.dumps(item["publishedThresholds"]),
                    index,
                )
                for index, item in enumerate(metric_catalog())
            ]
        elif "insert into dbo.labeling_case" in normalized:
            self.inserts += 1
            self.case_id = params[0]
        else:
            raise AssertionError(statement)
        return self

    def fetchone(self):
        row, self.row = self.row, None
        return row

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


def test_ensure_case_is_idempotent_by_report_id():
    cursor = MaterialCursor()

    first = labeling_runtime.ensure_labeling_case_for_report(cursor, "report-id")
    second = labeling_runtime.ensure_labeling_case_for_report(cursor, "report-id")

    assert first["created"] is True
    assert first["sourceStatus"] == "complete"
    assert second == {"caseId": first["caseId"], "created": False}
    assert cursor.inserts == 1


class ListingCursor:
    def __init__(self):
        self.statement = ""
        self.rows = []

    def execute(self, statement, *_params):
        self.statement = statement
        self.rows = [("old-report",), ("current-report",)]
        return self

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


def test_reconciler_includes_superseded_completed_reports(monkeypatch):
    cursor = ListingCursor()
    ensure = MagicMock(return_value={"caseId": "case-id", "created": True})
    monkeypatch.setattr(labeling_runtime, "ensure_labeling_case_for_report", ensure)

    summary = labeling_runtime.reconcile_completed_reports(
        cursor, limit=10, materialize=True
    )

    assert "r.is_current=1" not in cursor.statement
    assert summary == {"scanned": 2, "eligible": 2, "created": 2, "errors": []}
    assert [call.args[1] for call in ensure.call_args_list] == [
        "old-report",
        "current-report",
    ]


def test_worker_entrypoints_have_one_canonical_pipeline():
    root = Path(__file__).resolve().parents[1]
    service_bus = (root / "worker.py").read_text(encoding="utf-8")
    function_app = (root / "function_app.py").read_text(encoding="utf-8")
    assert "return process_session_pipeline(" in service_bus
    assert "function_app heredado está deshabilitado" in function_app
    assert "El pipeline Service Bus heredado está deshabilitado" in service_bus
