from django.urls import path

from . import feeds, views

urlpatterns = [
    path('publications', views.PublicationListView.as_view(), name='publication-list'),
    path('publications/<slug:slug>', views.PublicationDetailView.as_view(), name='publication-detail'),
    path('categories', views.CategoryListView.as_view(), name='category-list'),
    path('search', views.SearchView.as_view(), name='search'),
    path('sitemap.xml', feeds.sitemap, name='sitemap'),
    path('news-sitemap.xml', feeds.news_sitemap, name='news-sitemap'),
    path('rss.xml', feeds.rss, name='rss'),
]
