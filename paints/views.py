from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView, View

from audit.services import log_action
from system_tools.models import AppSetting
from users.mixins import AdminRequiredMixin

from .forms import PaintForm
from .models import Paint


class PaintListView(AdminRequiredMixin, ListView):
    """Display all paints with search and active/inactive filter."""

    model = Paint
    template_name = "paints/paint_list.html"
    context_object_name = "paints"
    paginate_by = 25

    def get_queryset(self):
        qs = Paint.objects.all()

        # Active/inactive filter
        status = self.request.GET.get("status", "active")
        if status == "inactive":
            qs = qs.filter(is_active=False)
        elif status == "all":
            pass
        else:
            qs = qs.filter(is_active=True)

        # Category filter
        category = self.request.GET.get("category", "")
        if category:
            qs = qs.filter(category=category)

        # Search — name, category label, paint_type, base_type, colour
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(colour__icontains=q))

        return qs.order_by("category", "name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["category_choices"] = Paint.Category.choices
        ctx["q"] = self.request.GET.get("q", "")
        ctx["current_status"] = self.request.GET.get("status", "active")
        ctx["current_category"] = self.request.GET.get("category", "")
        return ctx


class PaintCreateView(AdminRequiredMixin, CreateView):
    """Allow admin to add a new paint to the catalogue."""

    model = Paint
    form_class = PaintForm
    template_name = "paints/paint_form.html"
    success_url = reverse_lazy("paints:paint_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("Add Paint")
        ctx["submit_label"] = _("Add Paint")
        ctx["vat_rate"] = AppSetting.get_vat_rate()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _('Paint "%(name)s" was added successfully.') % {"name": self.object.name})
        log_action(
            user=self.request.user,
            action="PAINT_CREATED",
            module="paints",
            description=f"Created paint '{self.object.name}' (category: {self.object.get_category_display()}).",
            metadata={"paint_id": self.object.pk, "category": self.object.category},
            request=self.request,
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


class PaintUpdateView(AdminRequiredMixin, UpdateView):
    """Allow admin to edit an existing paint record."""

    model = Paint
    form_class = PaintForm
    template_name = "paints/paint_form.html"
    success_url = reverse_lazy("paints:paint_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("Edit Paint — %(name)s") % {"name": self.object.name}
        ctx["submit_label"] = _("Save Changes")
        ctx["vat_rate"] = AppSetting.get_vat_rate()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _('Paint "%(name)s" was updated successfully.') % {"name": self.object.name})
        log_action(
            user=self.request.user,
            action="PAINT_UPDATED",
            module="paints",
            description=f"Updated paint '{self.object.name}' (id: {self.object.pk}).",
            metadata={"paint_id": self.object.pk},
            request=self.request,
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


class PaintDeactivateView(AdminRequiredMixin, View):
    """
    Toggle a paint's is_active status.
    GET  → confirmation page
    POST → perform toggle
    """

    template_name = "paints/paint_confirm_deactivate.html"

    def get(self, request, pk):
        paint = get_object_or_404(Paint, pk=pk)
        return render(request, self.template_name, {"paint": paint})

    def post(self, request, pk):
        paint = get_object_or_404(Paint, pk=pk)
        paint.is_active = not paint.is_active
        paint.save(update_fields=["is_active"])
        action_word = "activated" if paint.is_active else "deactivated"
        audit_action = "PAINT_ACTIVATED" if paint.is_active else "PAINT_DEACTIVATED"
        messages.success(
            request,
            _('Paint "%(name)s" has been %(action)s.') % {"name": paint.name, "action": _(action_word)},
        )
        log_action(
            user=request.user,
            action=audit_action,
            module="paints",
            description=f"Paint '{paint.name}' (id: {paint.pk}) was {action_word}.",
            metadata={"paint_id": paint.pk, "is_active": paint.is_active},
            request=request,
        )
        return redirect("paints:paint_list")
