from django.urls import path

from .views import DashboardView, GlobalSearchView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("search/", GlobalSearchView.as_view(), name="global_search"),
]
