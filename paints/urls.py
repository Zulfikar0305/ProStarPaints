from django.urls import path

from . import views

app_name = "paints"

urlpatterns = [
    path("", views.PaintListView.as_view(), name="paint_list"),
    path("create/", views.PaintCreateView.as_view(), name="paint_create"),
    path("<int:pk>/edit/", views.PaintUpdateView.as_view(), name="paint_update"),
    path("<int:pk>/deactivate/", views.PaintDeactivateView.as_view(), name="paint_deactivate"),
]
