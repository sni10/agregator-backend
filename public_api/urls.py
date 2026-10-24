from django.urls import path

from . import views

urlpatterns = [
    path('publications', views.PublicationListView.as_view(), name='publication-list'),
    path('publications/<slug:slug>', views.PublicationDetailView.as_view(), name='publication-detail'),
    path('categories', views.CategoryListView.as_view(), name='category-list'),
    path('search', views.SearchView.as_view(), name='search'),
]
