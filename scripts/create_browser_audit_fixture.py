import os
import sys
import pathlib
import django

# Ensure project root is on sys.path so `config` can be imported when
# this script is executed directly.
PROJ_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if PROJ_ROOT not in sys.path:
    sys.path.insert(0, PROJ_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from quotation.models import Quotation, QuotationSection

User = get_user_model()
username = "audituser"
password = "pass"
user, created = User.objects.get_or_create(username=username, defaults={"email": "audit@example.com"})
if created:
    user.set_password(password)
    user.save()

q = Quotation.objects.create(created_by=user, customer_name="BrowserAudit")
s = QuotationSection.objects.create(
    quotation=q,
    subsection_key="interior_walls",
    display_name="Interior Walls",
    sort_order=1,
    selection_order=1,
)

print(q.pk, s.pk, username, password)
