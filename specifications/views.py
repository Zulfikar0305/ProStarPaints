import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.generic import View

from quotation.models import Quotation
from quotation.views import QuotationAccessMixin
from specifications.services import ManualSpecificationBuilderService
from specifications.services.export_service import ExportService
from specifications.services.preview_service import PreviewService
from users.mixins import AdminRequiredMixin

from .models import SpecificationTemplate, KnowledgeEntry, KnowledgeCategory, SpecificationRule, KNOWLEDGE_CATEGORIES, SurfaceDefault, ManualSpecificationItem
from .forms import SpecificationTemplateForm, SpecificationRuleForm
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.db.models import Q
from .forms import KnowledgeEntryForm, KnowledgeCategoryForm, SurfaceDefaultForm
from .models import KnowledgeCategory
import logging

logger = logging.getLogger(__name__)


class ClausesIndexView(AdminRequiredMixin, View):
    template_name = "specifications/clauses_index.html"

    def get(self, request):
        clauses = KnowledgeEntry.objects.filter(kind=KnowledgeEntry.KIND_CLAUSE).select_related("category").order_by("sort_order", "title")
        return render(request, self.template_name, {"clauses": clauses})


class ClauseEditView(AdminRequiredMixin, View):
    template_name = "specifications/clause_edit.html"

    def get(self, request, pk):
        obj = get_object_or_404(KnowledgeEntry, pk=pk)
        form = KnowledgeEntryForm(instance=obj)
        return render(request, self.template_name, {"form": form, "obj": obj})

    def post(self, request, pk):
        obj = get_object_or_404(KnowledgeEntry, pk=pk)
        form = KnowledgeEntryForm(request.POST, instance=obj)
        if form.is_valid():
            saved = form.save()
            saved.created_by = saved.created_by or request.user
            saved.save()
            messages.success(request, "Clause saved.")
            return redirect(reverse("specifications:clauses_index"))
        return render(request, self.template_name, {"form": form, "obj": obj})


class ClauseCreateView(AdminRequiredMixin, View):
    template_name = "specifications/clause_edit.html"

    def get(self, request):
        form = KnowledgeEntryForm(initial={"kind": KnowledgeEntry.KIND_CLAUSE})
        return render(request, self.template_name, {"form": form, "obj": None})

    def post(self, request):
        form = KnowledgeEntryForm(request.POST)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.created_by = request.user
            saved.save()
            messages.success(request, "Clause created.")
            return redirect(reverse("specifications:clauses_index"))
        return render(request, self.template_name, {"form": form, "obj": None})


class ClauseDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(KnowledgeEntry, pk=pk)
        obj.delete()
        messages.success(request, "Clause deleted.")
        return redirect(reverse("specifications:clauses_index"))


class CategoriesIndexView(AdminRequiredMixin, View):
    template_name = "specifications/categories_index.html"

    def get(self, request):
        cats = KnowledgeCategory.objects.order_by("name")
        return render(request, self.template_name, {"categories": cats})


class CategoryEditView(AdminRequiredMixin, View):
    template_name = "specifications/category_edit.html"

    def get(self, request, pk):
        obj = get_object_or_404(KnowledgeCategory, pk=pk)
        form = KnowledgeCategoryForm(instance=obj)
        return render(request, self.template_name, {"form": form, "obj": obj})

    def post(self, request, pk):
        obj = get_object_or_404(KnowledgeCategory, pk=pk)
        form = KnowledgeCategoryForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Category saved.")
            return redirect(reverse("specifications:categories_index"))
        return render(request, self.template_name, {"form": form, "obj": obj})


class CategoryCreateView(AdminRequiredMixin, View):
    template_name = "specifications/category_edit.html"

    def get(self, request):
        form = KnowledgeCategoryForm()
        return render(request, self.template_name, {"form": form, "obj": None})

    def post(self, request):
        form = KnowledgeCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Category created.")
            return redirect(reverse("specifications:categories_index"))
        return render(request, self.template_name, {"form": form, "obj": None})


class CategoryDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(KnowledgeCategory, pk=pk)
        obj.delete()
        messages.success(request, "Category deleted.")
        return redirect(reverse("specifications:categories_index"))


class RulesIndexView(AdminRequiredMixin, View):
    template_name = "specifications/rules_index.html"

    def get(self, request):
        rules = SpecificationRule.objects.order_by("priority", "pk")
        return render(request, self.template_name, {"rules": rules})


class RuleCreateView(AdminRequiredMixin, View):
    template_name = "specifications/rule_edit.html"

    def get(self, request):
        form = SpecificationRuleForm()
        return render(request, self.template_name, {"form": form, "obj": None})

    def post(self, request):
        form = SpecificationRuleForm(request.POST)
        if form.is_valid():
            saved = form.save()
            messages.success(request, "Rule created.")
            return redirect(reverse("specifications:rules_index"))
        return render(request, self.template_name, {"form": form, "obj": None})


class RuleEditView(AdminRequiredMixin, View):
    template_name = "specifications/rule_edit.html"

    def get(self, request, pk):
        obj = get_object_or_404(SpecificationRule, pk=pk)
        form = SpecificationRuleForm(instance=obj)
        return render(request, self.template_name, {"form": form, "obj": obj})

    def post(self, request, pk):
        obj = get_object_or_404(SpecificationRule, pk=pk)
        form = SpecificationRuleForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Rule saved.")
            return redirect(reverse("specifications:rules_index"))
        return render(request, self.template_name, {"form": form, "obj": obj})


class RuleDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(SpecificationRule, pk=pk)
        obj.delete()
        messages.success(request, "Rule deleted.")
        return redirect(reverse("specifications:rules_index"))


class RuleMoveView(AdminRequiredMixin, View):
    """Move a rule up or down within its rule_type ordering."""

    def post(self, request, pk, direction):
        obj = get_object_or_404(SpecificationRule, pk=pk)
        if direction not in ("up", "down"):
            return redirect(reverse("specifications:rules_index"))
        if direction == "up":
            other = SpecificationRule.objects.filter(rule_type=obj.rule_type, priority__lt=obj.priority).order_by("-priority").first()
        else:
            other = SpecificationRule.objects.filter(rule_type=obj.rule_type, priority__gt=obj.priority).order_by("priority").first()
        if other:
            obj.priority, other.priority = other.priority, obj.priority
            other.save()
            obj.save()
        return redirect(reverse("specifications:rules_index"))


class BuilderQuotationAccessMixin(QuotationAccessMixin):
    """Access control for quotation-specific manual builder views."""

    def get_quotation(self, request, pk):
        return get_object_or_404(self.get_base_qs(), pk=pk)


class BuilderQuotationView(BuilderQuotationAccessMixin, View):
    template_name = "specifications/builder.html"

    def get(self, request, pk):
        quotation = self.get_quotation(request, pk)
        service = ManualSpecificationBuilderService()
        resolver = service.build_serialisable_automatic_context(quotation)
        manual_overrides = service.manual_overrides_for_quotation(quotation)

        ctx = {
            "quotation": quotation,
            "spec_data_json": json.dumps(resolver),
            "manual_overrides_json": json.dumps(manual_overrides),
            "draft_id": quotation.pk,
            "draft_preview_url": reverse("specifications:builder_quotation_preview", args=[quotation.pk]),
            "pdf_selection_url": reverse("quotation:pdf_select", args=[quotation.pk]),
            "request": request,
        }
        return render(request, self.template_name, ctx)


class BuilderQuotationSaveView(BuilderQuotationAccessMixin, View):
    def post(self, request, pk):
        quotation = self.get_quotation(request, pk)
        service = ManualSpecificationBuilderService()

        try:
            payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        except Exception:
            payload = {}

        if not isinstance(payload, dict):
            return JsonResponse({"error": "Invalid payload"}, status=400)

        section_id = payload.get("section_id")
        if section_id is None:
            section_id = payload.get("section_pk")
        if section_id is None:
            section_id = payload.get("section_key")

        if section_id is not None:
            section = service.resolve_section_for_manual_key(quotation, section_id)
            if section is None:
                return JsonResponse({"error": "Section not found"}, status=404)

            preparation_requirements = str(payload.get("preparation_requirements") or "")
            application_requirements = str(payload.get("application_requirements") or "")
            service.save_manual_item(
                quotation,
                section,
                preparation_requirements=preparation_requirements,
                application_requirements=application_requirements,
                images=[],
                created_by=request.user,
            )
            return JsonResponse({
                "draft_id": quotation.pk,
                "preview_url": reverse("specifications:builder_quotation_preview", args=[quotation.pk]),
                "manual_overrides": service.manual_overrides_for_quotation(quotation),
            })

        manual_overrides = payload.get("manual_overrides") if isinstance(payload.get("manual_overrides"), dict) else {}
        normalized_overrides = service.normalize_manual_overrides(manual_overrides)
        for section_key, item_override in normalized_overrides.items():
            section = service.resolve_section_for_manual_key(quotation, section_key)
            if section is None:
                continue
            service.save_manual_item(
                quotation,
                section,
                preparation_requirements=item_override.get("preparation_requirements", ""),
                application_requirements=item_override.get("application_requirements", ""),
                images=item_override.get("images", []),
                created_by=request.user,
            )

        return JsonResponse({
            "draft_id": quotation.pk,
            "preview_url": reverse("specifications:builder_quotation_preview", args=[quotation.pk]),
            "manual_overrides": service.manual_overrides_for_quotation(quotation),
        })


class BuilderQuotationPreviewView(BuilderQuotationAccessMixin, View):
    def get(self, request, pk):
        quotation = self.get_quotation(request, pk)
        service = ManualSpecificationBuilderService()
        resolver = service.build_serialisable_automatic_context(quotation)
        manual_overrides = service.manual_overrides_for_quotation(quotation)

        from types import SimpleNamespace
        draft = SimpleNamespace(
            quotation=quotation,
            data={
                "resolver": resolver,
                "manual_overrides": manual_overrides,
                "draft_overrides": {"pricing_visible": True, "sections": {}, "report_controls": {}},
                "rendered_html": {},
            },
            created_by=request.user,
        )

        preview_ctx = PreviewService().preview_context_for_draft(draft)
        html = render_to_string("quotation/pdf/manual_specification.html", preview_ctx)
        return HttpResponse(html)


class BuilderQuotationExportView(BuilderQuotationAccessMixin, View):
    def get(self, request, pk):
        quotation = self.get_quotation(request, pk)
        service = ManualSpecificationBuilderService()
        resolver = service.build_serialisable_automatic_context(quotation)
        manual_overrides = service.manual_overrides_for_quotation(quotation)

        from types import SimpleNamespace
        draft = SimpleNamespace(
            quotation=quotation,
            data={
                "resolver": resolver,
                "manual_overrides": manual_overrides,
                "draft_overrides": {"pricing_visible": True, "sections": {}, "report_controls": {}},
                "rendered_html": {},
            },
            created_by=request.user,
        )

        export = ExportService().export_pdf_from_draft(draft, "manual_specification", request.user, request=request)
        if export and export.pk and export.status == export.Status.GENERATED:
            return redirect("quotation:pdf_download_direct", export_id=export.pk)

        messages.error(request, "Manual specification PDF could not be generated.")
        return redirect("quotation:pdf_select", pk=quotation.pk)


class LandingView(AdminRequiredMixin, View):
    template_name = "specifications/landing.html"

    def get(self, request):
        # Only basic context for now — models exist but no heavy functionality
        template_count = SpecificationTemplate.objects.count()
        entry_count = KnowledgeEntry.objects.count()
        return render(request, self.template_name, {
            "template_count": template_count,
            "entry_count": entry_count,
        })


class TemplatesIndexView(AdminRequiredMixin, View):
    template_name = "specifications/templates_index.html"

    def get(self, request):
        # Bootstrap: ensure a sensible default exists for automatic_specification
        DEFAULT_KEY = "automatic_specification"
        try:
            if not SpecificationTemplate.objects.filter(key=DEFAULT_KEY).exists():
                SpecificationTemplate.objects.create(
                    name="Professional Specification",
                    key=DEFAULT_KEY,
                    content="Professional specification template. Edit to customise.",
                    config={},
                    is_active=True,
                    created_by=request.user,
                )
        except Exception:
            # Silently continue if bootstrap cannot run (e.g. during migrations)
            pass

        templates_qs = SpecificationTemplate.objects.all().order_by("name")
        templates = []
        for t in templates_qs:
            can_deactivate = False
            if t.is_active:
                # Allow deactivation only when another active template exists
                other_active = SpecificationTemplate.objects.filter(key=t.key, is_active=True).exclude(pk=t.pk).exists()
                can_deactivate = bool(other_active)
            templates.append({"obj": t, "can_deactivate": can_deactivate})

        return render(request, self.template_name, {"templates": templates})


class TemplateEditView(AdminRequiredMixin, View):
    template_name = "specifications/template_edit.html"

    def get(self, request, pk):
        obj = get_object_or_404(SpecificationTemplate, pk=pk)
        form = SpecificationTemplateForm(instance=obj)
        # Prevent changing the key for existing templates
        try:
            form.fields["key"].disabled = True
        except Exception:
            pass
        return render(request, self.template_name, {"form": form, "obj": obj})

    def post(self, request, pk):
        obj = get_object_or_404(SpecificationTemplate, pk=pk)
        form = SpecificationTemplateForm(request.POST, instance=obj)
        # Keep key read-only for existing templates
        try:
            form.fields["key"].disabled = True
        except Exception:
            pass
        if form.is_valid():
            saved = form.save()
            saved.created_by = saved.created_by or request.user
            saved.save()
            messages.success(request, "Template saved.")
            return redirect(reverse("specifications:templates_index"))
        return render(request, self.template_name, {"form": form, "obj": obj})


class TemplateDuplicateView(AdminRequiredMixin, View):
    """Create a non-active copy of a template and open it for editing."""

    def post(self, request, pk):
        orig = get_object_or_404(SpecificationTemplate, pk=pk)
        base_key = f"{orig.key}-copy"
        new_key = base_key
        i = 1
        while SpecificationTemplate.objects.filter(key=new_key).exists():
            new_key = f"{base_key}-{i}"
            i += 1
        new_name = f"{orig.name} (copy)"
        new = SpecificationTemplate.objects.create(
            name=new_name,
            key=new_key,
            content=orig.content,
            config=orig.config or {},
            is_active=False,
            created_by=request.user,
        )
        messages.success(request, "Template duplicated.")
        return redirect(reverse("specifications:template_edit", args=[new.pk]))


class TemplateDeactivateView(AdminRequiredMixin, View):
    """Deactivate a template unless it is the only active template for its key."""

    def post(self, request, pk):
        obj = get_object_or_404(SpecificationTemplate, pk=pk)
        if obj.is_active:
            active_count = SpecificationTemplate.objects.filter(key=obj.key, is_active=True).count()
            if active_count <= 1:
                messages.error(request, "Cannot deactivate the only active template for this key.")
                return redirect(reverse("specifications:templates_index"))
            obj.is_active = False
            obj.save()
            messages.success(request, "Template deactivated.")
        return redirect(reverse("specifications:templates_index"))


class AutomaticSpecificationView(AdminRequiredMixin, View):
    """Admin-facing page to configure the Automatic Specification defaults.

    This view focuses on section visibility, heading overrides and the
    canonical report-control flags for the active `automatic_specification`
    template key.
    """

    template_name = "specifications/automatic_spec.html"
    DEFAULT_KEY = "automatic_specification"

    def get(self, request):
        # Ensure an active template exists for the automatic specification
        try:
            tmpl = SpecificationTemplate.objects.filter(key=self.DEFAULT_KEY, is_active=True).first()
            if not tmpl:
                tmpl = SpecificationTemplate.objects.create(
                    name="Professional Specification",
                    key=self.DEFAULT_KEY,
                    content="Professional specification template. Edit section defaults below.",
                    config={},
                    is_active=True,
                    created_by=request.user,
                )
        except Exception:
            tmpl = SpecificationTemplate.objects.filter(key=self.DEFAULT_KEY).first()

        form = SpecificationTemplateForm(instance=tmpl)
        return render(
            request,
            self.template_name,
            {
                "template": tmpl,
                "sections_ui": form.sections_ui,
                "report_controls_ui": getattr(form, "report_controls_ui", []),
            },
        )

    def post(self, request):
        tmpl = SpecificationTemplate.objects.filter(key=self.DEFAULT_KEY, is_active=True).first()
        if not tmpl:
            messages.error(request, "Automatic Specification template not found.")
            return redirect(reverse("specifications:landing"))

        action = request.POST.get("action")
        if action == "restore":
            cfg = dict(tmpl.config or {})
            cfg.pop("sections", None)
            cfg.pop("report_controls", None)
            tmpl.config = cfg
            tmpl.save()
            messages.success(request, "Automatic Specification defaults restored.")
            return redirect(reverse("specifications:automatic_spec"))

        form = SpecificationTemplateForm(request.POST, instance=tmpl)
        if form.is_valid():
            form.save()
            messages.success(request, "Automatic Specification defaults updated.")
            return redirect(reverse("specifications:automatic_spec"))

        messages.error(request, "Failed to save automatic specification defaults.")
        return redirect(reverse("specifications:automatic_spec"))


class SurfaceDefaultsIndexView(AdminRequiredMixin, View):
    template_name = "specifications/knowledge_index.html"

    def get(self, request):
        q = request.GET.get("q", "").strip()
        only_active = request.GET.get("active")

        qs = SurfaceDefault.objects.all()
        if q:
            qs = qs.filter(
                Q(main_section__icontains=q)
                | Q(subsection__icontains=q)
                | Q(surface__icontains=q)
                | Q(preparation_requirements__icontains=q)
                | Q(surface_rules__icontains=q)
            )
        if only_active in ("1", "true", "on"):
            qs = qs.filter(is_active=True)

        qs = qs.order_by("main_section", "subsection", "surface")
        return render(request, self.template_name, {"entries": qs, "q": q, "only_active": only_active})


class SurfaceDefaultCreateView(AdminRequiredMixin, View):
    template_name = "specifications/surface_default_edit.html"

    def get(self, request):
        form = SurfaceDefaultForm()
        return render(request, self.template_name, {"form": form, "obj": None})

    def post(self, request):
        form = SurfaceDefaultForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, "Surface default created.")
            return redirect(reverse("specifications:surface_defaults_index"))
        return render(request, self.template_name, {"form": form, "obj": None})


class SurfaceDefaultEditView(AdminRequiredMixin, View):
    template_name = "specifications/surface_default_edit.html"

    def get(self, request, pk):
        obj = get_object_or_404(SurfaceDefault, pk=pk)
        form = SurfaceDefaultForm(instance=obj)
        return render(request, self.template_name, {"form": form, "obj": obj})

    def post(self, request, pk):
        obj = get_object_or_404(SurfaceDefault, pk=pk)
        form = SurfaceDefaultForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Surface default saved.")
            return redirect(reverse("specifications:surface_defaults_index"))
        return render(request, self.template_name, {"form": form, "obj": obj})


class SurfaceDefaultDeactivateView(AdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(SurfaceDefault, pk=pk)
        obj.is_active = False
        obj.save()
        messages.success(request, "Surface default deactivated.")
        return redirect(reverse("specifications:surface_defaults_index"))


class KnowledgeIndexView(SurfaceDefaultsIndexView):
    pass


class KnowledgeCreateView(SurfaceDefaultCreateView):
    pass


class KnowledgeEditView(SurfaceDefaultEditView):
    pass


class KnowledgeDeactivateView(SurfaceDefaultDeactivateView):
    pass


