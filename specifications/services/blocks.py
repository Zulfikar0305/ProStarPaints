from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import hashlib


@dataclass
class SpecificationBlock:
    """Lightweight internal representation for a specification block.

    This is intentionally a pure in-memory dataclass; it is NOT persisted
    to the database. Consumers should use `to_dict()` to produce a
    serialisable payload that downstream components (builder, preview,
    export) can consume.
    """

    block_type: str
    title: Optional[str] = None
    content: Optional[str] = None
    pk: Optional[int] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    visible: bool = True
    editable: bool = False
    order: Optional[float] = None
    resolved_id: Optional[str] = None

    def compute_resolved_id(self, section_resolved_id: Optional[str] = None) -> str:
        """Compute a deterministic, stable ID for this block.

        The ID is derived from the parent section's `resolved_id`, the
        block type and a stable identifier (prefer `pk`). Truncated to
        16 hex chars for brevity while still being practically unique.
        """
        base = f"{section_resolved_id or ''}::{self.block_type}::"
        identifier = str(self.pk) if self.pk is not None else (self.title or self.content or "")
        self.resolved_id = hashlib.sha1((base + identifier).encode("utf-8")).hexdigest()[:16]
        return self.resolved_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolved_id": self.resolved_id,
            "block_type": self.block_type,
            "title": self.title,
            "content": self.content,
            "pk": self.pk,
            "source": self.source,
            "metadata": self.metadata,
            "visible": self.visible,
            "editable": self.editable,
            "order": self.order,
        }
