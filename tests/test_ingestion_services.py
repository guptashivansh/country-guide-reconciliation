"""Tests for ingestion services."""
import pytest
from unittest.mock import MagicMock
from app.ingestion.ingestion_job_service import IngestionJobService


class TestIngestionJobService:
    def setup_method(self):
        self.mock_repo = MagicMock()
        self.service = IngestionJobService(self.mock_repo)

    def test_create_job(self):
        self.mock_repo.create_job.return_value = 42
        result = self.service.create_job("https://example.com", country="India")
        self.mock_repo.create_job.assert_called_once_with("https://example.com", country="India")
        assert result == 42

    def test_get_job(self):
        self.mock_repo.get_job.return_value = {"id": 1, "source_url": "https://example.com"}
        result = self.service.get_job(1)
        self.mock_repo.get_job.assert_called_once_with(1)
        assert result == {"id": 1, "source_url": "https://example.com"}

    def test_mark_fetched(self):
        self.service.mark_fetched(1)
        self.mock_repo.transition_job.assert_called_once_with(1, "fetched")

    def test_mark_normalized(self):
        self.service.mark_normalized(1, source_snapshot_id=99)
        self.mock_repo.transition_job.assert_called_once_with(
            1, "normalized", source_snapshot_id=99,
        )

    def test_mark_extracted(self):
        self.service.mark_extracted(1)
        self.mock_repo.transition_job.assert_called_once_with(1, "extracted")

    def test_mark_reconciled(self):
        self.service.mark_reconciled(1)
        self.mock_repo.transition_job.assert_called_once_with(1, "reconciled")

    def test_mark_failed(self):
        self.service.mark_failed(1, "timeout")
        self.mock_repo.transition_job.assert_called_once_with(
            1, "failed", failure_reason="timeout",
        )

    def test_list_recent_jobs(self):
        self.mock_repo.list_recent_jobs.return_value = [{"id": 1}]
        result = self.service.list_recent_jobs(limit=10)
        assert result == [{"id": 1}]
        self.mock_repo.list_recent_jobs.assert_called_once_with(limit=10)

    def test_list_recent_jobs_default_limit(self):
        self.mock_repo.list_recent_jobs.return_value = []
        self.service.list_recent_jobs()
        self.mock_repo.list_recent_jobs.assert_called_once_with(limit=25)

    def test_retry_job_not_found(self):
        self.mock_repo.get_job.return_value = None
        result = self.service.retry_job(999)
        assert result is None

    def test_retry_job_success(self):
        self.mock_repo.get_job.return_value = {
            "source_url": "https://example.com",
            "country": "India",
        }
        self.mock_repo.create_job.return_value = 43
        result = self.service.retry_job(1)
        self.mock_repo.create_job.assert_called_once_with(
            "https://example.com", country="India",
        )
        assert result == {
            "job_id": 43,
            "source_url": "https://example.com",
            "country": "India",
            "resume_from": "queued",
            "existing_snapshot_id": None,
        }
