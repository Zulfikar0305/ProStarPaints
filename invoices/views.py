from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from audit.services import log_action
from system_tools.models import AppSetting
from users.mixins import AdminRequiredMixin
from users.models import User

from .forms import InvoiceForm
from .models import Invoice


# ---------------------------------------------------------------------------
# Shared mixin — Rep sees only own records; Admin sees all (non-removed)
# ---------------------------------------------------------------------------

class InvoiceAccessMixin(LoginRequiredMixin):
    """
    LoginRequired mixin that scopes the base queryset by role:
    - ADMIN / superuser → all non-removed invoices
    - REP              → only their own non-removed invoices
    """

    def _is_admin(self):
        u = self.request.user
        return u.is_superuser or getattr(u, "role", None) == "ADMIN"

    def get_base_qs(self):
        qs = Invoice.objects.select_related("created_by").filter(is_removed=False)
        if not self._is_admin():
            qs = qs.filter(created_by=self.request.user)
        return qs


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class InvoiceListView(InvoiceAccessMixin, ListView):
    template_name = "invoices/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 25

    def get_queryset(self):
        qs = self.get_base_qs()

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(customer_name__icontains=q) | Q(reference__icontains=q))

        status = self.request.GET.get("status", "")
        if status in Invoice.Status.values:
            qs = qs.filter(status=status)

        # Admin-only: filter by rep
        rep_id = self.request.GET.get("rep", "")
        if self._is_admin() and rep_id:
            qs = qs.filter(created_by_id=rep_id)

        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["current_rep"] = self.request.GET.get("rep", "")
        ctx["status_choices"] = Invoice.Status.choices
        ctx["is_admin"] = self._is_admin()
        if self._is_admin():
            ctx["reps"] = User.objects.filter(role=User.Role.REP, is_active=True).order_by("last_name", "first_name")
        return ctx


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

class InvoiceDetailView(InvoiceAccessMixin, DetailView):
    template_name = "invoices/invoice_detail.html"
    context_object_name = "invoice"

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_base_qs(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["is_admin"] = self._is_admin()
        return ctx


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class InvoiceCreateView(InvoiceAccessMixin, CreateView):
    template_name = "invoices/invoice_form.html"
    form_class = InvoiceForm
    success_url = reverse_lazy("invoices:invoice_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            _("Invoice %(ref)s was created successfully.") % {"ref": self.object.reference},
        )
        log_action(
            user=self.request.user,
            action="INVOICE_CREATED",
            module="invoices",
            description=f"Created invoice {self.object.reference} for '{self.object.customer_name}'.",
            metadata={"invoice_id": self.object.pk, "reference": self.object.reference, "status": self.object.status},
            request=self.request,
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("New Invoice / Spec Sheet")
        ctx["submit_label"] = _("Create Invoice")
        ctx["vat_rate"] = AppSetting.get_vat_rate()
        return ctx


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class InvoiceUpdateView(InvoiceAccessMixin, UpdateView):
    template_name = "invoices/invoice_form.html"
    form_class = InvoiceForm

    def get_object(self, queryset=None):
        return get_object_or_404(self.get_base_qs(), pk=self.kwargs["pk"])

    def get_success_url(self):
        return reverse_lazy("invoices:invoice_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            _("Invoice %(ref)s was updated.") % {"ref": self.object.reference},
        )
        log_action(
            user=self.request.user,
            action="INVOICE_UPDATED",
            module="invoices",
            description=f"Updated invoice {self.object.reference} for '{self.object.customer_name}'.",
            metadata={"invoice_id": self.object.pk, "reference": self.object.reference, "status": self.object.status},
            request=self.request,
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("Edit Invoice")
        ctx["submit_label"] = _("Save Changes")
        ctx["vat_rate"] = AppSetting.get_vat_rate()
        return ctx


# ---------------------------------------------------------------------------
# Remove (admin-only soft-delete)
# ---------------------------------------------------------------------------

class InvoiceRemoveView(AdminRequiredMixin, View):
    """Soft-delete an invoice. Only admins/superusers may do this."""

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, is_removed=False)
        return redirect(
            reverse_lazy("invoices:invoice_confirm_remove") + f"?pk={pk}"
        )

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, is_removed=False)
        invoice.is_removed = True
        invoice.save(update_fields=["is_removed", "updated_at"])
        messages.success(
            request,
            _("Invoice %(ref)s has been removed.") % {"ref": invoice.reference},
        )
        log_action(
            user=request.user,
            action="INVOICE_REMOVED",
            module="invoices",
            description=f"Removed invoice {invoice.reference} for '{invoice.customer_name}'.",
            metadata={"invoice_id": invoice.pk, "reference": invoice.reference},
            request=request,
        )
        return redirect("invoices:invoice_list")


class InvoiceConfirmRemoveView(AdminRequiredMixin, View):
    """GET confirmation page before soft-deleting."""

    def get(self, request):
        pk = request.GET.get("pk")
        invoice = get_object_or_404(Invoice, pk=pk, is_removed=False)
        return self._render(request, invoice)

    def _render(self, request, invoice):
        from django.shortcuts import render
        return render(request, "invoices/invoice_confirm_remove.html", {"invoice": invoice})

