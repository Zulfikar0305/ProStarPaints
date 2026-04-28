from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView, View

from audit.services import log_action

from .forms import UserCreateForm, UserUpdateForm
from .mixins import AdminRequiredMixin
from .models import User


class UserListView(AdminRequiredMixin, ListView):
    """Display all users (admins and reps) in a sortable table."""

    model = User
    template_name = "users/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.all().order_by("last_name", "first_name")
        role_filter = self.request.GET.get("role", "")
        if role_filter in (User.Role.ADMIN, User.Role.REP):
            qs = qs.filter(role=role_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["role_choices"] = User.Role.choices
        ctx["current_role_filter"] = self.request.GET.get("role", "")
        return ctx


class UserCreateView(AdminRequiredMixin, CreateView):
    """Allow admin to create a new user account."""

    model = User
    form_class = UserCreateForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("users:user_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("Create User")
        ctx["submit_label"] = _("Create User")
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        name = self.object.get_full_name() or self.object.username
        messages.success(self.request, _("User %(name)s was created successfully.") % {"name": name})
        log_action(
            user=self.request.user,
            action="USER_CREATED",
            module="users",
            description=f"Created user '{name}' ({self.object.email}) with role {self.object.role}.",
            metadata={"target_user_id": self.object.pk, "role": self.object.role},
            request=self.request,
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


class UserUpdateView(AdminRequiredMixin, UpdateView):
    """Allow admin to edit an existing user's details."""

    model = User
    form_class = UserUpdateForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy("users:user_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = _("Edit User — %(name)s") % {"name": self.object.get_full_name() or self.object.username}
        ctx["submit_label"] = _("Save Changes")
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        name = self.object.get_full_name() or self.object.username
        messages.success(self.request, _("User %(name)s was updated successfully.") % {"name": name})
        log_action(
            user=self.request.user,
            action="USER_UPDATED",
            module="users",
            description=f"Updated user '{name}' ({self.object.email}).",
            metadata={"target_user_id": self.object.pk, "role": self.object.role},
            request=self.request,
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


class UserDeactivateView(AdminRequiredMixin, View):
    """
    Toggle a user's is_active status.
    GET  → confirmation page
    POST → perform toggle
    """

    template_name = "users/user_confirm_deactivate.html"

    def get(self, request, pk):
        from django.shortcuts import render as _render
        user = get_object_or_404(User, pk=pk)
        return _render(request, self.template_name, {"target_user": user})

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        # Prevent admin from deactivating themselves
        if user == request.user:
            messages.error(request, _("You cannot deactivate your own account."))
            return redirect("users:user_list")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class ProfileView(LoginRequiredMixin, View):
    """Display the current user's profile information."""

    def get(self, request):
        return render(request, "users/profile.html", {"profile_user": request.user})
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])

        action_word = "activated" if user.is_active else "deactivated"
        audit_action = "USER_ACTIVATED" if user.is_active else "USER_DEACTIVATED"
        name = user.get_full_name() or user.username
        messages.success(
            request,
            _("User %(name)s has been %(action)s.") % {"name": name, "action": _(action_word)},
        )
        log_action(
            user=request.user,
            action=audit_action,
            module="users",
            description=f"User '{name}' ({user.email}) was {action_word}.",
            metadata={"target_user_id": user.pk, "is_active": user.is_active},
            request=request,
        )
        return redirect("users:user_list")
