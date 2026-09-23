import json
import os
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .mock_data import MOCK_CANDIDATES, MOCK_INTERVIEWS, MOCK_JOB_OPENINGS


class HiringFunctionSupport(ABC):
    """Abstract interface for Hiring module Function Support (FME)."""

    @abstractmethod
    def search_candidates(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_candidate_detail(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_job_openings(
        self,
        status: Optional[str] = None,
        department: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_interview_schedule(
        self,
        candidate_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_recruitment_summary(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class MockHiringSupport(HiringFunctionSupport):
    """In-memory Mock implementation of Hiring Function Support."""

    def __init__(
        self,
        candidates: Optional[List[Dict[str, Any]]] = None,
        jobs: Optional[List[Dict[str, Any]]] = None,
        interviews: Optional[List[Dict[str, Any]]] = None,
    ):
        self.candidates = candidates or list(MOCK_CANDIDATES)
        self.jobs = jobs or list(MOCK_JOB_OPENINGS)
        self.interviews = interviews or list(MOCK_INTERVIEWS)

    def search_candidates(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        results = self.candidates

        if status:
            s_lower = status.strip().lower()
            results = [c for c in results if c.get("status", "").lower() == s_lower]

        if job_id:
            j_lower = job_id.strip().lower()
            results = [c for c in results if c.get("job_id", "").lower() == j_lower]

        if keyword:
            kw = keyword.strip().lower()
            filtered = []
            for c in results:
                name_match = kw in c.get("name", "").lower()
                email_match = kw in c.get("email", "").lower()
                position_match = kw in c.get("position", "").lower()
                skills_match = any(kw in sk.lower() for sk in c.get("skills", []))
                if name_match or email_match or position_match or skills_match:
                    filtered.append(c)
            results = filtered

        return results[:limit]

    def get_candidate_detail(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        cid = candidate_id.strip().lower()
        for c in self.candidates:
            if c.get("id", "").lower() == cid:
                return dict(c)
        return None

    def list_job_openings(
        self,
        status: Optional[str] = None,
        department: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        results = self.jobs

        if status:
            s_lower = status.strip().lower()
            results = [j for j in results if j.get("status", "").lower() == s_lower]

        if department:
            d_lower = department.strip().lower()
            results = [j for j in results if d_lower in j.get("department", "").lower()]

        return results[:limit]

    def get_interview_schedule(
        self,
        candidate_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        results = self.interviews

        if candidate_id:
            cid = candidate_id.strip().lower()
            results = [i for i in results if i.get("candidate_id", "").lower() == cid]

        if from_date:
            results = [i for i in results if i.get("interview_date", "") >= from_date]

        if to_date:
            results = [i for i in results if i.get("interview_date", "") <= to_date]

        return results

    def get_recruitment_summary(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        candidates = self.candidates
        if from_date:
            candidates = [c for c in candidates if c.get("applied_date", "") >= from_date]
        if to_date:
            candidates = [c for c in candidates if c.get("applied_date", "") <= to_date]

        by_status: Dict[str, int] = {}
        for c in candidates:
            st = c.get("status", "unknown")
            by_status[st] = by_status.get(st, 0) + 1

        by_dept: Dict[str, int] = {}
        for j in self.jobs:
            dept = j.get("department", "unknown")
            by_dept[dept] = by_dept.get(dept, 0) + j.get("open_positions", 0)

        return {
            "total_openings": sum(j.get("open_positions", 0) for j in self.jobs if j.get("status") == "open"),
            "total_candidates": len(candidates),
            "pending_interview_count": by_status.get("pending_interview", 0),
            "interviewing_count": by_status.get("interviewing", 0),
            "offered_count": by_status.get("offered", 0),
            "rejected_count": by_status.get("rejected", 0),
            "hired_count": by_status.get("hired", 0),
            "by_department": by_dept,
            "by_status": by_status,
        }


class RealHiringSupport(HiringFunctionSupport):
    """Production Function Support connecting to FME backend / REST API."""

    def __init__(
        self,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 10,
    ):
        self.api_base_url = (api_base_url or os.getenv("HIRING_API_BASE_URL", "http://127.0.0.1:8000/api/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("HIRING_API_KEY", "")
        self.timeout = timeout

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        clean_endpoint = endpoint.lstrip("/")
        url = f"{self.api_base_url}/{clean_endpoint}"
        if params:
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if filtered_params:
                query_str = urllib.parse.urlencode(filtered_params)
                url = f"{url}?{query_str}"

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "Hiring-MCP-Server/1.0")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP Error {e.code} khi gọi API {url}: {error_body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Không thể kết nối tới API server tại {url}: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Lỗi khi gọi API {url}: {str(e)}")

    def search_candidates(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        result = self._request("candidates", {"keyword": keyword, "status": status, "job_id": job_id, "limit": limit})
        if isinstance(result, dict):
            return result.get("items", result.get("candidates", result.get("data", [])))
        return result if isinstance(result, list) else []

    def get_candidate_detail(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        try:
            result = self._request(f"candidates/{candidate_id}")
            if isinstance(result, dict) and "data" in result and isinstance(result["data"], dict):
                return result["data"]
            return result if isinstance(result, dict) else None
        except Exception:
            return None

    def list_job_openings(
        self,
        status: Optional[str] = None,
        department: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        result = self._request("jobs", {"status": status, "department": department, "limit": limit})
        if isinstance(result, dict):
            return result.get("items", result.get("jobs", result.get("data", [])))
        return result if isinstance(result, list) else []

    def get_interview_schedule(
        self,
        candidate_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = self._request("interviews", {"candidate_id": candidate_id, "from_date": from_date, "to_date": to_date})
        if isinstance(result, dict):
            return result.get("items", result.get("schedules", result.get("data", [])))
        return result if isinstance(result, list) else []

    def get_recruitment_summary(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = self._request("recruitment/summary", {"from_date": from_date, "to_date": to_date})
        if isinstance(result, dict) and "data" in result and isinstance(result["data"], dict):
            return result["data"]
        return result if isinstance(result, dict) else {}

