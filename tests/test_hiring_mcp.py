"""Unit tests for Hiring MCP Server tools and validation."""

import sys

import pytest
from mcp_servers.hiring.function_support import MockHiringSupport
from mcp_servers.hiring.tools import HiringTools
from mcp_servers.hiring.validators import (
    validate_candidate_id,
    validate_candidate_status,
    validate_date,
    validate_job_status,
)


@pytest.fixture
def tools():
    return HiringTools(MockHiringSupport())


def test_validators():
    # Date validation
    assert validate_date("2026-08-20")[0] is True
    assert validate_date(None)[0] is True
    assert validate_date("20-08-2026")[0] is False
    assert validate_date("invalid-date")[0] is False

    # Candidate status validation
    assert validate_candidate_status("pending_interview")[0] is True
    assert validate_candidate_status("interviewing")[0] is True
    assert validate_candidate_status("invalid_status")[0] is False

    # Job status validation
    assert validate_job_status("open")[0] is True
    assert validate_job_status("closed")[0] is True
    assert validate_job_status("unknown_status")[0] is False

    # Candidate ID validation
    assert validate_candidate_id("UV001")[0] is True
    assert validate_candidate_id("")[0] is False
    assert validate_candidate_id(None)[0] is False


def test_search_candidates(tools):
    # Search all
    res = tools.search_candidates()
    assert res["success"] is True
    assert res["metadata"]["source"] == "hiring"
    assert len(res["data"]["candidates"]) > 0

    # Search by keyword
    res = tools.search_candidates(keyword="Backend")
    assert res["success"] is True
    for c in res["data"]["candidates"]:
        assert "Backend" in c["position"] or any("Backend" in sk for sk in c.get("skills", []))

    # Search by status
    res = tools.search_candidates(status="pending_interview")
    assert res["success"] is True
    for c in res["data"]["candidates"]:
        assert c["status"] == "pending_interview"

    # Search with invalid status
    res = tools.search_candidates(status="wrong_status")
    assert res["success"] is False
    assert res["error"] is not None


def test_get_candidate_detail(tools):
    # Valid candidate
    res = tools.get_candidate_detail("UV001")
    assert res["success"] is True
    assert res["data"]["id"] == "UV001"
    assert res["data"]["name"] == "Nguyễn Văn An"

    # Non-existent candidate
    res = tools.get_candidate_detail("UV999")
    assert res["success"] is False
    assert "Không tìm thấy" in res["error"]

    # Missing ID
    res = tools.get_candidate_detail("")
    assert res["success"] is False
    assert "Thiếu mã ứng viên" in res["error"]


def test_list_job_openings(tools):
    # List open positions
    res = tools.list_job_openings(status="open")
    assert res["success"] is True
    assert res["data"]["total_found"] >= 4

    # List by department
    res = tools.list_job_openings(department="Công nghệ thông tin")
    assert res["success"] is True
    assert any("Công nghệ thông tin" in j["department"] for j in res["data"]["job_openings"])

    # Invalid status
    res = tools.list_job_openings(status="invalid_status")
    assert res["success"] is False


def test_get_interview_schedule(tools):
    # All schedules
    res = tools.get_interview_schedule()
    assert res["success"] is True
    assert len(res["data"]["schedules"]) > 0

    # By candidate ID
    res = tools.get_interview_schedule(candidate_id="UV001")
    assert res["success"] is True
    for s in res["data"]["schedules"]:
        assert s["candidate_id"] == "UV001"

    # Date range validation
    res = tools.get_interview_schedule(from_date="invalid")
    assert res["success"] is False


def test_get_recruitment_summary(tools):
    res = tools.get_recruitment_summary()
    assert res["success"] is True
    data = res["data"]
    assert data["total_openings"] > 0
    assert data["total_candidates"] > 0
    assert data["pending_interview_count"] >= 1
    assert "Khối Công nghệ thông tin" in data["by_department"]


def test_server_supports_streamable_http(monkeypatch):
    from mcp_servers.hiring import server

    calls = []

    class FakeServer:
        async def run_streamable_http_async(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(server, "mcp_server", FakeServer())
    monkeypatch.setattr(
        sys,
        "argv",
        ["server.py", "--transport", "streamable-http", "--host", "127.0.0.1", "--port", "9001"],
    )

    server.main()

    assert calls == [{"host": "127.0.0.1", "port": 9001}]
