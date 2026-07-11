from django.urls import path

from . import views

app_name = "specifications"

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("templates/", views.TemplatesIndexView.as_view(), name="templates_index"),
    path("templates/<int:pk>/edit/", views.TemplateEditView.as_view(), name="template_edit"),
    path("knowledge/", views.KnowledgeIndexView.as_view(), name="knowledge_index"),
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
]
