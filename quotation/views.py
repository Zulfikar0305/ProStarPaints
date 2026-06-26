import json

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.db import IntegrityError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView, View

from audit.services import log_action
from paints.models import Paint

from .config import (
    ALL_GENERIC_SECTION_CONFIGS,
    FINISH_TO_PAINT_GROUPS,
    FINISHES,
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
from .models import (
    Quotation,
    QuotationLineItem,
    QuotationPdfExport,
    QuotationPin,
    QuotationSection,
    QuotationSectionImage,
)
from .preflight import get_quotation_preflight
from .services import (
    ALL_SUBSECTIONS,
    EXTERIOR_SUBSECTIONS,
    INTERIOR_SUBSECTIONS,
    get_quotation_summary,
    create_repeatable_section,
    delete_repeatable_section,
    get_leaflet_groups,
)
from .pricing import apply_paint_pricing_to_line_item, recalculate_quotation_totals
from .workspace import (
    HAS_PDF_CHOICES,
    READINESS_FILTER_CHOICES,
    annotate_workspace,
    apply_quotation_filters,
    get_pinned_pk_set,
    get_pinned_quotations,
    get_quotation_readiness,
    get_quotation_workspace_stats,
    get_recently_viewed_quotations,
    track_recent_quotation,
)


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
    """The Quotations Workspace — stats, filters, pins, recently-viewed and list."""

    template_name       = "quotation/quotation_list.html"
    context_object_name = "quotations"
    paginate_by         = 25

    # ── view-mode handling ───────────────────────────────────────────
    def _resolve_view_mode(self):
        """Return 'table' or 'cards' from ?view= override or user preference."""
        requested = (self.request.GET.get("view") or "").lower()
        if requested in ("table", "cards"):
            return requested
        pref = getattr(
            getattr(self.request.user, "app_settings", None),
            "preferred_quotation_view",
            None,
        )
        return pref if pref in ("table", "cards") else "table"

    def get_queryset(self):
        qs = apply_quotation_filters(self.get_base_qs(), self.request, self.request.user)
        return qs.order_by("-updated_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        req = self.request

        ctx["q"]              = req.GET.get("q", "")
        ctx["current_status"] = req.GET.get("status", "")
        ctx["current_readiness"] = req.GET.get("readiness", "")
        ctx["current_has_pdf"] = req.GET.get("has_pdf", "")
        ctx["current_date_from"] = req.GET.get("date_from", "")
        ctx["current_date_to"]   = req.GET.get("date_to", "")
        ctx["current_rep"]    = req.GET.get("rep", "")
        ctx["status_choices"] = Quotation.Status.choices
        ctx["readiness_choices"] = READINESS_FILTER_CHOICES
        ctx["has_pdf_choices"] = HAS_PDF_CHOICES
        ctx["is_admin"]       = self._is_admin()
        ctx["view_mode"]      = self._resolve_view_mode()
        ctx["has_filters"]    = any([
            ctx["q"], ctx["current_status"], ctx["current_readiness"],
            ctx["current_has_pdf"], ctx["current_date_from"],
            ctx["current_date_to"], ctx["current_rep"],
        ])

        # Admin-only rep filter list
        if ctx["is_admin"]:
            from users.models import User
            ctx["rep_choices"] = (
                User.objects.filter(quotations__isnull=False)
                .distinct().order_by("first_name", "last_name", "username")
            )

        # Stats
        ctx["stats"] = get_quotation_workspace_stats(user)

        # Readiness for the current page
        page_qs = ctx.get("page_obj").object_list if ctx.get("page_obj") else ctx["quotations"]
        pin_set = get_pinned_pk_set(user)
        rows = []
        for q in page_qs:
            rows.append({
                "q":         q,
                "readiness": get_quotation_readiness(q),
                "is_pinned": q.pk in pin_set,
            })
        ctx["rows"] = rows

        # Pinned + recently viewed (annotated, scoped)
        pinned = get_pinned_quotations(user)
        ctx["pinned_quotations"] = [
            {"q": q, "readiness": get_quotation_readiness(q)} for q in pinned
        ]
        recents = get_recently_viewed_quotations(user, req.session)
        ctx["recent_quotations"] = [
            {"q": q, "readiness": get_quotation_readiness(q)} for q in recents
        ]

        # Preserve filter querystring for pagination links (without page=)
        params = req.GET.copy()
        params.pop("page", None)
        ctx["filter_qs"] = params.urlencode()

        return ctx


# ---------------------------------------------------------------------------
# Pin / unpin
# ---------------------------------------------------------------------------

class QuotationPinToggleView(QuotationAccessMixin, View):
    """Toggle a pin on a quotation the current user is allowed to access."""

    def post(self, request, pk):
        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        pin, created = QuotationPin.objects.get_or_create(
            user=request.user, quotation=quotation,
        )
        if not created:
            pin.delete()
            messages.info(request, f"Unpinned {quotation.reference}.")
            action = "QUOTATION_UNPINNED"
        else:
            messages.success(request, f"Pinned {quotation.reference}.")
            action = "QUOTATION_PINNED"
        log_action(
            user=request.user,
            action=action,
            module="quotation",
            description=f"{request.user} {'pinned' if created else 'unpinned'} {quotation.reference}.",
            metadata={"quotation_id": quotation.pk, "reference": quotation.reference},
            request=request,
        )
        # Validate next URL to prevent open-redirect (don't follow off-site refs)
        from django.utils.http import url_has_allowed_host_and_scheme
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect("quotation:quotation_list")


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

        # Existing keys on this quotation
        existing_keys = set(quotation.sections.values_list("subsection_key", flat=True))

        # If no valid keys and there are no existing selections, require the
        # user to pick at least one surface (initial selection). If there are
        # existing selections, allow submitting an empty set to unselect all
        # categories (i.e. delete all sections for the quotation).
        if not valid_keys and not existing_keys:
            messages.warning(request, "Please select at least one surface to continue.")
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
        return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet=interior_walls")


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
        saved_paint_rows    = []   # list of existing paint-row dicts for this section
        saved_primer_rows   = []   # repeatable primer rows (per-row)
        saved_waterproof_rows = [] # repeatable waterproofing rows (per-row)

        for li in line_items:
            if li.item_type == QuotationLineItem.ItemType.WATERPROOFING:
                saved_waterproofing.add(li.metadata.get("key", ""))
                saved_waterproof_rows.append({
                    "line_pk": li.pk,
                    "key": li.metadata.get("key", ""),
                    "coats": li.coats,
                    "area_sqm": str(li.area_sqm) if li.area_sqm is not None else "",
                    "price_excl_vat": str(li.price_excl_vat or 0),
                    "price_incl_vat": str(li.price_incl_vat or 0),
                    "total_excl_vat": str(li.total_excl_vat or 0),
                    "total_incl_vat": str(li.total_incl_vat or 0),
                    "metadata": li.metadata or {},
                })
            elif li.item_type == QuotationLineItem.ItemType.PRIMER:
                k = li.metadata.get("key", "")
                saved_primers[k] = str(li.coats)
                saved_primer_rows.append({
                    "line_pk": li.pk,
                    "key": k,
                    "coats": li.coats,
                    "area_sqm": str(li.area_sqm) if li.area_sqm is not None else "",
                    "price_excl_vat": str(li.price_excl_vat or 0),
                    "price_incl_vat": str(li.price_incl_vat or 0),
                    "total_excl_vat": str(li.total_excl_vat or 0),
                    "total_incl_vat": str(li.total_incl_vat or 0),
                    "metadata": li.metadata or {},
                })
            elif li.item_type == QuotationLineItem.ItemType.PREP_WORK:
                saved_prep_work.add(li.metadata.get("key", ""))
            elif li.item_type == QuotationLineItem.ItemType.PAINT:
                # Preserve per-paint line information so the UI can render repeatable rows
                try:
                    paint_pk = li.paint.pk if li.paint else None
                except Exception:
                    paint_pk = None
                saved_paint_rows.append({
                    "line_pk": li.pk,
                    "paint_pk": paint_pk,
                    "coats": li.coats,
                    "area_sqm": str(li.area_sqm) if li.area_sqm is not None else "",
                    "price_excl_vat": str(li.price_excl_vat or 0),
                    "price_incl_vat": str(li.price_incl_vat or 0),
                    "metadata": li.metadata or {},
                })
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
            "saved_paint_rows":    saved_paint_rows,
            "saved_primer_rows":   saved_primer_rows,
            "saved_waterproof_rows": saved_waterproof_rows,
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
        saved_paint_rows:    list = []
        saved_primer_rows:   list = []
        saved_waterproof_rows: list = []

        for li in line_items:
            if li.item_type == QuotationLineItem.ItemType.WATERPROOFING:
                saved_waterproofing.add(li.metadata.get("key", ""))
                saved_waterproof_rows.append({
                    "line_pk": li.pk,
                    "key": li.metadata.get("key", ""),
                    "coats": li.coats,
                    "area_sqm": str(li.area_sqm) if li.area_sqm is not None else "",
                    "price_excl_vat": str(li.price_excl_vat or 0),
                    "price_incl_vat": str(li.price_incl_vat or 0),
                    "total_excl_vat": str(li.total_excl_vat or 0),
                    "total_incl_vat": str(li.total_incl_vat or 0),
                    "metadata": li.metadata or {},
                })
            elif li.item_type == QuotationLineItem.ItemType.PRIMER:
                k = li.metadata.get("key", "")
                saved_primers[k] = str(li.coats)
                saved_primer_rows.append({
                    "line_pk": li.pk,
                    "key": k,
                    "coats": li.coats,
                    "area_sqm": str(li.area_sqm) if li.area_sqm is not None else "",
                    "price_excl_vat": str(li.price_excl_vat or 0),
                    "price_incl_vat": str(li.price_incl_vat or 0),
                    "total_excl_vat": str(li.total_excl_vat or 0),
                    "total_incl_vat": str(li.total_incl_vat or 0),
                    "metadata": li.metadata or {},
                })
            elif li.item_type == QuotationLineItem.ItemType.PREP_WORK:
                saved_prep_work.add(li.metadata.get("key", ""))
            elif li.item_type == QuotationLineItem.ItemType.PAINT:
                try:
                    paint_pk = li.paint.pk if li.paint else None
                except Exception:
                    paint_pk = None
                saved_paint_rows.append({
                    "line_pk": li.pk,
                    "paint_pk": paint_pk,
                    "coats": li.coats,
                    "area_sqm": str(li.area_sqm) if li.area_sqm is not None else "",
                    "price_excl_vat": str(li.price_excl_vat or 0),
                    "price_incl_vat": str(li.price_incl_vat or 0),
                    "metadata": li.metadata or {},
                })
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
            "saved_paint_rows":    saved_paint_rows,
            "saved_primer_rows":   saved_primer_rows,
            "saved_waterproof_rows": saved_waterproof_rows,
            # JSON strings for JS restoration
            "saved_paint_bases_json": json.dumps(saved_paint_bases),
            "saved_paint_coats_json": json.dumps(saved_paint_coats),
            "saved_primers_json":     json.dumps(saved_primers),
        }

    def get(self, request, pk, *args, **kwargs):
        quotation     = get_object_or_404(self.get_base_qs(), pk=pk)
        track_recent_quotation(request.session, quotation.pk)
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
            elif sec.subsection_key in ALL_GENERIC_SECTION_CONFIGS:
                summary    = self._generic_section_context(sec)
                cfg        = ALL_GENERIC_SECTION_CONFIGS[sec.subsection_key]
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

        # Flat pk-keyed summaries dict (kept for backward compat)
        section_summaries: dict[int, dict] = {
            entry["section"].pk: entry["summary"]
            for entry in interior_sections_data
        }

        # Build enriched list for exterior sections.
        exterior_sections_data: list[dict] = []
        for sec in exterior_secs:
            if sec.subsection_key in ALL_GENERIC_SECTION_CONFIGS:
                summary    = self._generic_section_context(sec)
                cfg        = ALL_GENERIC_SECTION_CONFIGS[sec.subsection_key]
                is_generic = True
            else:
                summary    = {
                    "configured": sec.line_items.exists(),
                    "meta":       {},
                    "line_count": sec.line_items.count(),
                }
                cfg        = None
                is_generic = False
            exterior_sections_data.append({
                "section":    sec,
                "summary":    summary,
                "config":     cfg,
                "is_generic": is_generic,
            })
            section_summaries[sec.pk] = summary

        any_configured  = any(v.get("configured", False) for v in section_summaries.values())
        finish_map_json = json.dumps(FINISH_TO_PAINT_GROUPS)

        # Leaflet grouping data for the builder (server-side only)
        leaflet_groups = get_leaflet_groups(quotation)
        selected_leaflet_keys = [g["key"] for g in leaflet_groups]
        default_leaflet_key = selected_leaflet_keys[0] if selected_leaflet_keys else None

        # Active leaflet selection (server-driven via ?leaflet=)
        requested_leaflet = request.GET.get("leaflet")
        if requested_leaflet in selected_leaflet_keys:
            active_leaflet_key = requested_leaflet
        else:
            active_leaflet_key = default_leaflet_key

        active_leaflet_group = None
        active_leaflet_selections = []
        if active_leaflet_key:
            for g in leaflet_groups:
                if g["key"] == active_leaflet_key:
                    active_leaflet_group = g
                    active_leaflet_selections = g.get("selections", [])
                    break

        # Build a pk-keyed lookup of the previously-prepared section entries
        section_entry_map = {}
        for entry in interior_sections_data + exterior_sections_data:
            section_entry_map[entry["section"].pk] = entry

        # Build the active sections payload for template consumption. Each
        # entry mirrors the per-section entry used elsewhere so partials can
        # be re-used without duplicating preparation logic in templates.
        active_sections_data = []
        for sel in active_leaflet_selections:
            s = sel["section"]
            entry = section_entry_map.get(s.pk, {})
            active_sections_data.append({
                "section": s,
                "summary": entry.get("summary", {}),
                "config": entry.get("config"),
                "is_walls": entry.get("is_walls", s.subsection_key == "interior_walls"),
                "is_generic": entry.get("is_generic", s.subsection_key in ALL_GENERIC_SECTION_CONFIGS),
                "selection_label": sel.get("selection_label"),
                "selection_order": sel.get("selection_order"),
            })

        return render(request, self.template_name, {
            "quotation":              quotation,
            "interior_sections_data": interior_sections_data,
            "exterior_sections_data": exterior_sections_data,
            "interior_secs":          interior_secs,
            "exterior_secs":          exterior_secs,
            "section_summaries":      section_summaries,
            "any_configured":         any_configured,
            "quotation_summary":      get_quotation_summary(quotation),
            "leaflet_groups":         leaflet_groups,
            "selected_leaflet_keys":  selected_leaflet_keys,
            "default_leaflet_key":    default_leaflet_key,
            "active_leaflet_key":     active_leaflet_key,
            "active_leaflet_group":   active_leaflet_group,
            "active_leaflet_can_add": active_leaflet_key in ALL_SUBSECTIONS if active_leaflet_key else False,
            "active_leaflet_selections": active_leaflet_selections,
            "active_sections_data":   active_sections_data,
            "is_admin":               self._is_admin(),
            # All available paints for client-side population of paint-row selects
            "all_paints_json":       json.dumps([
                {
                    "pk": int(p.pk),
                    "name": p.name,
                    "spread_rate_per_litre": str(p.spread_rate_per_litre) if p.spread_rate_per_litre is not None else None,
                    "price_excl_vat": str(p.price_excl_vat),
                    "price_incl_vat": str(p.price_incl_vat),
                    "priced_volume_litres": str(p.priced_volume_litres) if p.priced_volume_litres is not None else None,
                    "finish": p.finish,
                    "group_key": next((k for k, g in PAINT_GROUPS.items() if g.paint_name.lower() in p.name.lower()), None),
                    "base_type": p.base_type,
                }
                for p in Paint.objects.filter(is_active=True)
            ]),
            # JSON map of paint-groups for client-side base selectors
            "paint_groups_json": json.dumps({
                k: {"bases": v.bases, "label": v.label} for k, v in PAINT_GROUPS.items()
            }),
            "all_paints":            Paint.objects.filter(is_active=True).order_by("name"),
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


def _find_catalogue_paint_by_label(label: str, category: str | None = None) -> Paint | None:
    """
    Attempt to find a catalogue Paint that best matches a UI label and optional category.

    Matching strategy (in order):
    - exact name (case-insensitive)
    - name contains label (case-insensitive)
    - name contains any individual word from label
    - first active paint in the category (only when category is provided)

    Returns None when no reasonable match found.
    """
    try:
        qs = Paint.objects.filter(is_active=True)
        if category:
            qs = qs.filter(category=category)

        # 1) exact
        p = qs.filter(name__iexact=label).first()
        if p:
            return p

        # 2) contains whole label
        p = qs.filter(name__icontains=label).first()
        if p:
            return p

        # 3) try individual words
        for w in (label or "").split():
            if not w:
                continue
            p = qs.filter(name__icontains=w).first()
            if p:
                return p

        # 4) fallback: first in category (only if category provided)
        if category:
            return qs.first()
    except Exception:
        return None
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
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet=interior_walls#section-{section.pk}")

        # Finishes are now owned by individual paint rows. Keep section-level
        # surface conditions validation but do not require section-level finishes.
        surface_conds = [c for c in surface_conds if c in valid_conds]

        try:
            area_sqm = Decimal(area_sqm_raw) if area_sqm_raw else None
            if area_sqm is not None and area_sqm < 0:
                raise ValueError
        except (ValueError, Exception):
            messages.error(request, "Please enter a valid area (m²).")
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet=interior_walls#section-{section.pk}")

        try:
            moisture = int(moisture_raw) if moisture_raw else 0
            moisture = max(0, min(moisture, 100))
        except ValueError:
            moisture = 0

        # ── Wipe existing line items for this section ───────────────────────
        # Preserve existing per-row values (area, etc.) so they are not
        # overwritten by the section reference area when the incoming
        # per-row inputs are left blank. Fetch these before deleting rows.
        # Collect previous per-row line PKs from paint/primer/waterproof rows
        prev_line_pks = []
        prev_line_pks.extend(POST.getlist("paint_row_line_pk"))
        prev_line_pks.extend(POST.getlist("primer_row_line_pk"))
        prev_line_pks.extend(POST.getlist("waterproof_row_line_pk"))
        prev_areas = {}
        try:
            pks = list({int(p) for p in prev_line_pks if p})
            if pks:
                for pli in section.line_items.filter(pk__in=pks):
                    prev_areas[str(pli.pk)] = pli.area_sqm
        except Exception:
            prev_areas = {}

        section.line_items.all().delete()
        # Mark section as configured
        section.is_placeholder = False
        section.save(update_fields=["is_placeholder"])

        # ── 1. NOTE item: wall summary metadata ─────────────────────────────
        wall_type_label = dict(WALL_TYPES).get(wall_type, wall_type)
        cond_labels = [dict(SURFACE_CONDITIONS).get(c, c) for c in surface_conds]

        # Sanitize any legacy section-level finishes (may be empty). Finish
        # metadata is now owned by individual paint rows but keep the
        # labels for logging/backwards-compatibility.
        valid_finishes = {k for k, _ in FINISHES}
        finishes = [f for f in finishes if f in valid_finishes]
        finish_labels = [dict(FINISHES).get(f, f) for f in finishes]

        # Create a NOTE line for section summary — do not store finishes here;
        # each PAINT QuotationLineItem will own its own finish metadata.
        QuotationLineItem.objects.create(
            quotation   = quotation,
            section     = section,
            item_type   = QuotationLineItem.ItemType.NOTE,
            description = (
                f"Interior Walls — {wall_type_label} | "
                f"Area: {area_sqm or 'TBC'} m²"
            ),
            area_sqm  = area_sqm,
            metadata  = {
                "wall_type":         wall_type,
                "wall_type_label":   wall_type_label,
                "surface_conditions": surface_conds,
                "surface_cond_labels": cond_labels,
                "moisture_level":    moisture,
                "notes":             notes,
            },
        )

        # ── 2. WATERPROOFING items ───────────────────────────────────────────
        wp_row_keys = POST.getlist("waterproof_row_key")
        wp_row_areas = POST.getlist("waterproof_row_area_sqm")
        wp_row_coats = POST.getlist("waterproof_row_coats")
        wp_row_line_pks = POST.getlist("waterproof_row_line_pk")

        # Determine if per-row inputs were provided (prefer them)
        wp_rows = max([len(wp_row_keys), len(wp_row_areas), len(wp_row_coats), len(wp_row_line_pks), 0])
        wp_labels = dict(WATERPROOFING_OPTIONS)

        # Per-row waterproofing preferred; fallback to legacy checkbox behaviour
        from paints.models import Paint as _Paint
        if wp_rows == 0 or all(not k.strip() for k in wp_row_keys):
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
        else:
            for i in range(wp_rows):
                key = (wp_row_keys[i] if i < len(wp_row_keys) else "").strip()
                if not key:
                    continue
                area_raw = (wp_row_areas[i] if i < len(wp_row_areas) else "").strip()
                coats_raw = (wp_row_coats[i] if i < len(wp_row_coats) else "1").strip()
                line_pk = (wp_row_line_pks[i] if i < len(wp_row_line_pks) else "").strip()

                try:
                    coats = int(coats_raw or "1")
                    coats = max(1, min(coats, 2))
                except ValueError:
                    coats = 1

                try:
                    if area_raw:
                        row_area = Decimal(area_raw)
                    elif line_pk and str(line_pk) in prev_areas and prev_areas.get(str(line_pk)) is not None:
                        row_area = prev_areas.get(str(line_pk))
                    else:
                        row_area = area_sqm
                    if row_area is not None and row_area < 0:
                        row_area = None
                except Exception:
                    row_area = None

                wp_label = wp_labels.get(key, key)
                matched = _find_catalogue_paint_by_label(wp_label, Paint.Category.WATERPROOFING)
                price_excl = matched.price_excl_vat if matched else Decimal("0")
                price_incl = matched.price_incl_vat if matched else Decimal("0")

                li = QuotationLineItem.objects.create(
                    quotation   = quotation,
                    section     = section,
                    item_type   = QuotationLineItem.ItemType.WATERPROOFING,
                    description = wp_label,
                    paint       = matched,
                    coats       = coats,
                    area_sqm    = row_area,
                    price_excl_vat = price_excl,
                    price_incl_vat = price_incl,
                    metadata    = {"key": key, "paint_matched": matched is not None},
                )

                try:
                    apply_paint_pricing_to_line_item(li)
                except Exception:
                    meta = dict(li.metadata or {})
                    meta.update({"pricing_status": "pending", "pricing_pending_reason": "pricing_exception"})
                    li.metadata = meta
                    li.save(update_fields=["metadata"])

        # ── 3. PRIMER items ─────────────────────────────────────────────────
        pr_row_keys = POST.getlist("primer_row_key")
        pr_row_areas = POST.getlist("primer_row_area_sqm")
        pr_row_coats = POST.getlist("primer_row_coats")
        pr_row_line_pks = POST.getlist("primer_row_line_pk")

        pr_rows = max([len(pr_row_keys), len(pr_row_areas), len(pr_row_coats), len(pr_row_line_pks), 0])
        primer_labels = dict(PRIMER_OPTIONS)

        # Per-row primer preferred; fallback to legacy checkbox behaviour
        from paints.models import Paint as _Paint
        if pr_rows == 0 or all(not k.strip() for k in pr_row_keys):
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
        else:
            for i in range(pr_rows):
                key = (pr_row_keys[i] if i < len(pr_row_keys) else "").strip()
                if not key:
                    continue
                area_raw = (pr_row_areas[i] if i < len(pr_row_areas) else "").strip()
                coats_raw = (pr_row_coats[i] if i < len(pr_row_coats) else "1").strip()
                line_pk = (pr_row_line_pks[i] if i < len(pr_row_line_pks) else "").strip()

                try:
                    coats = int(coats_raw or "1")
                    coats = max(1, min(coats, 2))
                except ValueError:
                    coats = 1

                try:
                    if area_raw:
                        row_area = Decimal(area_raw)
                    elif line_pk and str(line_pk) in prev_areas and prev_areas.get(str(line_pk)) is not None:
                        row_area = prev_areas.get(str(line_pk))
                    else:
                        row_area = area_sqm
                    if row_area is not None and row_area < 0:
                        row_area = None
                except Exception:
                    row_area = None

                pr_label = primer_labels.get(key, key)
                matched = _find_catalogue_paint_by_label(pr_label, Paint.Category.PRIMER)
                price_excl = matched.price_excl_vat if matched else Decimal("0")
                price_incl = matched.price_incl_vat if matched else Decimal("0")

                li = QuotationLineItem.objects.create(
                    quotation   = quotation,
                    section     = section,
                    item_type   = QuotationLineItem.ItemType.PRIMER,
                    description = pr_label,
                    paint       = matched,
                    coats       = coats,
                    area_sqm    = row_area,
                    price_excl_vat = price_excl,
                    price_incl_vat = price_incl,
                    metadata    = {"key": key, "paint_matched": matched is not None},
                )

                try:
                    apply_paint_pricing_to_line_item(li)
                except Exception:
                    meta = dict(li.metadata or {})
                    meta.update({"pricing_status": "pending", "pricing_pending_reason": "pricing_exception"})
                    li.metadata = meta
                    li.save(update_fields=["metadata"])

        # ── 4. PREP_WORK items ───────────────────────────────────────────────
        prep_labels = dict(OTHER_PREP_OPTIONS)
        # Mapping of prep option keys to Paint.Category values
        prep_key_to_category = {
            "filling": Paint.Category.CRACKS,
            "mould_treatment": Paint.Category.MOULD,
            "efflor_removal": Paint.Category.EFFLORESCENCE,
            "cleaning": Paint.Category.CLEANING,
            "sanding": Paint.Category.SANDING,
            "remove_paint": Paint.Category.OLD_PAINT_REMOVAL,
        }

        for prep_key in POST.getlist("prep_work"):
            if prep_key not in prep_labels:
                continue
            prep_label = prep_labels[prep_key]
            category = prep_key_to_category.get(prep_key)
            matched = _find_catalogue_paint_by_label(prep_label, category) if category else None

            # Default metadata for pack/per-metre items when not provided by UI
            meta = {"key": prep_key, "paint_matched": matched is not None}
            if matched and matched.pricing_method == Paint.PricingMethod.FIXED_PACK:
                # Default to one package when user doesn't specify count in the UI
                meta["package_count"] = 1
            if matched and matched.pricing_method == Paint.PricingMethod.PER_METRE:
                # Default to one metre/roll when user doesn't specify count in the UI
                meta["roll_count"] = 1

            price_excl = matched.price_excl_vat if matched else Decimal("0")
            price_incl = matched.price_incl_vat if matched else Decimal("0")

            li = QuotationLineItem.objects.create(
                quotation   = quotation,
                section     = section,
                item_type   = QuotationLineItem.ItemType.PREP_WORK,
                description = prep_label,
                paint       = matched,
                price_excl_vat = price_excl,
                price_incl_vat = price_incl,
                metadata    = meta,
            )

            try:
                apply_paint_pricing_to_line_item(li)
            except Exception:
                meta = dict(li.metadata or {})
                meta.update({"pricing_status": "pending", "pricing_pending_reason": "pricing_exception"})
                li.metadata = meta
                li.save(update_fields=["metadata"])

        # ── 5. PAINT items ───────────────────────────────────────────────────
        # Prefer per-row inputs named paint_row_finish, paint_row_paint_pk,
        # paint_row_area_sqm, paint_row_coats, paint_row_base. If none are
        # provided, fall back to legacy group-based inputs to preserve
        # backward compatibility.
        row_finishes = POST.getlist("paint_row_finish")
        row_paint_pks = POST.getlist("paint_row_paint_pk")
        row_areas = POST.getlist("paint_row_area_sqm")
        row_coats = POST.getlist("paint_row_coats")
        row_bases = POST.getlist("paint_row_base")
        row_line_pks = POST.getlist("paint_row_line_pk")

        rows = max([len(row_finishes), len(row_paint_pks), len(row_areas), len(row_coats), len(row_bases), 0])

        # Per-row handling only — legacy paint-group inputs removed.
        from paints.models import Paint as _Paint
        for i in range(rows):
                finish = (row_finishes[i] if i < len(row_finishes) else "")
                if not finish:
                    continue
                paint_pk = (row_paint_pks[i] if i < len(row_paint_pks) else "")
                area_raw = (row_areas[i] if i < len(row_areas) else "").strip()
                coats_raw = (row_coats[i] if i < len(row_coats) else "1").strip()
                # Do not default per-row base to WHITE; treat empty as None
                base_raw = (row_bases[i] if i < len(row_bases) else "").strip()
                base_val = base_raw or None

                try:
                    coats = int(coats_raw or "1")
                    coats = max(1, min(coats, 2))
                except ValueError:
                    coats = 1

                try:
                    line_pk = (row_line_pks[i] if i < len(row_line_pks) else "").strip()
                    if area_raw:
                        row_area = Decimal(area_raw)
                    elif line_pk and str(line_pk) in prev_areas and prev_areas.get(str(line_pk)) is not None:
                        row_area = prev_areas.get(str(line_pk))
                    else:
                        row_area = area_sqm
                    if row_area is not None and row_area < 0:
                        row_area = None
                except Exception:
                    row_area = None

                matched_paint = None
                if paint_pk:
                    try:
                        matched_paint = _Paint.objects.filter(pk=int(paint_pk), is_active=True).first()
                    except Exception:
                        matched_paint = None

                paint_group_key = None
                base_label = ""
                description = "Paint"

                if matched_paint is None:
                    groups = get_paint_groups_for_finishes([finish])
                    for pg in groups:
                        candidate = _try_match_paint(pg.paint_name, base_val) if base_val else None
                        if candidate:
                            matched_paint = candidate
                            paint_group_key = pg.key
                            base_label = dict(pg.bases).get(base_val, base_val) if pg.bases else ""
                            description = pg.label
                            if base_label:
                                description += f" — {base_label}"
                            break
                else:
                    description = matched_paint.name
                    base_label = getattr(matched_paint, 'base_type', '') or ''

                price_excl = matched_paint.price_excl_vat if matched_paint else Decimal("0")
                price_incl = matched_paint.price_incl_vat if matched_paint else Decimal("0")

                li = QuotationLineItem.objects.create(
                    quotation      = quotation,
                    section        = section,
                    item_type      = QuotationLineItem.ItemType.PAINT,
                    description    = description,
                    paint          = matched_paint,
                    coats          = coats,
                    area_sqm       = row_area,
                    price_excl_vat = price_excl,
                    price_incl_vat = price_incl,
                    metadata       = {
                        "finish":       finish,
                        "paint_group":  paint_group_key,
                        "paint_name":   matched_paint.name if matched_paint else None,
                        "base":         base_val,
                        "base_label":   base_label,
                        "paint_matched": matched_paint is not None,
                    },
                )

                try:
                    apply_paint_pricing_to_line_item(li)
                except Exception:
                    meta = dict(li.metadata or {})
                    meta.update({"pricing_status": "pending", "pricing_pending_reason": "pricing_exception"})
                    li.metadata = meta
                    li.save(update_fields=["metadata"])

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
        # Recalculate totals after saving interior walls
        try:
            recalculate_quotation_totals(quotation)
        except Exception:
            pass

        # Handle optional section image uploads (single-file posts or multi-file)
        MAX_IMAGE_BYTES = 4 * 1024 * 1024
        try:
            files = request.FILES.getlist('section_images') if getattr(request, 'FILES', None) else []
        except Exception:
            files = []

        if files:
            try:
                existing = section.images.count()
                for f in files:
                    if existing >= 3:
                        break
                    ctype = getattr(f, 'content_type', '')
                    if not ctype or not ctype.startswith('image/'):
                        continue
                    if hasattr(f, 'size') and f.size and f.size > MAX_IMAGE_BYTES:
                        continue
                    QuotationSectionImage.objects.create(section=section, image=f, uploaded_by=request.user)
                    existing += 1
            except Exception:
                # Swallow — image issues should not prevent the section save
                pass

        return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet=interior_walls#section-{section.pk}")


# ---------------------------------------------------------------------------
# Generic Interior Section – save handler
# ---------------------------------------------------------------------------

class GenericSectionSaveView(QuotationAccessMixin, View):
    """
    POST-only view that saves any supported generic section
    (all interior non-walls sections + all supported exterior sections).

    Deletes existing line items for the section and recreates them from POST
    data.  The InteriorSectionConfig drives validation and labelling so there
    is no per-section branching here.
    """

    _GENERIC_KEYS = frozenset(ALL_GENERIC_SECTION_CONFIGS.keys())

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
        cfg       = ALL_GENERIC_SECTION_CONFIGS.get(section.subsection_key)

        if not cfg:
            messages.error(request, "Unknown section configuration.")
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}#section-{section.pk}")

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
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}#section-{section.pk}")

        if not finishes:
            messages.error(request, "Please select at least one finish.")
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}#section-{section.pk}")

        area_sqm_raw = POST.get("area_sqm", "").strip()
        try:
            area_sqm = Decimal(area_sqm_raw) if area_sqm_raw else None
            if area_sqm is not None and area_sqm < 0:
                raise ValueError
        except (ValueError, Exception):
            messages.error(request, "Please enter a valid area (m\u00b2).")
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}#section-{section.pk}")

        moisture_raw = POST.get("moisture_level", "").strip()
        try:
            moisture = int(moisture_raw) if moisture_raw else 0
            moisture = max(0, min(moisture, 100))
        except ValueError:
            moisture = 0

        notes = POST.get("notes", "").strip()

        # ── Wipe and rebuild line items (atomic + lock) ─────────────────────
        # Preserve existing per-row values (area, etc.) before deletion so
        # blank per-row inputs do not overwrite previously-saved per-row areas.
        # Collect previous per-row line PKs from paint/primer/waterproof rows
        prev_line_pks = []
        prev_line_pks.extend(POST.getlist("paint_row_line_pk"))
        prev_line_pks.extend(POST.getlist("primer_row_line_pk"))
        prev_line_pks.extend(POST.getlist("waterproof_row_line_pk"))
        prev_areas = {}
        # Ensure logging variables exist even if the atomic block fails
        type_labels = []
        finish_labels = []
        cond_labels = []
        try:
            with transaction.atomic():
                # Acquire DB lock on the section row
                section = QuotationSection.objects.select_for_update().get(pk=section.pk)
                pks = list({int(p) for p in prev_line_pks if p})
                if pks:
                    for pli in section.line_items.filter(pk__in=pks):
                        prev_areas[str(pli.pk)] = pli.area_sqm

                section.line_items.all().delete()
                section.is_placeholder = False
                section.save(update_fields=["is_placeholder"])

                type_labels   = [dict(cfg.types).get(t, t)                  for t in selected_types]
                finish_labels = [dict(cfg.finishes).get(f, f)              for f in finishes]
                cond_labels   = [dict(cfg.surface_conditions).get(c, c)    for c in surface_conds]

                # ── 1. NOTE (section summary metadata) ──────────────────────────────
                # NOTE: Do not store finishes at section level. Each paint row will
                # include its own finish metadata. The NOTE remains for general notes.
                QuotationLineItem.objects.create(
                    quotation   = quotation,
                    section     = section,
                    item_type   = QuotationLineItem.ItemType.NOTE,
                    description = (
                        f"{cfg.display_name} \u2014 {', '.join(type_labels)} | "
                        f"Area: {area_sqm or 'TBC'} m\u00b2"
                    ),
                    area_sqm    = area_sqm,
                    metadata    = {
                        "section_key":         cfg.key,
                        "section_name":        cfg.display_name,
                        "substrate_type":      cfg.substrate_type,
                        "types":               selected_types,
                        "type_labels":         type_labels,
                        "surface_conditions":  surface_conds,
                        "surface_cond_labels": cond_labels,
                        "moisture_level":      moisture,
                        "area_sqm":            str(area_sqm) if area_sqm else None,
                        "notes":               notes,
                    },
                )

                # ── 2. WATERPROOFING items ───────────────────────────────────────────
                wp_row_keys = POST.getlist("waterproof_row_key")
                wp_row_areas = POST.getlist("waterproof_row_area_sqm")
                wp_row_coats = POST.getlist("waterproof_row_coats")
                wp_row_line_pks = POST.getlist("waterproof_row_line_pk")

                wp_rows = max([len(wp_row_keys), len(wp_row_areas), len(wp_row_coats), len(wp_row_line_pks), 0])
                wp_labels = dict(WATERPROOFING_OPTIONS)

                if wp_rows == 0 or all(not k.strip() for k in wp_row_keys):
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
                else:
                    for i in range(wp_rows):
                        key = (wp_row_keys[i] if i < len(wp_row_keys) else "").strip()
                        if not key:
                            continue
                        area_raw = (wp_row_areas[i] if i < len(wp_row_areas) else "").strip()
                        coats_raw = (wp_row_coats[i] if i < len(wp_row_coats) else "1").strip()
                        line_pk = (wp_row_line_pks[i] if i < len(wp_row_line_pks) else "").strip()

                        try:
                            coats = int(coats_raw or "1")
                            coats = max(1, min(coats, 2))
                        except ValueError:
                            coats = 1

                        try:
                            if area_raw:
                                row_area = Decimal(area_raw)
                            elif line_pk and str(line_pk) in prev_areas and prev_areas.get(str(line_pk)) is not None:
                                row_area = prev_areas.get(str(line_pk))
                            else:
                                row_area = area_sqm
                            if row_area is not None and row_area < 0:
                                row_area = None
                        except Exception:
                            row_area = None

                        wp_label = wp_labels.get(key, key)
                        QuotationLineItem.objects.create(
                            quotation   = quotation,
                            section     = section,
                            item_type   = QuotationLineItem.ItemType.WATERPROOFING,
                            description = wp_label,
                            coats       = coats,
                            area_sqm    = row_area,
                            metadata    = {"key": key},
                        )

                # ── 3. PRIMER items ─────────────────────────────────────────────────
                pr_row_keys = POST.getlist("primer_row_key")
                pr_row_areas = POST.getlist("primer_row_area_sqm")
                pr_row_coats = POST.getlist("primer_row_coats")
                pr_row_line_pks = POST.getlist("primer_row_line_pk")

                pr_rows = max([len(pr_row_keys), len(pr_row_areas), len(pr_row_coats), len(pr_row_line_pks), 0])
                primer_labels = dict(PRIMER_OPTIONS)

                if pr_rows == 0 or all(not k.strip() for k in pr_row_keys):
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
                else:
                    for i in range(pr_rows):
                        key = (pr_row_keys[i] if i < len(pr_row_keys) else "").strip()
                        if not key:
                            continue
                        area_raw = (pr_row_areas[i] if i < len(pr_row_areas) else "").strip()
                        coats_raw = (pr_row_coats[i] if i < len(pr_row_coats) else "1").strip()
                        line_pk = (pr_row_line_pks[i] if i < len(pr_row_line_pks) else "").strip()

                        try:
                            coats = int(coats_raw or "1")
                            coats = max(1, min(coats, 2))
                        except ValueError:
                            coats = 1

                        try:
                            if area_raw:
                                row_area = Decimal(area_raw)
                            elif line_pk and str(line_pk) in prev_areas and prev_areas.get(str(line_pk)) is not None:
                                row_area = prev_areas.get(str(line_pk))
                            else:
                                row_area = area_sqm
                            if row_area is not None and row_area < 0:
                                row_area = None
                        except Exception:
                            row_area = None

                        pr_label = primer_labels.get(key, key)
                        QuotationLineItem.objects.create(
                            quotation   = quotation,
                            section     = section,
                            item_type   = QuotationLineItem.ItemType.PRIMER,
                            description = pr_label,
                            coats       = coats,
                            area_sqm    = row_area,
                            metadata    = {"key": key},
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
                # Per-row inputs preferred; fallback to legacy group inputs when
                # per-row data is not supplied.
                row_finishes = POST.getlist("paint_row_finish")
                row_paint_pks = POST.getlist("paint_row_paint_pk")
                row_areas = POST.getlist("paint_row_area_sqm")
                row_coats = POST.getlist("paint_row_coats")
                row_bases = POST.getlist("paint_row_base")
                row_line_pks = POST.getlist("paint_row_line_pk")

                rows = max([len(row_finishes), len(row_paint_pks), len(row_areas), len(row_coats), len(row_bases), 0])

                # Per-row handling only — legacy paint-group inputs removed.
                from paints.models import Paint as _Paint
                for i in range(rows):
                        finish = (row_finishes[i] if i < len(row_finishes) else "")
                        if not finish:
                            continue
                        paint_pk = (row_paint_pks[i] if i < len(row_paint_pks) else "")
                        area_raw = (row_areas[i] if i < len(row_areas) else "").strip()
                        coats_raw = (row_coats[i] if i < len(row_coats) else "1").strip()
                        # Do not default per-row base to WHITE; treat empty as None
                        base_raw = (row_bases[i] if i < len(row_bases) else "").strip()
                        base_val = base_raw or None

                        try:
                            coats = int(coats_raw or "1")
                            coats = max(1, min(coats, 2))
                        except ValueError:
                            coats = 1

                        try:
                            line_pk = (row_line_pks[i] if i < len(row_line_pks) else "").strip()
                            if area_raw:
                                row_area = Decimal(area_raw)
                            elif line_pk and str(line_pk) in prev_areas and prev_areas.get(str(line_pk)) is not None:
                                row_area = prev_areas.get(str(line_pk))
                            else:
                                row_area = area_sqm
                            if row_area is not None and row_area < 0:
                                row_area = None
                        except Exception:
                            row_area = None

                        matched_paint = None
                        if paint_pk:
                            try:
                                matched_paint = _Paint.objects.filter(pk=int(paint_pk), is_active=True).first()
                            except Exception:
                                matched_paint = None

                        paint_group_key = None
                        base_label = ""
                        description = cfg.display_name

                        if matched_paint is None:
                            groups = get_paint_groups_for_finishes([finish])
                            for pg in groups:
                                candidate = _try_match_paint(pg.paint_name, base_val) if base_val else None
                                if candidate:
                                    matched_paint = candidate
                                    paint_group_key = pg.key
                                    base_label = dict(pg.bases).get(base_val, base_val) if pg.bases else ""
                                    description = pg.label
                                    if base_label:
                                        description += f" \u2014 {base_label}"
                                    break
                        else:
                            description = matched_paint.name
                            base_label = getattr(matched_paint, 'base_type', '') or ''

                        price_excl = matched_paint.price_excl_vat if matched_paint else Decimal("0")
                        price_incl = matched_paint.price_incl_vat if matched_paint else Decimal("0")

                        li = QuotationLineItem.objects.create(
                            quotation      = quotation,
                            section        = section,
                            item_type      = QuotationLineItem.ItemType.PAINT,
                            description    = description,
                            paint          = matched_paint,
                            coats          = coats,
                            area_sqm       = row_area,
                            price_excl_vat = price_excl,
                            price_incl_vat = price_incl,
                            metadata       = {
                                "finish":       finish,
                                "paint_group":  paint_group_key,
                                "paint_name":   matched_paint.name if matched_paint else None,
                                "base":         base_val,
                                "base_label":   base_label,
                                "paint_matched": matched_paint is not None,
                            },
                        )

                        try:
                            apply_paint_pricing_to_line_item(li)
                        except Exception:
                            meta = dict(li.metadata or {})
                            meta.update({"pricing_status": "pending", "pricing_pending_reason": "pricing_exception"})
                            li.metadata = meta
                            li.save(update_fields=["metadata"])
        except Exception:
            prev_areas = {}

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
                "quotation_id":   quotation.pk,
                "section_id":     section.pk,
                "section_key":    cfg.key,
                "section_name":   cfg.display_name,
                "substrate_type": cfg.substrate_type,
                "types":          selected_types,
                "finishes":       finishes,
                "area_sqm":       str(area_sqm) if area_sqm else None,
            },
            request = request,
        )

        messages.success(request, f"{cfg.display_name} saved successfully.")
        # Recalculate quotation totals after section saved
        try:
            recalculate_quotation_totals(quotation)
        except Exception:
            # Fail silently — totals can be recalculated later
            pass
        # Preserve active leaflet state: return to the same leaflet
        return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}#section-{section.pk}")


class CreateSelectionView(QuotationAccessMixin, View):
    """POST-only endpoint to create an additional repeated section for a category."""

    def post(self, request, pk, subsection_key, *args, **kwargs):
        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        try:
            new_section = create_repeatable_section(quotation=quotation, subsection_key=subsection_key)
        except ValueError:
            messages.error(request, "Invalid or unselected category.")
            # Redirect back to builder with the requested category active
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={subsection_key}")
        except IntegrityError:
            messages.error(request, "Unable to create section. Try again.")
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={subsection_key}")

        messages.success(request, "New section added.")
        # Keep the leaflet for the created section active
        return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': quotation.pk})}?leaflet={new_section.subsection_key}#section-{new_section.pk}")


class DeleteSelectionView(QuotationAccessMixin, View):
    """POST-only endpoint to delete a single repeated section and renumber siblings."""

    def post(self, request, pk, section_pk, *args, **kwargs):
        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        # Resolve the exact section by pk and quotation
        section = get_object_or_404(QuotationSection, pk=section_pk, quotation=quotation)
        try:
            delete_repeatable_section(quotation=quotation, section_pk=section_pk)
        except QuotationSection.DoesNotExist:
            messages.error(request, "Section not found.")
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}")
        except IntegrityError:
            messages.error(request, "Unable to delete section. Try again.")
            return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}")

        messages.success(request, "Section removed.")
        # Redirect back to builder with the deleted section's category active
        return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}")


class SectionImageDeleteView(QuotationAccessMixin, View):
    """Delete a section image (DB record + storage file)."""

    def post(self, request, pk, section_pk, image_pk, *args, **kwargs):
        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        section = get_object_or_404(QuotationSection, pk=section_pk, quotation=quotation)
        img = get_object_or_404(QuotationSectionImage, pk=image_pk, section=section)

        try:
            img.delete()
            messages.success(request, "Image deleted.")
        except Exception:
            messages.error(request, "Could not delete image.")

        return redirect(f"{reverse('quotation:quotation_builder', kwargs={'pk': pk})}?leaflet={section.subsection_key}#section-{section.pk}")


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
        track_recent_quotation(request.session, quotation.pk)

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
            # Include section images (thumbnail URLs) for the review page
            images = [img.image.url for img in sec.images.order_by("sort_order")]
            section_data.append({
                "section":    sec,
                "configured": len(items) > 0,
                "items":      enriched_items,
                "images":     images,
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

        # Most recent successful PDF for the "last generated" panel
        from .pdf_templates import get_template_display_name
        last_pdf_export = (
            quotation.pdf_exports
            .filter(status=QuotationPdfExport.Status.GENERATED)
            .select_related("generated_by")
            .order_by("-created_at")
            .first()
        )
        if last_pdf_export:
            last_pdf_export.template_name = get_template_display_name(last_pdf_export.template_key)

        return render(request, self.template_name, {
            "quotation":         quotation,
            "section_data":      section_data,
            "subtotal":          subtotal,
            "is_admin":          self._is_admin(),
            "quotation_summary": get_quotation_summary(quotation),
            "last_pdf_export":   last_pdf_export,
            "preflight":         get_quotation_preflight(quotation),
        })


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

class QuotationDetailView(QuotationAccessMixin, DetailView):
    template_name       = "quotation/quotation_detail.html"
    context_object_name = "quotation"

    def get_object(self, queryset=None):
        obj = get_object_or_404(self.get_base_qs(), pk=self.kwargs["pk"])
        track_recent_quotation(self.request.session, obj.pk)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_admin"] = self._is_admin()
        ctx["sections"] = self.object.sections.order_by("substrate_type", "sort_order")
        from .pdf_templates import get_template_display_name
        exports = list(
            self.object.pdf_exports
            .select_related("generated_by")
            .order_by("-created_at")[:10]
        )
        for exp in exports:
            exp.template_name = get_template_display_name(exp.template_key)
        ctx["pdf_exports"] = exports
        return ctx


# ---------------------------------------------------------------------------
# PDF Template Selection
# ---------------------------------------------------------------------------

class QuotationPdfTemplateSelectView(QuotationAccessMixin, View):
    """
    GET  /quotations/<pk>/pdf/
    Show a card for each available PDF template and let the user choose one.
    """

    template_name = "quotation/pdf_template_select.html"

    def get(self, request, pk):
        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        track_recent_quotation(request.session, quotation.pk)
        from .pdf_templates import PDF_TEMPLATES, get_template_display_name
        templates = [
            {"key": k, **v}
            for k, v in PDF_TEMPLATES.items()
        ]
        recent_exports = list(
            quotation.pdf_exports
            .select_related("generated_by")
            .order_by("-created_at")[:5]
        )
        for exp in recent_exports:
            exp.template_name = get_template_display_name(exp.template_key)
        summary = get_quotation_summary(quotation)
        preflight = get_quotation_preflight(quotation)
        preferred_key = getattr(
            getattr(request.user, "app_settings", None),
            "preferred_pdf_template",
            None,
        )
        return render(request, self.template_name, {
            "quotation":         quotation,
            "pdf_templates":     templates,
            "recent_exports":    recent_exports,
            "quotation_summary": summary,
            "preflight":         preflight,
            "preferred_pdf_template_key": preferred_key,
        })


# ---------------------------------------------------------------------------
# PDF Generate
# ---------------------------------------------------------------------------

class QuotationPdfGenerateView(QuotationAccessMixin, View):
    """
    POST /quotations/<pk>/pdf/generate/
    Validates the template_key, calls the PDF service, audits, and redirects.
    """

    def post(self, request, pk):
        from .pdf_service import render_quotation_pdf
        from .pdf_templates import PDF_TEMPLATES

        quotation = get_object_or_404(self.get_base_qs(), pk=pk)
        template_key = request.POST.get("template_key", "").strip()

        # Validate against registry — never accept arbitrary paths
        if template_key not in PDF_TEMPLATES:
            messages.error(request, _("Invalid template selection. Please choose a valid template."))
            return redirect("quotation:pdf_select", pk=pk)

        # Preflight: block only when clearly unsafe (e.g. no sections at all).
        preflight = get_quotation_preflight(quotation)
        if not preflight["can_generate_pdf"]:
            messages.error(
                request,
                _("This quotation isn't ready for a PDF yet. %(summary)s") % {
                    "summary": preflight["summary"]
                },
            )
            return redirect("quotation:pdf_select", pk=pk)

        export = render_quotation_pdf(
            quotation=quotation,
            template_key=template_key,
            generated_by=request.user,
            request=request,
        )

        if export.status == QuotationPdfExport.Status.GENERATED:
            # Optionally remember the chosen template as the user's default.
            try:
                app_settings = getattr(request.user, "app_settings", None)
                if (
                    app_settings
                    and getattr(app_settings, "remember_last_pdf_template", False)
                    and template_key in PDF_TEMPLATES
                    and app_settings.preferred_pdf_template != template_key
                ):
                    app_settings.preferred_pdf_template = template_key
                    app_settings.save(update_fields=["preferred_pdf_template", "updated_at"])
            except Exception:
                pass

            log_action(
                user=request.user,
                action="QUOTATION_PDF_GENERATED",
                module="quotation",
                description=(
                    f"PDF generated for quotation {quotation.reference} "
                    f"using template '{template_key}'."
                ),
                metadata={
                    "quotation_reference": quotation.reference,
                    "quotation_id":        quotation.pk,
                    "template_key":        template_key,
                    "export_id":           export.pk,
                },
                request=request,
            )
            messages.success(
                request,
                _("PDF generated successfully. You can download it below."),
            )
            return redirect("quotation:pdf_download", export_id=export.pk)
        else:
            log_action(
                user=request.user,
                action="QUOTATION_PDF_GENERATION_FAILED",
                module="quotation",
                description=(
                    f"PDF generation failed for {quotation.reference} "
                    f"(template '{template_key}'): {export.error_message[:200]}"
                ),
                metadata={
                    "quotation_reference": quotation.reference,
                    "quotation_id":        quotation.pk,
                    "template_key":        template_key,
                    "export_id":           export.pk,
                },
                request=request,
            )
            messages.error(
                request,
                _("PDF generation failed. Please try again or contact support."),
            )
            return redirect("quotation:pdf_select", pk=pk)


# ---------------------------------------------------------------------------
# PDF Download
# ---------------------------------------------------------------------------

class QuotationPdfDownloadView(QuotationAccessMixin, View):
    """
    GET /quotations/pdf/<export_id>/download/
    Stream the generated PDF to the browser.
    """

    def get(self, request, export_id):
        from django.http import FileResponse, Http404

        # Access-control: admin sees all; rep sees only own exports
        qs = QuotationPdfExport.objects.select_related("quotation", "generated_by")
        if not self._is_admin():
            qs = qs.filter(quotation__created_by=request.user)

        export = get_object_or_404(qs, pk=export_id)

        if export.status != QuotationPdfExport.Status.GENERATED or not export.file:
            messages.error(request, _("This PDF export is not available for download."))
            return redirect("quotation:quotation_detail", pk=export.quotation_id)

        try:
            response = FileResponse(
                export.file.open("rb"),
                content_type="application/pdf",
            )
            safe_name = export.file.name.split("/")[-1]
            response["Content-Disposition"] = (
                f'attachment; filename="{safe_name}"'
            )
            return response
        except (FileNotFoundError, OSError):
            messages.error(request, _("PDF file could not be found. Please regenerate."))
            return redirect("quotation:pdf_select", pk=export.quotation_id)

