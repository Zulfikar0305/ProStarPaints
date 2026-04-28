from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("", views.UserListView.as_view(), name="user_list"),
    path("create/", views.UserCreateView.as_view(), name="user_create"),
    path("<int:pk>/edit/", views.UserUpdateView.as_view(), name="user_update"),
    path("<int:pk>/deactivate/", views.UserDeactivateView.as_view(), name="user_deactivate"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
]
