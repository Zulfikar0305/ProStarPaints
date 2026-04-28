from django.urls import path

from .views import (
    InvoiceConfirmRemoveView,
    InvoiceCreateView,
    InvoiceDetailView,
    InvoiceListView,
    InvoiceRemoveView,
    InvoiceUpdateView,
)

app_name = "invoices"

urlpatterns = [
    path("", InvoiceListView.as_view(), name="invoice_list"),
    path("create/", InvoiceCreateView.as_view(), name="invoice_create"),
    path("<int:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("<int:pk>/edit/", InvoiceUpdateView.as_view(), name="invoice_update"),
    path("<int:pk>/remove/", InvoiceRemoveView.as_view(), name="invoice_remove"),
    path("confirm-remove/", InvoiceConfirmRemoveView.as_view(), name="invoice_confirm_remove"),
]
