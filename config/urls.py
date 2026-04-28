"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),

    # Root — redirect to dashboard
    path("", RedirectView.as_view(pattern_name="dashboard:dashboard", permanent=False), name="home"),

    # Auth
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    # Dashboard
    path("dashboard/", include("dashboard.urls", namespace="dashboard")),

    # User management (admin-only)
    path("users/", include("users.urls", namespace="users")),

    # Paint management (admin-only)
    path("paints/", include("paints.urls", namespace="paints")),

    # Audit logs (admin-only)
    path("audit/", include("audit.urls", namespace="audit")),

    # Invoices / spec sheets
    path("invoices/", include("invoices.urls", namespace="invoices")),

    # Quotation builder
    path("quotations/", include("quotation.urls", namespace="quotation")),

    # System Tools (admin-only)
    path("system-tools/", include("system_tools.urls", namespace="system_tools")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
