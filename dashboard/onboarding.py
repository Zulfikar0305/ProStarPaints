"""
Onboarding checklists for admin and rep dashboards.

Pure read-only computation against existing data. No new models.
Each step exposes:
    label, done, hint, url (optional), icon
"""

from __future__ import annotations

from django.urls import reverse

from paints.models import Paint
from quotation.models import Quotation, QuotationPdfExport
from system_tools.models import AppSetting
from users.models import User


def _step(label: str, done: bool, *, hint: str = "", url: str = "", icon: str = "bi-check2") -> dict:
    return {"label": label, "done": done, "hint": hint, "url": url, "icon": icon}


def get_admin_checklist() -> dict:
    has_other_users = User.objects.exclude(is_superuser=True).exists()
    has_paints = Paint.objects.filter(is_active=True).exists()
    has_vat = AppSetting.objects.filter(key=AppSetting.VAT_RATE_KEY).exists()
    has_quotation = Quotation.objects.exists()
    has_pdf = QuotationPdfExport.objects.filter(
        status=QuotationPdfExport.Status.GENERATED
    ).exists()

    steps = [
        _step(
            "Add users",
            has_other_users,
            hint="Invite at least one rep or admin teammate so the workflow is end-to-end.",
            url=reverse("users:user_list"),
            icon="bi-people",
        ),
        _step(
            "Add paints",
            has_paints,
            hint="Build the catalogue your reps will pull from when configuring sections.",
            url=reverse("paints:paint_list"),
            icon="bi-palette",
        ),
        _step(
            "Configure VAT",
            has_vat,
            hint="Set the application VAT rate used across pricing and invoices.",
            url=reverse("system_tools:vat_settings"),
            icon="bi-percent",
        ),
        _step(
            "Create first quotation",
            has_quotation,
            hint="Start a draft quotation to validate the customer / sections / builder flow.",
            url=reverse("quotation:quotation_start"),
            icon="bi-file-earmark-plus",
        ),
        _step(
            "Generate first PDF",
            has_pdf,
            hint="Export a customer-ready PDF from any quotation to prove the engine works.",
            url=reverse("quotation:quotation_list"),
            icon="bi-file-earmark-pdf",
        ),
    ]
    return _summarise(steps, role="admin")


def get_rep_checklist(user) -> dict:
    profile_done = bool(user.first_name and user.last_name and user.email)
    my_quotations = Quotation.objects.filter(created_by=user)
    has_quotation = my_quotations.exists()
    has_configured = my_quotations.filter(sections__is_placeholder=False).exists()
    has_pdf = QuotationPdfExport.objects.filter(
        quotation__created_by=user,
        status=QuotationPdfExport.Status.GENERATED,
    ).exists()

    steps = [
        _step(
            "Complete your profile",
            profile_done,
            hint="Add your full name and email so PDFs and notifications attribute work correctly.",
            url=reverse("users:profile"),
            icon="bi-person-circle",
        ),
        _step(
            "Start a quotation",
            has_quotation,
            hint="Create a draft to capture a customer and project.",
            url=reverse("quotation:quotation_start"),
            icon="bi-file-earmark-plus",
        ),
        _step(
            "Configure surfaces",
            has_configured,
            hint="Add at least one configured section (interior or exterior) inside the builder.",
            url=reverse("quotation:quotation_list"),
            icon="bi-grid-3x3-gap",
        ),
        _step(
            "Generate a PDF",
            has_pdf,
            hint="Pick a template and export your first customer-ready PDF.",
            url=reverse("quotation:quotation_list"),
            icon="bi-file-earmark-pdf",
        ),
    ]
    return _summarise(steps, role="rep")


def _summarise(steps: list[dict], *, role: str) -> dict:
    total = len(steps)
    done = sum(1 for s in steps if s["done"])
    return {
        "role": role,
        "steps": steps,
        "total": total,
        "done": done,
        "percent": int(round(done / total * 100)) if total else 0,
        "complete": done == total,
    }
