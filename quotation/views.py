import json

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, View

from audit.services import log_action
from paints.models import Paint

from .config import (
    FINISH_TO_PAINT_GROUPS,
    FINISHES,
    INTERIOR_SECTION_CONFIGS,
    MOISTURE_WARNING_THRESHOLD,
    OTHER_PREP_OPTIONS,
    PAINT_GROUPS,
    PRIMER_OPTIONS,
    SURFACE_CONDITIONS,
    WALL_TYPES,
    WATERPROOFING_OPTIONS,
    get_paint_groups_for_finishes,
)
from .description_engine import generate_line_item_description
from .forms import QuotationStartForm
from .models import Quotation, QuotationLineItem, QuotationSection
from .services import ALL_SUBSECTIONS, EXTERIOR_SUBSECTIONS, INTERIOR_SUBSECTIONS


# ---------------------------------------------------------------------------
# Shared access mixin
# ---------------------------------------------------------------------------

class QuotationAccessMixin(LoginRequiredMixin):
    """
    REP  → sees only quotations they created.
    ADMIN / superuser → sees all quotations.
    """

    def _is_admin(self):
        u = self.request.user
        return u.is_superuser or getattr(u, "role", None) == "ADMIN"

    def get_base_qs(self):
        qs = Quotation.objects.select_related("created_by")
        if not self._is_admin():
            qs = qs.filter(created_by=self.request.user)
        return qs


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class QuotationListView(QuotationAccessMixin, ListView):
    template_name       = "quotation/quotation_list.html"
    context_object_name = "quotations"
    paginate_by         = 25

    def get_queryset(self):
        qs = self.get_base_qs()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(customer_name__icontains=q)
                | Q(reference__icontains=q)
                | Q(project_name__icontains=q)
            )
        status = self.request.GET.get("status", "")
        if status in Quotation.Status.values:
            qs = qs.filter(status=status)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]              = self.request.GET.get("q", "")
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["status_choices"] = Quotation.Status.choices
        ctx["is_admin"]       = self._is_admin()
        return ctx


# ---------------------------------------------------------------------------
# Start (create DRAFT)
# ---------------------------------------------------------------------------

class QuotationStartView(QuotationAccessMixin, View):
    template_name = "quotation/quotation_start.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"form": QuotationStartForm()})

    def post(self, request, *args, **kwargs):
        form = QuotationStartForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        quotation = form.save(commit=False)
        quotation.created_by = request.user
        quotation.status = Quotation.Status.DRAFT
        quotation.save()

        log_action(
            user=request.user,
            action="QUOTATION_CREATED",
            module="quotation",
            description=f"Quotation {quotation.reference} created for {quotation.customer_name}.",
            metadata={"quotation_id": quotation.pk, "reference": quotation.reference},
            request=request,
        )

        messages.success(request, f"Quotation {quotation.reference} created. Now select your surfaces.")
        return redirect("quotation:quotation_sections", pk=quotation.pk)


# ---------------------------------------------------------------------------
# Substrate / section selection
# ---------------------------------------------------------------------------

class QuotationSubstrateSelectionView(QuotationAccessMixin, View):
    template_name = "quotation/quotation_sections.html"

    def _get_quotation(self, request, pk):
        return get_object_or_404(self.get_base_qs(), pk=pk)

    def get(self, request, pk, *args, **kwargs):
        quotation = self._get_quotation(request, pk)
        existing_keys = set(quotation.sections.values_list("subsection_key", flat=True))
        return render(request, self.template_name, {
            "quotation":     quotation,
            "interior_subs": INTERIOR_SUBSECTIONS,
            "exterior_subs": EXTERIOR_SUBSECTIONS,
            "existing_keys": existing_keys,
        })

    def post(self, request, pk, *args, **kwargs):
        quotation = self._get_quotation(request, pk)
        selected_keys = set(request.POST.getlist("subsections"))

        # Sanitise: only accept keys we know
        valid_keys   = selected_keys & ALL_SUBSECTIONS.keys()
        invalid_keys = selected_keys - valid_keys
        if invalid_keys:
            messages.error(request, "Invalid section selection.")
            return redirect("quotation:quotation_sections", pk=pk)

        if not valid_keys:
            messages.warning(request, "Please select at least one surface to continue.")
            existing_keys = set(quotation.sections.values_list("subsection_key", flat=True))
            return render(request, self.template_name, {
                "quotation":     quotation,
                "interior_subs": INTERIOR_SUBSECTIONS,
                "exterior_subs": EXTERIOR_SUBSECTIONS,
                "existing_keys": existing_keys,
            })

        # Remove deselected sections
        quotation.sections.exclude(subsection_key__in=valid_keys).delete()

        # Create newly selected sections
        existing_keys = set(quotation.sections.values_list("subsection_key", flat=True))
        to_create = [
            QuotationSection(
                quotation=quotation,
                substrate_type=ALL_SUBSECTIONS[key].substrate,
                subsection_key=key,
                display_name=ALL_SUBSECTIONS[key].display_name,
                sort_order=ALL_SUBSECTIONS[key].sort_order,
                is_placeholder=True,
            )
            for key in valid_keys
            if key not in existing_keys
        ]
        if to_create:
            QuotationSection.objects.bulk_create(to_create)

        log_action(
            user=request.user,
            action="QUOTATION_SECTIONS_SELECTED",
            module="quotation",
            description=(
                f"Sections updated for {quotation.reference}: "
                + ", ".join(sorted(valid_keys))
            ),
            metadata={
                "quotation_id": quotation.pk,
                "reference":    quotation.reference,
                "sections":     sorted(valid_keys),
            },
            request=request,
        )

        messages.success(request, "Surfaces saved. Your quotation builder is ready.")
        return redirect("quotation:quotation_builder", pk=pk)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class QuotationBuilderView(QuotationAccessMixin, View):
    template_name = "quotation/quotation_builder.html"

    # ------------------------------------------------------------------
    # Build the interior walls context for a single section
    # ------------------------------------------------------------------
    @staticmethod
    def _iw_context(section: QuotationSection) -> dict:
        """
        Build saved-state dicts for the interior walls partial template.
        Reads existing line items so the form can be pre-populated.
        """
        line_items = list(section.line_items.select_related("paint").all())

        # NOTE item holds the main wall metadata
        note_item = next(
            (li for li in line_items if li.item_type == QuotationLineItem.ItemType.NOTE),
            None,
        )
        meta = note_item.metadata if note_item else {}

        # Keys from saved items
        saved_waterproofing = set()
        saved_primers       = {}   # key → coats str
        saved_prep_work     = set()
        saved_paint_keys    = set()
        saved_paint_bases   = {}   # group_key → base_val
        saved_paint_coats   = {}   # group_key → coats str

        for li in line_items:
            if li.item_type == QuotationLineItem.ItemType.WATERPROOFING:
                saved_waterproofing.add(li.metadata.get("key", ""))
            elif li.item_type == QuotationLineItem.ItemType.PRIMER:
                k = li.metadata.get("key", "")
                saved_primers[k] = str(li.coats)
            elif li.item_type == QuotationLineItem.ItemType.PREP_WORK:
                saved_prep_work.add(li.metadata.get("key", ""))
            elif li.item_type == QuotationLineItem.ItemType.PAINT:
                gk = li.metadata.get("paint_group", "")
                if gk:
                    saved_paint_keys.add(gk)
                    saved_paint_bases[gk] = li.metadata.get("base", "WHITE")
                    saved_paint_coats[gk] = str(li.coats)

        return {
            "configured":          note_item is not None,
            "meta":                meta,
            "line_count":          len(line_items),
            "saved_waterproofing": saved_waterproofing,
            "saved_primers":       saved_primers,
            "saved_prep_work":     saved_prep_work,
            "saved_paint_keys":    saved_paint_keys,
            "saved_paint_bases":   saved_paint_bases,
            "saved_paint_coats":   saved_paint_coats,
            # JSON strings for JS restoration
            "saved_paint_bases_json":  json.dumps(saved_paint_bases),
            "saved_paint_coats_json":  json.dumps(saved_paint_coats),
            "saved_primers_json":      json.dumps(saved_primers),
        }

    @staticmethod
    def _generic_section_context(section: QuotationSection) -> dict:
        """
        Build saved-state dict for any generic interior section
        (ceilings, floors, doors_trims_skirtings, window_frames).
        Reads existing line items so the form can be pre-populated on re-open.
        """
        line_items = list(section.line_items.select_related("paint").all())

        note_item = next(
            (li for li in line_items if li.item_type == QuotationLineItem.ItemType.NOTE),
            None,
        )
        meta = note_item.metadata if note_item else {}

        saved_waterproofing: set  = set()
        saved_primers:       dict = {}
        saved_prep_work:     set  = set()
        saved_paint_keys:    set  = set()
        saved_paint_bases:   dict = {}
        saved_paint_coats:   dict = {}

        for li in line_items:
            if li.item_type == QuotationLineItem.ItemType.WATERPROOFING:
                saved_waterproofing.add(li.metadata.get("key", ""))
            elif li.item_type == QuotationLineItem.ItemType.PRIMER:
                k = li.metadata.get("key", "")
                saved_primers[k] = str(li.coats)
            elif li.item_type == QuotationLineItem.ItemType.PREP_WORK:
                saved_prep_work.add(li.metadata.get("key", ""))
            elif li.item_type == QuotationLineItem.ItemType.PAINT:
                gk = li.metadata.get("paint_group", "")
                if gk:
                    saved_paint_keys.add(gk)
                    saved_paint_bases[gk] = li.metadata.get("base", "WHITE")
                    saved_paint_coats[gk] = str(li.coats)

        return {
            "configured":          note_item is not None,
            "meta":                meta,
            "line_count":          len(line_items),
            "saved_waterproofing": saved_waterproofing,
            "saved_primers":       saved_primers,
            "saved_prep_work":     saved_prep_work,
            "saved_paint_keys":    saved_paint_keys,
            "saved_paint_bases":   saved_paint_bases,
            "saved_paint_coats":   saved_paint_coats,
            # JSON strings for JS restoration
            "saved_paint_bases_json": json.dumps(saved_paint_bases),
            "saved_paint_coats_json": json.dumps(saved_paint_coats),
            "saved_primers_json":     json.dumps(saved_primers),
        }

    def get(self, request, pk, *args, **kwargs):
        quotation     = get_object_or_404(self.get_base_qs(), pk=pk)
        all_sections  = list(quotation.sections.order_by("sort_order"))
        interior_secs = [s for s in all_sections if s.substrate_type == "INTERIOR"]
        exterior_secs = [s for s in all_sections if s.substrate_type == "EXTERIOR"]

        # Build enriched list for interior sections.
        # Each entry carries the section object, its saved-state summary, the
        # config (if generic) and flags so the template can branch cleanly.
        interior_sections_data: list[dict] = []
        for sec in interior_secs:
            if sec.subsection_key == "interior_walls":
                summary    = self._iw_context(sec)
                cfg        = None
                is_walls   = True
                is_generic = False
            elif sec.subsection_key in INTERIOR_SECTION_CONFIGS:
                summary    = self._generic_section_context(sec)
                cfg        = INTERIOR_SECTION_CONFIGS[sec.subsection_key]
                is_walls   = False
                is_generic = True
            else:
                summary    = {"configured": False, "meta": {}, "line_count": 0}
                cfg        = None
                is_walls   = False
                is_generic = False
            interior_sections_data.append({
                "section":    sec,
                "summary":    summary,
                "config":     cfg,
                "is_walls":   is_walls,
                "is_generic": is_generic,
            })

        # Flat pk-keyed summaries dict still used by exterior cards
        section_summaries: dict[int, dict] = {
            entry["section"].pk: entry["summary"]
            for entry in interior_sections_data
        }
        for sec in exterior_secs:
            section_summaries[sec.pk] = {
                "configured": sec.line_items.exists(),
                "meta":       {},
                "line_count": sec.line_items.count(),
            }

        any_configured  = any(v.get("configured", False) for v in section_summaries.values())
        finish_map_json = json.dumps(FINISH_TO_PAINT_GROUPS)

        return render(request, self.template_name, {
            "quotation":              quotation,
            "interior_sections_data": interior_sections_data,
            "interior_secs":          interior_secs,
            "exterior_secs":          exterior_secs,
            "section_summaries":      section_summaries,
            "any_configured":         any_configured,
            "is_admin":               self._is_admin(),
            # shared config passed through to all partials
            "wall_types":             WALL_TYPES,
            "surface_conditions":     SURFACE_CONDITIONS,
            "finishes":               FINISHES,
            "finish_map_json":        finish_map_json,
            "all_paint_groups":       list(PAINT_GROUPS.values()),
            "waterproofing_options":  WATERPROOFING_OPTIONS,
            "primer_options":         PRIMER_OPTIONS,
            "other_prep_options":     OTHER_PREP_OPTIONS,
            "moisture_threshold":     MOISTURE_WARNING_THRESHOLD,
        })


# ---------------------------------------------------------------------------
# Interior Walls – save handler
# ---------------------------------------------------------------------------

def _try_match_paint(paint_name: str, base_type: str) -> Paint | None:
    """
    Return the first active Paint whose name contains paint_name (case-insensitive)
    and whose base_type matches. Returns None if not found — caller must handle.
    """
    try:
        return (
            Paint.objects
            .filter(name__icontains=paint_name, base_type=base_type, is_active=True)
            .first()
        )
    except Exception:
        return None


class InteriorWallsSaveView(QuotationAccessMixin, View):
    """
    POST-only view that saves the Interior Walls configuration for a section.
    Deletes existing line items for this section and recreates from POST data.
    """

    def _get_section(self, request, pk, section_pk):
        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        return get_object_or_404(
            QuotationSection,
            pk=section_pk,
            quotation=quotation,
            subsection_key="interior_walls",
        )

    def post(self, request, pk, section_pk, *args, **kwargs):
        section   = self._get_section(request, pk, section_pk)
        quotation = section.quotation
        POST      = request.POST

        # ── Collect form values ──────────────────────────────────────────────
        wall_type    = POST.get("wall_type", "").strip()
        surface_conds = POST.getlist("surface_conditions")
        finishes     = POST.getlist("finishes")
        area_sqm_raw = POST.get("area_sqm", "").strip()
        moisture_raw = POST.get("moisture_level", "").strip()
        notes        = POST.get("notes", "").strip()

        # Basic validation
        valid_wall_types = {k for k, _ in WALL_TYPES}
        valid_finishes   = {k for k, _ in FINISHES}
        valid_conds      = {k for k, _ in SURFACE_CONDITIONS}

        if wall_type not in valid_wall_types:
            messages.error(request, "Please select a valid wall type.")
            return redirect("quotation:quotation_builder", pk=pk)

        finishes = [f for f in finishes if f in valid_finishes]
        surface_conds = [c for c in surface_conds if c in valid_conds]

        if not finishes:
            messages.error(request, "Please select at least one finish.")
            return redirect("quotation:quotation_builder", pk=pk)

        try:
            area_sqm = Decimal(area_sqm_raw) if area_sqm_raw else None
            if area_sqm is not None and area_sqm < 0:
                raise ValueError
        except (ValueError, Exception):
            messages.error(request, "Please enter a valid area (m²).")
            return redirect("quotation:quotation_builder", pk=pk)

        try:
            moisture = int(moisture_raw) if moisture_raw else 0
            moisture = max(0, min(moisture, 100))
        except ValueError:
            moisture = 0

        # ── Wipe existing line items for this section ───────────────────────
        section.line_items.all().delete()
        # Mark section as configured
        section.is_placeholder = False
        section.save(update_fields=["is_placeholder"])

        # ── 1. NOTE item: wall summary metadata ─────────────────────────────
        wall_type_label    = dict(WALL_TYPES).get(wall_type, wall_type)
        finish_labels      = [dict(FINISHES).get(f, f) for f in finishes]
        cond_labels        = [dict(SURFACE_CONDITIONS).get(c, c) for c in surface_conds]

        QuotationLineItem.objects.create(
            quotation   = quotation,
            section     = section,
            item_type   = QuotationLineItem.ItemType.NOTE,
            description = (
                f"Interior Walls — {wall_type_label} | "
                f"Finishes: {', '.join(finish_labels)} | "
                f"Area: {area_sqm or 'TBC'} m²"
            ),
            area_sqm  = area_sqm,
            metadata  = {
                "wall_type":         wall_type,
                "wall_type_label":   wall_type_label,
                "surface_conditions": surface_conds,
                "surface_cond_labels": cond_labels,
                "finishes":          finishes,
                "finish_labels":     finish_labels,
                "moisture_level":    moisture,
                "notes":             notes,
            },
        )

        # ── 2. WATERPROOFING items ───────────────────────────────────────────
        wp_labels = dict(WATERPROOFING_OPTIONS)
        for wp_key in POST.getlist("waterproofing"):
            if wp_key not in wp_labels:
                continue
            QuotationLineItem.objects.create(
                quotation   = quotation,
                section     = section,
                item_type   = QuotationLineItem.ItemType.WATERPROOFING,
                description = wp_labels[wp_key],
                area_sqm    = area_sqm,
                metadata    = {"key": wp_key},
            )

        # ── 3. PRIMER items ─────────────────────────────────────────────────
        primer_labels = dict(PRIMER_OPTIONS)
        for pr_key in POST.getlist("primers"):
            if pr_key not in primer_labels:
                continue
            try:
                coats = int(POST.get(f"primer_coats_{pr_key}", "1"))
                coats = max(1, min(coats, 2))
            except ValueError:
                coats = 1
            QuotationLineItem.objects.create(
                quotation   = quotation,
                section     = section,
                item_type   = QuotationLineItem.ItemType.PRIMER,
                description = primer_labels[pr_key],
                coats       = coats,
                area_sqm    = area_sqm,
                metadata    = {"key": pr_key},
            )

        # ── 4. PREP_WORK items ───────────────────────────────────────────────
        prep_labels = dict(OTHER_PREP_OPTIONS)
        for prep_key in POST.getlist("prep_work"):
            if prep_key not in prep_labels:
                continue
            QuotationLineItem.objects.create(
                quotation   = quotation,
                section     = section,
                item_type   = QuotationLineItem.ItemType.PREP_WORK,
                description = prep_labels[prep_key],
                metadata    = {"key": prep_key},
            )

        # ── 5. PAINT items ───────────────────────────────────────────────────
        active_groups = get_paint_groups_for_finishes(finishes)
        for pg in active_groups:
            selected = POST.get(f"paint_selected_{pg.key}")
            if not selected:
                continue
            try:
                coats = int(POST.get(f"paint_coats_{pg.key}", "1"))
                coats = max(1, min(coats, 2))
            except ValueError:
                coats = 1

            base_val = POST.get(f"paint_base_{pg.key}", "WHITE").strip()
            base_label = dict(pg.bases).get(base_val, base_val) if pg.bases else ""

            # Attempt paint catalogue match
            matched_paint = _try_match_paint(pg.paint_name, base_val) if base_val else None

            price_excl = matched_paint.price_excl_vat if matched_paint else Decimal("0")
            price_incl = matched_paint.price_incl_vat if matched_paint else Decimal("0")

            description = pg.label
            if base_label:
                description += f" — {base_label}"

            QuotationLineItem.objects.create(
                quotation      = quotation,
                section        = section,
                item_type      = QuotationLineItem.ItemType.PAINT,
                description    = description,
                paint          = matched_paint,
                coats          = coats,
                area_sqm       = area_sqm,
                price_excl_vat = price_excl,
                price_incl_vat = price_incl,
                metadata       = {
                    "paint_group":  pg.key,
                    "paint_name":   pg.paint_name,
                    "base":         base_val,
                    "base_label":   base_label,
                    "paint_matched": matched_paint is not None,
                },
            )

        log_action(
            user        = request.user,
            action      = "INTERIOR_WALLS_SAVED",
            module      = "quotation",
            description = (
                f"Interior Walls configured for {quotation.reference}: "
                f"{wall_type_label}, {', '.join(finish_labels)}, {area_sqm or 'TBC'} m²"
            ),
            metadata    = {
                "quotation_id": quotation.pk,
                "section_id":   section.pk,
                "wall_type":    wall_type,
                "finishes":     finishes,
                "area_sqm":     str(area_sqm) if area_sqm else None,
            },
            request = request,
        )

        messages.success(request, "Interior Walls saved successfully.")
        return redirect("quotation:quotation_builder", pk=pk)


# ---------------------------------------------------------------------------
# Generic Interior Section – save handler
# ---------------------------------------------------------------------------

class GenericInteriorSectionSaveView(QuotationAccessMixin, View):
    """
    POST-only view that saves any supported generic interior section
    (ceilings, floors, doors_trims_skirtings, window_frames).

    Deletes existing line items for the section and recreates them from POST
    data.  The InteriorSectionConfig drives validation and labelling so there
    is no per-section branching here.
    """

    _GENERIC_KEYS = frozenset(INTERIOR_SECTION_CONFIGS.keys())

    def _get_section(self, request, pk, section_pk):
        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        return get_object_or_404(
            QuotationSection,
            pk=section_pk,
            quotation=quotation,
            subsection_key__in=self._GENERIC_KEYS,
        )

    def post(self, request, pk, section_pk, *args, **kwargs):
        section   = self._get_section(request, pk, section_pk)
        quotation = section.quotation
        cfg       = INTERIOR_SECTION_CONFIGS.get(section.subsection_key)

        if not cfg:
            messages.error(request, "Unknown section configuration.")
            return redirect("quotation:quotation_builder", pk=pk)

        POST = request.POST

        # ── Collect and validate ─────────────────────────────────────────────
        valid_types   = {k for k, _ in cfg.types}
        valid_finishes = {k for k, _ in cfg.finishes}
        valid_conds   = {k for k, _ in cfg.surface_conditions}

        selected_types = [t for t in POST.getlist("types")              if t in valid_types]
        surface_conds  = [c for c in POST.getlist("surface_conditions") if c in valid_conds]
        finishes       = [f for f in POST.getlist("finishes")           if f in valid_finishes]

        if not selected_types:
            messages.error(
                request,
                f"Please select at least one {cfg.type_label.lower()}.",
            )
            return redirect("quotation:quotation_builder", pk=pk)

        if not finishes:
            messages.error(request, "Please select at least one finish.")
            return redirect("quotation:quotation_builder", pk=pk)

        area_sqm_raw = POST.get("area_sqm", "").strip()
        try:
            area_sqm = Decimal(area_sqm_raw) if area_sqm_raw else None
            if area_sqm is not None and area_sqm < 0:
                raise ValueError
        except (ValueError, Exception):
            messages.error(request, "Please enter a valid area (m\u00b2).")
            return redirect("quotation:quotation_builder", pk=pk)

        moisture_raw = POST.get("moisture_level", "").strip()
        try:
            moisture = int(moisture_raw) if moisture_raw else 0
            moisture = max(0, min(moisture, 100))
        except ValueError:
            moisture = 0

        notes = POST.get("notes", "").strip()

        # ── Wipe and rebuild line items ──────────────────────────────────────
        section.line_items.all().delete()
        section.is_placeholder = False
        section.save(update_fields=["is_placeholder"])

        type_labels   = [dict(cfg.types).get(t, t)                  for t in selected_types]
        finish_labels = [dict(cfg.finishes).get(f, f)              for f in finishes]
        cond_labels   = [dict(cfg.surface_conditions).get(c, c)    for c in surface_conds]

        # ── 1. NOTE (section summary metadata) ──────────────────────────────
        QuotationLineItem.objects.create(
            quotation   = quotation,
            section     = section,
            item_type   = QuotationLineItem.ItemType.NOTE,
            description = (
                f"{cfg.display_name} \u2014 {', '.join(type_labels)} | "
                f"Finishes: {', '.join(finish_labels)} | "
                f"Area: {area_sqm or 'TBC'} m\u00b2"
            ),
            area_sqm    = area_sqm,
            metadata    = {
                "section_key":         cfg.key,
                "section_name":        cfg.display_name,
                "types":               selected_types,
                "type_labels":         type_labels,
                "surface_conditions":  surface_conds,
                "surface_cond_labels": cond_labels,
                "finishes":            finishes,
                "finish_labels":       finish_labels,
                "moisture_level":      moisture,
                "area_sqm":            str(area_sqm) if area_sqm else None,
                "notes":               notes,
            },
        )

        # ── 2. WATERPROOFING items ───────────────────────────────────────────
        wp_labels = dict(WATERPROOFING_OPTIONS)
        for wp_key in POST.getlist("waterproofing"):
            if wp_key not in wp_labels:
                continue
            QuotationLineItem.objects.create(
                quotation   = quotation,
                section     = section,
                item_type   = QuotationLineItem.ItemType.WATERPROOFING,
                description = wp_labels[wp_key],
                area_sqm    = area_sqm,
                metadata    = {"key": wp_key},
            )

        # ── 3. PRIMER items ─────────────────────────────────────────────────
        primer_labels = dict(PRIMER_OPTIONS)
        for pr_key in POST.getlist("primers"):
            if pr_key not in primer_labels:
                continue
            try:
                coats = int(POST.get(f"primer_coats_{pr_key}", "1"))
                coats = max(1, min(coats, 2))
            except ValueError:
                coats = 1
            QuotationLineItem.objects.create(
                quotation   = quotation,
                section     = section,
                item_type   = QuotationLineItem.ItemType.PRIMER,
                description = primer_labels[pr_key],
                coats       = coats,
                area_sqm    = area_sqm,
                metadata    = {"key": pr_key},
            )

        # ── 4. PREP_WORK items ───────────────────────────────────────────────
        prep_labels = dict(OTHER_PREP_OPTIONS)
        for prep_key in POST.getlist("prep_work"):
            if prep_key not in prep_labels:
                continue
            QuotationLineItem.objects.create(
                quotation   = quotation,
                section     = section,
                item_type   = QuotationLineItem.ItemType.PREP_WORK,
                description = prep_labels[prep_key],
                metadata    = {"key": prep_key},
            )

        # ── 5. PAINT items ───────────────────────────────────────────────────
        active_groups = get_paint_groups_for_finishes(finishes)
        for pg in active_groups:
            if not POST.get(f"paint_selected_{pg.key}"):
                continue
            try:
                coats = int(POST.get(f"paint_coats_{pg.key}", "1"))
                coats = max(1, min(coats, 2))
            except ValueError:
                coats = 1

            base_val   = POST.get(f"paint_base_{pg.key}", "WHITE").strip()
            base_label = dict(pg.bases).get(base_val, base_val) if pg.bases else ""

            matched_paint  = _try_match_paint(pg.paint_name, base_val) if base_val else None
            price_excl     = matched_paint.price_excl_vat if matched_paint else Decimal("0")
            price_incl     = matched_paint.price_incl_vat if matched_paint else Decimal("0")

            description = pg.label
            if base_label:
                description += f" \u2014 {base_label}"

            QuotationLineItem.objects.create(
                quotation      = quotation,
                section        = section,
                item_type      = QuotationLineItem.ItemType.PAINT,
                description    = description,
                paint          = matched_paint,
                coats          = coats,
                area_sqm       = area_sqm,
                price_excl_vat = price_excl,
                price_incl_vat = price_incl,
                metadata       = {
                    "paint_group":   pg.key,
                    "paint_name":    pg.paint_name,
                    "base":          base_val,
                    "base_label":    base_label,
                    "paint_matched": matched_paint is not None,
                },
            )

        # ── Audit log ────────────────────────────────────────────────────────
        action_key = f"SECTION_SAVED_{cfg.key.upper()}"
        log_action(
            user        = request.user,
            action      = action_key,
            module      = "quotation",
            description = (
                f"{cfg.display_name} configured for {quotation.reference}: "
                f"{', '.join(type_labels)}, {', '.join(finish_labels)}, "
                f"{area_sqm or 'TBC'} m\u00b2"
            ),
            metadata    = {
                "quotation_id": quotation.pk,
                "section_id":   section.pk,
                "section_key":  cfg.key,
                "types":        selected_types,
                "finishes":     finishes,
                "area_sqm":     str(area_sqm) if area_sqm else None,
            },
            request = request,
        )

        messages.success(request, f"{cfg.display_name} saved successfully.")
        return redirect("quotation:quotation_builder", pk=pk)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

class QuotationReviewView(QuotationAccessMixin, View):
    template_name = "quotation/quotation_review.html"

    def get(self, request, pk, *args, **kwargs):
        quotation = get_object_or_404(
            self.get_base_qs().prefetch_related(
                "sections",
                "sections__line_items",
                "sections__line_items__paint",
            ),
            pk=pk,
        )

        all_sections = list(quotation.sections.order_by("sort_order"))

        # Build per-section review data
        section_data = []
        for sec in all_sections:
            items = list(sec.line_items.select_related("paint").order_by("item_type", "pk"))
            # Attach generated description to each item so the template stays logic-free
            enriched_items = [
                {
                    "item":        li,
                    "description": generate_line_item_description(li),
                }
                for li in items
            ]
            section_data.append({
                "section":    sec,
                "configured": len(items) > 0,
                "items":      enriched_items,
            })

        # Simple totals (sum of stored price fields — will be zero until pricing is wired)
        subtotal = sum(
            (entry["item"].total_excl_vat or Decimal("0"))
            for entry_sec in section_data
            for entry in entry_sec["items"]
        )

        log_action(
            user        = request.user,
            action      = "QUOTATION_REVIEWED",
            module      = "quotation",
            description = f"Quotation {quotation.reference} reviewed by {request.user}.",
            metadata    = {
                "quotation_id": quotation.pk,
                "reference":    quotation.reference,
            },
            request = request,
        )

        return render(request, self.template_name, {
            "quotation":    quotation,
            "section_data": section_data,
            "subtotal":     subtotal,
            "is_admin":     self._is_admin(),
        })


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

class QuotationDetailView(QuotationAccessMixin, DetailView):
    template_name       = "quotation/quotation_detail.html"
    context_object_name = "quotation"

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_base_qs(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_admin"] = self._is_admin()
        ctx["sections"] = self.object.sections.order_by("substrate_type", "sort_order")
        return ctx

