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

    # ------------------------------------------------------------------
    # Categories and Clauses CRUD validation
    # ------------------------------------------------------------------
    print("\n-- CATEGORIES / CLAUSES CRUD --")
    # Create a category via POST
    cat_data = {"name": "Surface Preparation", "slug": "surface-prep", "description": "Surface prep steps"}
    cr = c.post("/specifications/knowledge/categories/add/", cat_data, follow=True)
    print(f"ADMIN POST /specifications/knowledge/categories/add/ -> {cr.status_code}; redirected={cr.redirect_chain}")

    # Find created category
    from specifications.models import KnowledgeCategory, KnowledgeEntry

    cat = KnowledgeCategory.objects.filter(slug="surface-prep").first()
    print("CATEGORY_CREATED:", bool(cat))

    # Create a clause
    clause_data = {
        "title": "Proper cleaning",
        "body": "Clean surfaces with detergent and rinse.",
        "category": str(cat.pk) if cat else "",
        "kind": KnowledgeEntry.KIND_CLAUSE,
        "is_default": "on",
        "is_active": "on",
        "sort_order": "10",
    }
    cr2 = c.post("/specifications/knowledge/clauses/add/", clause_data, follow=True)
    print(f"ADMIN POST /specifications/knowledge/clauses/add/ -> {cr2.status_code}; redirected={cr2.redirect_chain}")

    clause = KnowledgeEntry.objects.filter(title="Proper cleaning").first()
    print("CLAUSE_CREATED:", bool(clause), "PK:", getattr(clause, "pk", None))

    # Edit clause
    if clause:
        edit_url = f"/specifications/knowledge/clauses/{clause.pk}/edit/"
        gr = c.get(edit_url)
        print(f"ADMIN GET {edit_url} -> {gr.status_code}")
        post_edit = {
            "title": clause.title,
            "body": clause.body + " Updated",
            "category": str(cat.pk) if cat else "",
            "kind": clause.kind,
            "is_default": "on",
            "is_active": "on",
            "sort_order": str(clause.sort_order),
        }
        pr = c.post(edit_url, post_edit, follow=True)
        print(f"ADMIN POST {edit_url} -> {pr.status_code}; redirected={pr.redirect_chain}")
        clause.refresh_from_db()
        print("CLAUSE_BODY_UPDATED:", clause.body.endswith("Updated"))

    # Delete clause
    if clause:
        del_url = f"/specifications/knowledge/clauses/{clause.pk}/delete/"
        rd = c.post(del_url, {}, follow=True)
        print(f"ADMIN POST {del_url} -> {rd.status_code}; redirected={rd.redirect_chain}")
        exists = KnowledgeEntry.objects.filter(pk=clause.pk).exists()
        print("CLAUSE_EXISTS_AFTER_DELETE:", exists)

    # Rep should not be able to access clause create
    rep_post = c2.post("/specifications/knowledge/clauses/add/", clause_data)
    print(f"REP POST /specifications/knowledge/clauses/add/ -> {rep_post.status_code}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(2)
