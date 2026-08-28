from django.urls import path

from .views import (
    GenericSectionSaveView,
    InteriorWallsSaveView,
    QuotationBuilderView,
    QuotationDetailView,
    QuotationListView,
    QuotationPdfDownloadView,
    QuotationPdfGenerateView,
    QuotationPdfTemplateSelectView,
    QuotationPinToggleView,
    QuotationReviewView,
    QuotationStartView,
    QuotationSubstrateSelectionView,
    CreateSelectionView,
    DeleteSelectionView,
    SectionImageDeleteView,
)

app_name = "quotation"

urlpatterns = [
    path("",                                    QuotationListView.as_view(),               name="quotation_list"),
    path("start/",                              QuotationStartView.as_view(),              name="quotation_start"),
    path("<int:pk>/pin/",                       QuotationPinToggleView.as_view(),          name="quotation_pin_toggle"),
    path("<int:pk>/sections/",                  QuotationSubstrateSelectionView.as_view(), name="quotation_sections"),
    path("<int:pk>/builder/",                   QuotationBuilderView.as_view(),            name="quotation_builder"),
    path("<int:pk>/review/",                    QuotationReviewView.as_view(),             name="quotation_review"),
    path("<int:pk>/",                           QuotationDetailView.as_view(),             name="quotation_detail"),
    path("<int:pk>/pdf/",                       QuotationPdfTemplateSelectView.as_view(),  name="pdf_select"),
    path("<int:pk>/pdf/generate/",              QuotationPdfGenerateView.as_view(),        name="pdf_generate"),
    path("pdf/<int:export_id>/",                QuotationPdfDownloadView.as_view(),        name="pdf_download_direct"),
    path("pdf/<int:export_id>/download/",       QuotationPdfDownloadView.as_view(),        name="pdf_download"),
    # Section-specific save endpoints
    path("<int:pk>/sections/<int:section_pk>/interior-walls/save/",
         InteriorWallsSaveView.as_view(), name="interior_walls_save"),
    path("<int:pk>/sections/<int:section_pk>/save/",
         GenericSectionSaveView.as_view(), name="section_save"),
        path("<int:pk>/sections/<int:section_pk>/images/<int:image_pk>/delete/",
            SectionImageDeleteView.as_view(), name="section_image_delete"),
        # Repeatable selection endpoints (backend only)
            path("<int:pk>/sections/<str:subsection_key>/add/",
                CreateSelectionView.as_view(), name="section_add"),
            path("<int:pk>/sections/<int:section_pk>/delete/",
                DeleteSelectionView.as_view(), name="section_delete"),
]

