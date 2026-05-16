from django.urls import path

from .views import (
    GenericInteriorSectionSaveView,
    InteriorWallsSaveView,
    QuotationBuilderView,
    QuotationDetailView,
    QuotationListView,
    QuotationReviewView,
    QuotationStartView,
    QuotationSubstrateSelectionView,
)

app_name = "quotation"

urlpatterns = [
    path("",                                    QuotationListView.as_view(),               name="quotation_list"),
    path("start/",                              QuotationStartView.as_view(),              name="quotation_start"),
    path("<int:pk>/sections/",                  QuotationSubstrateSelectionView.as_view(), name="quotation_sections"),
    path("<int:pk>/builder/",                   QuotationBuilderView.as_view(),            name="quotation_builder"),
    path("<int:pk>/review/",                    QuotationReviewView.as_view(),             name="quotation_review"),
    path("<int:pk>/",                           QuotationDetailView.as_view(),             name="quotation_detail"),
    # Section-specific save endpoints
    path("<int:pk>/sections/<int:section_pk>/interior-walls/save/",
         InteriorWallsSaveView.as_view(), name="interior_walls_save"),
    path("<int:pk>/sections/<int:section_pk>/interior-section/save/",
         GenericInteriorSectionSaveView.as_view(), name="interior_section_save"),
]
