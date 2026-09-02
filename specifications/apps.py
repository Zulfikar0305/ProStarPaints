from django.apps import AppConfig
from django.db.models.signals import post_migrate


def ensure_default_specification_knowledge(sender=None, **kwargs):
    """Ensure the default specification knowledge is present once migrations are done."""
    try:
        from .models import KnowledgeEntry
        from .services.knowledge_seed import seed_default_specification_knowledge

        if not KnowledgeEntry.objects.filter(is_active=True).exists():
            seed_default_specification_knowledge()
    except Exception:
        pass


class SpecificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "specifications"
    verbose_name = "Specification Library"

    def ready(self):
        post_migrate.connect(ensure_default_specification_knowledge, sender=self, dispatch_uid="specifications.seed_default_knowledge")
