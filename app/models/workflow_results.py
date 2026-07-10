from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


WorkflowStatus = Literal["success", "failed", "partial"]
FailureType = Literal[
    "validation_error",
    "extraction_error",
    "network_error",
    "http_error",
    "reconciliation_error",
    "configuration_error",
    "pdf_error",
    "crawl_error",
    "unknown_error",
]


class FailureDetail(BaseModel):
    type: FailureType
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionResult(BaseModel):
    status: WorkflowStatus
    source_url: str
    raw_text: Optional[str] = None
    content_hash: Optional[str] = None
    failure: Optional[FailureDetail] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self):
        return self.status == "success"


class ExtractionResult(BaseModel):
    status: WorkflowStatus
    source_url: str
    rules: list[dict[str, Any]] = Field(default_factory=list)
    failure: Optional[FailureDetail] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self):
        return self.status in {"success", "partial"}


class ReconciliationResult(BaseModel):
    status: WorkflowStatus
    source_url: str
    changes_queued: int = 0
    skipped_count: int = 0
    failure: Optional[FailureDetail] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self):
        return self.status in {"success", "partial"}
