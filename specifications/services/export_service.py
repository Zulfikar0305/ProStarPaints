"""ExportService: produce export artifacts from saved drafts.

This service consumes the `PreviewService` context (which is built from a
`ManualSpecificationDraft`) and produces export artifacts (PDF). It does
not call the `SpecificationResolver` and does not rebuild the document
representation.
"""
from __future__ import annotations

import base64
import mimetypes
from typing import Any

from django.core.files.storage import default_storage
from django.template.loader import render_to_string


class ExportService:
    @staticmethod
    def _as_data_uri(value: Any) -> Any:
        """Convert media URLs into embedded data-URIs for PDF rendering.

        The PDF templates are rendered with `base_url=None`, so relative media
        URLs such as `/media/...` are not resolvable by WeasyPrint. We keep the
        underlying draft data untouched and only embed the binary data at render
        time, matching the regular quotation PDF behaviour.
        """
        if not isinstance(value, str):
            return value

        candidate = value.strip()
        if not candidate or candidate.startswith("data:") or "://" in candidate:
            return candidate

        candidate_path = candidate.split("?", 1)[0].split("#", 1)[0]
        storage_name = candidate_path

        if candidate_path.startswith("/media/"):
            storage_name = candidate_path[len("/media/"):]
        elif candidate_path.startswith("/"):
            storage_name = candidate_path.lstrip("/")

        raw = None
        try:
            with default_storage.open(storage_name, "rb") as fh:
                raw = fh.read()
        except Exception:
            try:
                import os
                if os.path.exists(candidate_path):
                    with open(candidate_path, "rb") as fh:
                        raw = fh.read()
                elif os.path.exists(storage_name):
                    with open(storage_name, "rb") as fh:
                        raw = fh.read()
                else:
                    return candidate
            except Exception:
                return candidate

        if raw is None:
            return candidate

        mime, _ = mimetypes.guess_type(storage_name) or mimetypes.guess_type(candidate_path) or (None, None)
        if not mime:
            mime = "image/png"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    def _normalise_pdf_images(self, sections: Any) -> Any:
        if not isinstance(sections, list):
            return sections

        for section in sections:
            if not isinstance(section, dict):
                continue
            image_items = section.get("images") or []
            if not isinstance(image_items, list):
                continue

            converted = []
            for item in image_items:
                if isinstance(item, dict):
                    image_url = item.get("url") or item.get("image") or item.get("src")
                    if not isinstance(image_url, str) or not image_url.strip():
                        continue
                    payload = dict(item)
                    payload["url"] = self._as_data_uri(image_url)
                    converted.append(payload)
                elif isinstance(item, str):
                    payload = self._as_data_uri(item)
                    if isinstance(payload, str) and payload.strip():
                        converted.append({"url": payload, "sort_order": len(converted)})
            if converted:
                section["images"] = converted
            elif not image_items:
                section["images"] = []
        return sections
    """High-level export helpers.

    Methods are deliberately small so new exporters (docx, email, html)
    can be added in future with minimal duplication.
    """

    def __init__(self):
        from .preview_service import PreviewService

        self.preview = PreviewService()

    def render_html_for_draft(self, draft, template_key: str):
        """Return rendered HTML for *draft* using the named PDF template.

        Does not perform PDF conversion; raises KeyError if template key
        is unknown, or ValueError if the draft lacks the required preview
        context.

        If the draft contains a resolver + draft overrides, prefer the merged
        preview context over any stale pre-rendered HTML snapshot. Otherwise the
        preview and PDF paths can diverge even though they are meant to render
        the same manual draft state.
        """
        data = getattr(draft, "data", {}) or {}
        if isinstance(data, dict):
            resolver = data.get("resolver")
            draft_overrides = data.get("draft_overrides")
            if not (isinstance(resolver, dict) and isinstance(draft_overrides, dict) and draft_overrides):
                rendered_map = data.get("rendered_html") if isinstance(data, dict) else None
                if rendered_map and isinstance(rendered_map, dict) and rendered_map.get(template_key):
                    return rendered_map.get(template_key)

        # Build the current merged context from draft state so Preview and PDF
        # consume the same report state. This is the authoritative render path
        # for draft-based exports.
        ctx = self.preview.preview_context_for_draft(draft)
        ctx["sections"] = self._normalise_pdf_images(ctx.get("sections") or [])

        # Ensure the context looks like a PDF-ready context (has sections)
        if not ctx or not ctx.get("sections"):
            raise ValueError("Draft does not contain PDF-ready context")

        # Validate template key and get template path
        from quotation.pdf_service import get_pdf_template

        template_cfg = get_pdf_template(template_key)
        tpl = template_cfg["template_path"]

        html = render_to_string(tpl, ctx)
        return html

    def export_pdf_from_draft(self, draft, template_key: str, generated_by, request=None):
        """Create a `QuotationPdfExport` for *draft* (PDF output).

        Returns the `QuotationPdfExport` instance. This function never calls
        the `SpecificationResolver` and uses only the preview context.
        """
        from django.core.files.base import ContentFile
        from quotation.models import QuotationPdfExport

        quotation = getattr(draft, "quotation", None)
        export = QuotationPdfExport(
            quotation=quotation,
            generated_by=generated_by,
            template_key=template_key,
            status=QuotationPdfExport.Status.GENERATED,
        )

        try:
            # Render HTML from draft
            html = self.render_html_for_draft(draft, template_key)

            # Convert via WeasyPrint
            import weasyprint

            pdf_bytes = weasyprint.HTML(string=html, base_url=None).write_pdf()

            filename = f"PSP_Quotation_{quotation.reference}_{template_key}.pdf"
            export.file.save(filename, ContentFile(pdf_bytes), save=False)
            export.status = QuotationPdfExport.Status.GENERATED
            export.save()

        except Exception as exc:
            # Capture error and hint if weasyprint native libs missing
            try:
                msg = str(exc)
                hint = ""
                if isinstance(exc, (ImportError, OSError)) or "libgobject" in msg or "WeasyPrint" in msg:
                    hint = (
                        "\n\nHint: WeasyPrint requires native libraries (Pango/Cairo). "
                        "On Windows install instructions are here: "
                        "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation"
                    )
            except Exception:
                hint = ""

            export.status = QuotationPdfExport.Status.FAILED
            export.error_message = (str(exc) + (hint or ""))[:1000]
            export.save()

        return export
