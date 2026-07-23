from typing import Iterable, List, Optional
from django.db.models import Q

from specifications.models import KnowledgeEntry


class ClauseService:
    """Resolve specification clauses via ClauseTrigger mappings.

    The service returns `KnowledgeEntry` objects (kind='clause').
    """

    @staticmethod
    def resolve(trigger_type: str, trigger_key: Optional[str] = None) -> List[KnowledgeEntry]:
        qs = KnowledgeEntry.objects.filter(kind=KnowledgeEntry.KIND_CLAUSE, is_active=True)
        if trigger_key is None:
            # explicit blank-key triggers only
            qs = qs.filter(triggers__trigger_type=trigger_type, triggers__trigger_key="")
        else:
            # match exact trigger_key, but also include generic ('') triggers
            qs = qs.filter(
                triggers__trigger_type=trigger_type,
            ).filter(Q(triggers__trigger_key=trigger_key) | Q(triggers__trigger_key=""))

        return list(qs.distinct().order_by("sort_order", "title"))
