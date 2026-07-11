from django.shortcuts import render
from django.views.generic import View

from users.mixins import AdminRequiredMixin

from .models import SpecificationTemplate, KnowledgeEntry
from .forms import SpecificationTemplateForm
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages


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
