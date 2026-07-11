from django.shortcuts import render
from django.views.generic import View

from users.mixins import AdminRequiredMixin

from .models import SpecificationTemplate, KnowledgeEntry
from .forms import SpecificationTemplateForm
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from .forms import KnowledgeEntryForm, KnowledgeCategoryForm
from .models import KnowledgeCategory


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
        templates = SpecificationTemplate.objects.all().order_by("name")
        return render(request, self.template_name, {"templates": templates})


class TemplateEditView(AdminRequiredMixin, View):
    template_name = "specifications/template_edit.html"

    def get(self, request, pk):
        obj = get_object_or_404(SpecificationTemplate, pk=pk)
        form = SpecificationTemplateForm(instance=obj)
        return render(request, self.template_name, {"form": form, "obj": obj})

    def post(self, request, pk):
        obj = get_object_or_404(SpecificationTemplate, pk=pk)
        form = SpecificationTemplateForm(request.POST, instance=obj)
        if form.is_valid():
            saved = form.save()
            saved.created_by = saved.created_by or request.user
            saved.save()
            messages.success(request, "Template saved.")
            return redirect(reverse("specifications:templates_index"))
        return render(request, self.template_name, {"form": form, "obj": obj})


class KnowledgeIndexView(AdminRequiredMixin, View):
    template_name = "specifications/knowledge_index.html"

    def get(self, request):
        entries = KnowledgeEntry.objects.select_related("category").order_by("title")
        return render(request, self.template_name, {"entries": entries})
