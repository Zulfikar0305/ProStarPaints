"""Validate Specification Library installation (Pack 1A).

Runs a few non-destructive checks:
 - ensures admin can access spec pages
 - ensures rep cannot access spec pages
 - ensures quotations list is accessible
 - attempts to import PDF module

Prints simple status lines for each check.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()


def get_or_create_admin():
    username = "spec_admin_pack1a"
    u = User.objects.filter(username=username).first()
    if not u:
        u = User.objects.create_superuser(
            username=username,
            email="spec_admin_pack1a@example.com",
            password="password123",
            first_name="Spec",
            last_name="Admin",
        )
        print("CREATED admin", username)
    else:
        if not u.is_superuser:
            u.is_superuser = True
            u.is_staff = True
            u.set_password("password123")
            u.save()
            print("UPDATED admin to superuser", username)
    return u


def get_or_create_rep():
    username = "spec_rep_pack1a"
    u = User.objects.filter(username=username).first()
    if not u:
        u = User.objects.create_user(
            username=username,
            email="spec_rep_pack1a@example.com",
            password="password123",
            first_name="Spec",
            last_name="Rep",
        )
        u.role = "REP"
        u.save()
        print("CREATED rep", username)
    else:
        if getattr(u, "role", None) != "REP":
            u.role = "REP"
            u.save()
            print("UPDATED rep role for", username)
    return u


def main():
    admin = get_or_create_admin()
    rep = get_or_create_rep()

    c = Client()
    c.force_login(admin)

    urls = ["/specifications/", "/specifications/templates/", "/specifications/knowledge/"]

    print("\n-- ADMIN ACCESS CHECKS --")
    for u in urls:
        r = c.get(u)
        ok = r.status_code == 200
        text = r.content.decode("utf-8", errors="replace")[:200]
        contains = "Specification Library" in text or "Document Templates" in text or "Knowledge Library" in text
        print(f"ADMIN GET {u} -> {r.status_code}; contains_spec_text={contains}")

    # Sidebar presence (dashboard)
    rd = c.get("/dashboard/")
    has_sidebar = "Specification Library" in rd.content.decode("utf-8", errors="replace")
    print(f"ADMIN GET /dashboard/ -> {rd.status_code}; sidebar_has_spec={has_sidebar}")

    print("\n-- REP ACCESS CHECKS --")
    c2 = Client()
    c2.force_login(rep)
    for u in urls:
        r = c2.get(u)
        loc = r.get("Location", "")
        print(f"REP GET {u} -> {r.status_code}; redirect_to={loc}")

    # Quotation list should remain accessible to reps
    rq = c2.get("/quotations/")
    print(f"REP GET /quotations/ -> {rq.status_code}")

    print("\n-- PDF MODULE IMPORT CHECK --")
    try:
        import importlib
        importlib.import_module("quotation.pdf_service")
        print("PDF_MODULE_IMPORT=OK")
    except Exception as e:
        print("PDF_MODULE_IMPORT_FAILED", str(e))

    # ------------------------------------------------------------------
    # Template edit validation
    # ------------------------------------------------------------------
    from specifications.models import SpecificationTemplate

    tmpl, created = SpecificationTemplate.objects.get_or_create(
        key="default-template",
        defaults={"name": "Default Template", "content": "", "is_active": True, "created_by": admin},
    )
    if created:
        print("CREATED default template", tmpl.pk)

    edit_url = f"/specifications/templates/{tmpl.pk}/edit/"
    r = c.get(edit_url)
    print(f"ADMIN GET {edit_url} -> {r.status_code}")

    post_data = {
        "name": tmpl.name,
        "key": tmpl.key,
        "is_active": "on",
        "cover_page": "Default cover page text",
        "document_title": "Specification Report",
        "introduction": "Intro text",
        "header": "{company} — Header",
        "footer": "{page} / {pages}",
        "closing_statement": "Thank you",
        "company_info": "Company Name\nAddress\nPhone",
        "logo_options": "{\"position\": \"top-right\"}",
        "typography": "Inter, 11pt",
        "colours": "primary:#6f42c1;accent:#00a86b",
        "spacing": "margin:20mm;gutter:10mm",
    }

    rp = c.post(edit_url, post_data, follow=True)
    print(f"ADMIN POST {edit_url} -> {rp.status_code}; redirected={rp.redirect_chain}")

    # Reload and confirm config populated
    tmpl.refresh_from_db()
    cfg = getattr(tmpl, "config", {}) or {}
    print("TEMPLATE_CONFIG_KEYS:", list(cfg.keys()))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(2)
