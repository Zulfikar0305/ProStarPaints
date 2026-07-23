**Version 2 — Specification Engine: Architecture & Developer Handover**

---

**1. Executive Summary**

- **Purpose**: Version 2 introduces a manual editing and publishing pipeline for product specifications. It lets users create and persist manual specification drafts derived from the `SpecificationResolver` output, preview the exact stored content, and export final specification artifacts (PDFs) without re-running or duplicating resolver logic.
- **What changed**: Implemented three major capabilities:
  - **Manual Specification Builder**: Persistent, editable `ManualSpecificationDraft` objects that store resolver payloads and optional pre-rendered HTML fragments.
  - **Specification Preview Engine**: Read-only preview pages that display exactly what is stored in a draft (prefer `rendered_html` if present), guaranteeing preview==export.
  - **Export Engine**: `ExportService` that consumes the draft/preview output and produces PDF exports (WeasyPrint). It never calls the `SpecificationResolver`.
- **Design philosophy**: Keep the resolver as the single authoritative generator of specification content. Do not duplicate resolver logic. Persist a canonical, JSON-serializable draft representation, and — when possible — pre-render the HTML used for export so preview and export are byte-identical. Put business logic in services; keep views thin; make exporters pluggable.

---

**2. Complete System Architecture**

- **High-level components**:
  - **Quotation**: The domain object representing the job/quotation to be specified.
  - **SpecificationResolver**: The algorithmic generator of a recommended specification based on quotation data and business rules.
  - **ManualSpecificationDraft (`ManualSpecificationDraft`)**: Persistent draft record that stores the resolver payload and editable payloads, plus optional `rendered_html`.
  - **PreviewService**: Produces a preview context or returns pre-rendered HTML for a draft.
  - **ExportService**: Produces export artifacts (PDF) from a draft (never re-runs resolver).
  - **PDF Service (`quotation.pdf_service`)**: Provides helpers to build PDF template contexts and to render templates; the core `build_pdf_context(..., use_resolver=True)` now supports `use_resolver=False`.
  - **Spec Report / Template helpers (`spec_report.generate_spec_for_sections`)**: Utilities to transform section-level data into the shape expected by PDF templates.
  - **Templates**: `templates/specifications/*` and `templates/quotation/pdf/*` including the pre-render embedding template.
  - **Validation scripts**: `scripts/validate_*.py` for resolver, builder, preview, export flows.

- **Major models (overview)**:
  - `ManualSpecificationDraft` — stores persistent draft JSON and metadata.
  - `QuotationPdfExport` — metadata and stored PDF for generated exports (audit trail).

---

**3. Data Flow**

A complete, step-by-step flow from Quotation to PDF:

- **Input: Quotation**
  - The user selects or opens a `Quotation` (existing DB model). This object contains all the data the resolver uses (products, selections, measurements, options).

- **Step 1 — SpecificationResolver**
  - `SpecificationResolver.resolve(quotation)` is invoked when creating a new draft or when explicitly requesting a fresh recommended specification.
  - Output: a pure-JSON serializable `resolver_payload` with keys such as `sections`, `template`, `metadata`, where each `section` includes `section_key`, `clauses`, `product_descriptions`, and optional `recommendation` text.
  - Constraint: `SpecificationResolver` is authoritative. Its output may be edited in the draft, but templates should rely on the draft's stored data for previews/exports.

- **Step 2 — ManualSpecificationDraft creation (Builder)**
  - `ManualSpecificationBuilderService.create_draft_from_resolver(quotation, ...)` consumes the resolver payload and builds a `ManualSpecificationDraft` record.
  - Draft `data` shape (canonical):
    - `resolver`: resolver payload (JSON-serializable dict)
    - `rendered_html`: optional map { template_key: "<pre-rendered HTML string>" }
    - `other_metadata`: optional fields for UI/editor state
  - Important: The draft must contain only JSON-serializable values (no model instances).
  - During draft creation, the builder attempts to pre-render selected templates into `rendered_html[template_key]`. It does this by producing a PDF-ready context (via `build_pdf_context(..., use_resolver=False)` or via `generate_spec_for_sections`) and rendering the template server-side to an HTML string. If pre-rendering fails, the draft will still contain `resolver` data and the preview/export will fall back to generating HTML from the draft data.

- **Step 3 — PreviewService**
  - `PreviewService.preview_context_for_draft(draft)` is the single source of preview data.
  - If `draft.data.rendered_html[template_key]` exists: return a small context that embeds that HTML verbatim. The preview page loads precisely the same HTML the export will use.
  - Otherwise: build a PDF-ready context from the `resolver` payload (a minimal, JSON-only representation compatible with templates) and render templates for display.
  - Key invariant: Preview is read-only and must display exactly the stored draft representation.

- **Step 4 — ExportService**
  - `ExportService.render_html_for_draft(draft, template_key)` returns HTML for the chosen template. It prefers `rendered_html` from the draft; otherwise it falls back to rendering the template from the preview context.
  - `ExportService.export_pdf_from_draft(draft, template_key, generated_by, request=None)`:
    - Calls `render_html_for_draft` to obtain HTML.
    - Converts HTML → PDF using WeasyPrint (or a configured exporter adapter) and stores the result as a `QuotationPdfExport` record (metadata: filename, template_key, generated_by, size, storage path/blob).
    - Does NOT call `SpecificationResolver` or attempt to rebuild quotation-level context beyond what's in the draft or preview.

- **Output: PDF**
  - The final artifact (PDF bytes) is stored and referenced by `QuotationPdfExport`. The preview page containing `rendered_html` should byte-for-byte match the exported PDF's rendered HTML (modulo WeasyPrint PDF rendering differences), ensuring WYSIWYG parity.

---

**4. Services**

For each service, responsibilities, public methods, and interactions are documented below.

- **`SpecificationResolver`**
  - **Responsibility**: Given a `Quotation`, compute recommended specification sections, clauses, and product descriptions according to business rules and configuration.
  - **Public methods**:
    - `resolve(quotation) -> dict` — returns a JSON-serializable payload: { "sections": [...], "template": { ... }, "metadata": { ... } }
  - **Interactions**: Called by the Builder on demand. NOT called by Preview or Export once a draft exists.

- **`ManualSpecificationBuilderService`** (file: specifications/services/builder_service.py)
  - **Responsibility**: Create and update `ManualSpecificationDraft` records; prepare pre-rendered HTML; sanitize and store only JSON-serializable data.
  - **Public methods**:
    - `prepare_spec(quotation) -> dict` — helper that calls the `SpecificationResolver` and returns the resolver payload (used by `create_draft_from_resolver`).
    - `create_draft_from_resolver(quotation, created_by=None, title='', template_key='detailed_spec') -> ManualSpecificationDraft` — creates and persists a new draft using the resolver payload; attempts to pre-render template HTML into `rendered_html`.
    - `save_draft(draft, data) -> ManualSpecificationDraft` — writes edited draft JSON back to DB, validating JSON-serializability.
    - `latest_draft_for_user(quotation, user) -> ManualSpecificationDraft` — convenience helper.
  - **Interactions**: Calls `SpecificationResolver` and `PDF / template rendering` to pre-render HTML; updates `ManualSpecificationDraft` model.

- **`PreviewService`** (file: specifications/services/preview_service.py)
  - **Responsibility**: Produce a preview context for a `ManualSpecificationDraft` or a direct pre-render embed if available.
  - **Public methods**:
    - `preview_context_for_draft(draft, template_key='detailed_spec') -> dict` — returns a context that views/templates consume. If `rendered_html` exists, returns minimal wrapper with that string; otherwise returns a full `pdf_ctx` built from draft `resolver` payload.
  - **Interactions**: May call `quotation.pdf_service.build_pdf_context(..., use_resolver=False)` or internal `generate_spec_for_sections` helpers to convert draft JSON into the shape templates expect.

- **`ExportService`** (file: specifications/services/export_service.py)
  - **Responsibility**: Export artifacts (currently PDF) from a `ManualSpecificationDraft` without re-running the resolver and without rebuilding document context beyond what the draft already contains.
  - **Public methods**:
    - `render_html_for_draft(draft, template_key='detailed_spec') -> str` — prefer `draft.data.rendered_html[template_key]` else render via `PreviewService`.
    - `export_pdf_from_draft(draft, template_key='detailed_spec', generated_by=None, request=None) -> QuotationPdfExport` — generate PDF bytes (WeasyPrint) and create a `QuotationPdfExport` record.
  - **Interactions**: Depends on `PreviewService` to generate an HTML context when `rendered_html` is absent. Uses `quotation.pdf.service` HTML→PDF conversion.

- **`quotation.pdf_service`** (file: quotation/pdf_service.py)
  - **Responsibility**: Central, reusable helpers to build the `pdf_ctx` for templates and invoke template rendering.
  - **Public methods**:
    - `build_pdf_context(quotation, request=None, use_resolver: bool = True) -> dict` — builds a full context for PDF templates. When `use_resolver=False`, it will not invoke the `SpecificationResolver` (used during draft pre-rendering and preview/export fallback).
    - Template rendering helpers used by Builder/Preview/Export.
  - **Interactions**: Used by Builder for pre-rendering (with `use_resolver=False`), and by other services when needed.

- **`spec_report` utilities**
  - **Responsibility**: Produce a template-friendly representation of section data (flattening, enrichments), used by `pdf_service` and builder pre-rendering.
  - **Public methods**:
    - `generate_spec_for_sections(section_data) -> list` — converts raw `resolver` section payloads into the shape templates require.

---

**5. Database Models**

- **`ManualSpecificationDraft` (specifications/models.py)**
  - **Purpose**: Canonical persisted representation of a user-edited specification.
  - **Key fields**:
    - `quotation` (FK): reference to the `Quotation` this draft belongs to.
    - `title` (string): human-readable title for the draft.
    - `data` (JSONField): canonical JSON payload, containing at minimum the `resolver` payload and optional `rendered_html` map. Example shape:

      {
        "resolver": { "sections": [ ... ], "template": { ... } },
        "rendered_html": { "detailed_spec": "<html>...</html>" },
        "ui_state": { ... }
      }

    - `status` (enum): workflow state (draft, published, archived).
    - `is_active` (bool): convenience flag.
    - standard audit fields: `created_at`, `updated_at`, `created_by`, `updated_by`.
  - **Important constraints**:
    - The `data` JSON must be JSON-serializable only (no ORM model instances). This was a major source of prior bugs.

- **`QuotationPdfExport` (where present)**
  - **Purpose**: Store export artifacts and metadata for audit and download.
  - **Typical fields**:
    - `quotation` (FK), `draft` (FK optional), `generated_by` (FK user), `template_key` (string), `filename`, `storage_path` or `file` (FileField), `created_at`, `size_bytes`, `status`.
  - **Behavior**: Write once; used by UI to list and download generated PDFs.

---

**6. Document Lifecycle**

- **Create**: User either requests a fresh recommended spec (resolver run) or copies an existing `ManualSpecificationDraft` to start editing.
- **Edit**: The UI editor posts the edited JSON back to `ManualSpecificationDraft.data` (via `ManualBuilderService.save_draft`). The server validates the JSON is serializable and within size limits.
- **Preview**: Server renders the draft via `PreviewService`. If `rendered_html` exists for the chosen template, the preview embeds it directly; otherwise preview is rendered from draft `data`.
- **Publish / Export**: User triggers export (or the export is scheduled). `ExportService` loads the draft, calls `render_html_for_draft`, then converts HTML→PDF and stores a `QuotationPdfExport`. Export never re-runs `SpecificationResolver` or mutates the draft by re-applying resolver logic.
- **Audit**: Exports are stored with metadata and can be downloaded; drafts are versioned or archived per team policy.

---

**7. Extension Points**

Where to extend the system and suggested approaches:

- **AI-assisted editing**
  - Add a service `specifications.services.ai_assistant` that consumes a `ManualSpecificationDraft` and returns suggested edits (diffs or full JSON). Keep the assistant output as diffs and always show user approval before writing to `data`.

- **Pluggable Exporters (DOCX, HTML, other formats)**
  - Introduce an `Exporter` interface with methods `render_html(draft, template_key)` and `export(draft, generated_by)`.
  - Move PDF-specific logic into `exporters/pdf_exporter.py` implementing `BaseExporter`. Add `exporters/docx_exporter.py` for `.docx` outputs.
  - Replace `ExportService.export_pdf_from_draft` with a registry `ExportService.export(draft, exporter_key, template_key)`.

- **Client Portal integration**
  - Provide an API endpoint to list `ManualSpecificationDraft` and `QuotationPdfExport` records for a quotation with scoped permissions. Consider adding webhook hooks on export completion.

- **Version history & auditing**
  - Add `ManualSpecificationDraftVersion` table (or a JSONB append-only log) to store immutable snapshots (who, when, delta). Provide a UI for diffs.

- **Digital Signatures**
  - Post-export hook: sign the PDF via an external signing service (REST API) and store signature metadata on `QuotationPdfExport`.

- **Background processing**
  - Offload long-running exports to a background task queue (Celery, RQ). Store `QuotationPdfExport.status` and update on completion.

---

**8. Coding Standards**

- **Separation of concerns**:
  - **Business logic**: `services/*` only. Services should be small, single-responsibility classes or modules.
  - **Views**: keep minimal — parse request, call service, return response.
  - **Templates**: presentation only, expect a consistent `pdf_ctx` contract. Avoid embedding heavy logic in templates.

- **Single source of truth**:
  - `SpecificationResolver` is the authoritative generator for initial recommendations.
  - `PreviewService` is the authoritative renderer for drafts (preview==export principle).
  - `ExportService` must never call `SpecificationResolver` or reconstruct the specification from the Quotation.

- **Data persistence rules**:
  - Draft JSON must contain only JSON-serializable structures. Never persist model instances inside JSONFields.
  - If you need a canonical domain object for passing between services, serialize it to primitives first.

- **API contracts**:
  - Services return plain Python dicts/lists/strings (no ORM objects unless the contract says so).
  - Use explicit method names and clear param lists (avoid implicit global state).

- **Tests and validation**:
  - Add focused unit tests for: `SpecificationResolver`, `ManualSpecificationBuilderService.create_draft_from_resolver`, `PreviewService`, `ExportService` (mock PDF conversion), and template rendering fallbacks.
  - Add small end-to-end validation scripts (already present under `scripts/`) and wrap them into CI jobs.

- **Error handling**:
  - Fail early for non-serializable draft data. Log template rendering failures to Sentry and present user-friendly messages.

---

**9. Technical Debt**

- **Template brittleness**: Templates expect a certain `pdf_ctx` contract. Some templates still assume model attributes (e.g., `.pk`) which leads to failures when `pdf_ctx` is built from JSON payloads. Normalize templates to use dict-style access.
- **Lack of Exporter abstraction**: Export logic is currently PDF-centric. Add an exporter interface for DOCX/HTML in V3.
- **No robust versioning**: Drafts do not have an immutable version log. Add a version table or snapshot strategy.
- **WeasyPrint dependency on native libs**: Windows and CI builds require proper native libs; set up CI images that include them or use a containerized exporter.
- **Testing gaps**: Missing unit tests for critical boundaries, especially around JSON serializability and the `rendered_html` pre-rendering path.
- **Race conditions on pre-rendering**: If pre-rendering fails partially, the draft may be left with incomplete `rendered_html` map — add transactional semantics or background re-render.
- **Storage strategy for exports**: Currently exports may be stored on the app server; better to move to object storage with signed URLs.

---

**10. Version 3 Roadmap (recommended packs)**

- **Pack 3A — Exporter Abstraction**: Extract PDF conversion into `exporters/pdf_exporter.py`, add a `BaseExporter` API, add registration, and add a `docx` exporter skeleton.
- **Pack 3B — Draft Versioning & Audits**: Implement `ManualSpecificationDraftVersion` and UI for history/diffs.
- **Pack 3C — Background Exports & Queuing**: Add Celery/RQ for long-running exports and integrate progress/status tracking.
- **Pack 3D — AI-assisted Editing**: Add an `ai_assistant` service that suggests clause-level edits and preserves diffs.
- **Pack 3E — Client Portal & Permissions**: Add API endpoints to list drafts/exports, permission checks, and signed download URLs.
- **Pack 3F — Signing & Compliance**: Add post-export digital signature flow and signed audit metadata.

---

**11. Final Architecture Diagram**

```mermaid
flowchart LR
  Q[Quotation] --> R[SpecificationResolver]
  R --> D[ManualSpecificationDraft (DB)]
  D --> P[PreviewService]
  D --> X[ExportService]
  P --> UI[Preview Page]
  X --> PDF[PDF (WeasyPrint)]
  PDF --> E[QuotationPdfExport (DB)]

  subgraph Services
    R
    P
    X
    PDF
  end

  style D fill:#f9f,stroke:#333,stroke-width:1px
  style E fill:#efe,stroke:#333,stroke-width:1px
  style UI fill:#eef,stroke:#333,stroke-width:1px
```

---

**12. Lessons Learned**

- **Persisting JSON only avoids subtle bugs**: Storing ORM instances inside JSON fields leads to serialization errors and fragile migrations. Enforce JSON serializability early.
- **Pre-rendering is the pragmatic way to guarantee preview==export**: Saving `rendered_html` produced by the server ensures the preview and export use the same HTML. It reduces divergence between UI rendering and server-side export.
- **Keep the resolver authoritative and isolated**: The resolver encodes business rules. Preventing other services from re-running/resimulating those rules avoids drift and inconsistencies.
- **Service-layer architecture simplifies testing and extension**: Concentrating logic in services makes extending functionality (AI assistants, exporters) straightforward.
- **Templates must be defensive**: Templates should assume `pdf_ctx` contains primitives and avoid attribute lookups that only work on model instances.

---

**Getting Started — For the developer returning in six months**

- **Where to look first**:
  - `specifications/services/builder_service.py` — builder logic and draft creation.
  - `specifications/services/preview_service.py` — preview rules and `rendered_html` usage.
  - `specifications/services/export_service.py` — export flow and PDF creation.
  - `quotation/pdf_service.py` — `build_pdf_context` and template helpers.
  - `specifications/models.py` — `ManualSpecificationDraft` model.
  - `templates/specifications/preview_rendered.html` — how pre-rendered HTML is embedded.

- **Quick validation commands** (from project root):

```bash
# Ensure migrations are applied
python manage.py migrate --noinput

# Validate resolver output
python scripts/validate_resolver.py

# Create a draft from resolver and validate
python scripts/validate_builder.py

# Render preview for a draft
python scripts/validate_preview.py

# Export a draft to PDF (may require WeasyPrint native libs)
python scripts/validate_export.py
```

- **If PDF export fails**: check WeasyPrint native dependencies and log files. On Windows, follow WeasyPrint installation docs (libpango, cairo, etc.) or run the export inside a Linux container that includes them.

---

**Contact Notes / Handoff Tips**

- The most likely first tasks on return will be (1) add exporter abstraction, (2) add version history, (3) harden template contracts and tests. Start by running the `scripts/validate_*.py` scripts to exercise the end-to-end flows.

- Keep the invariant: `ExportService` must never rebuild or re-resolve the specification. If you need modified rules, change the `SpecificationResolver` and re-generate drafts intentionally.

---

End of Version 2 Handover
