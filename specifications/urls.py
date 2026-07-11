from django.urls import path

from . import views

app_name = "specifications"

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("templates/", views.TemplatesIndexView.as_view(), name="templates_index"),
    path("templates/<int:pk>/edit/", views.TemplateEditView.as_view(), name="template_edit"),
    path("knowledge/", views.KnowledgeIndexView.as_view(), name="knowledge_index"),
]
