from django.urls import path

from . import views

app_name = "specifications"

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("templates/", views.TemplatesIndexView.as_view(), name="templates_index"),
    path("automatic/", views.AutomaticSpecificationView.as_view(), name="automatic_spec"),
    path("templates/<int:pk>/edit/", views.TemplateEditView.as_view(), name="template_edit"),
    path("templates/<int:pk>/duplicate/", views.TemplateDuplicateView.as_view(), name="template_duplicate"),
    path("templates/<int:pk>/deactivate/", views.TemplateDeactivateView.as_view(), name="template_deactivate"),
    path("knowledge/", views.KnowledgeIndexView.as_view(), name="knowledge_index"),
    path("knowledge/add/", views.KnowledgeCreateView.as_view(), name="knowledge_add"),
    path("knowledge/<int:pk>/edit/", views.KnowledgeEditView.as_view(), name="knowledge_edit"),
    path("knowledge/<int:pk>/deactivate/", views.KnowledgeDeactivateView.as_view(), name="knowledge_deactivate"),
    # Clauses CRUD
    path("knowledge/clauses/", views.ClausesIndexView.as_view(), name="clauses_index"),
    path("knowledge/clauses/add/", views.ClauseCreateView.as_view(), name="clause_add"),
    path("knowledge/clauses/<int:pk>/edit/", views.ClauseEditView.as_view(), name="clause_edit"),
    path("knowledge/clauses/<int:pk>/delete/", views.ClauseDeleteView.as_view(), name="clause_delete"),

    # Categories CRUD
    path("knowledge/categories/", views.CategoriesIndexView.as_view(), name="categories_index"),
    path("knowledge/categories/add/", views.CategoryCreateView.as_view(), name="category_add"),
    path("knowledge/categories/<int:pk>/edit/", views.CategoryEditView.as_view(), name="category_edit"),
    path("knowledge/categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
    # Rules
    path("rules/", views.RulesIndexView.as_view(), name="rules_index"),
    path("rules/add/", views.RuleCreateView.as_view(), name="rule_add"),
    path("rules/<int:pk>/edit/", views.RuleEditView.as_view(), name="rule_edit"),
    path("rules/<int:pk>/delete/", views.RuleDeleteView.as_view(), name="rule_delete"),
    path("rules/<int:pk>/move/<str:direction>/", views.RuleMoveView.as_view(), name="rule_move"),
    # Manual builder
    path("builder/quotation/<int:quotation_pk>/", views.ManualBuilderView.as_view(), name="builder_quotation"),
    path("builder/quotation/<int:quotation_pk>/save/", views.DraftSaveView.as_view(), name="builder_draft_save"),
    path("builder/quotation/<int:quotation_pk>/export/", views.ManualBuilderExportView.as_view(), name="builder_quotation_export"),
    # Preview
    path("preview/draft/<int:draft_pk>/", views.DraftPreviewView.as_view(), name="preview_draft"),
    path("preview/quotation/<int:quotation_pk>/", views.QuotationPreviewView.as_view(), name="preview_quotation"),
]
