from django.urls import path

from . import feeds, views

urlpatterns = [
    path('publications', views.PublicationListView.as_view(), name='publication-list'),
    path('publications/<slug:slug>', views.PublicationDetailView.as_view(), name='publication-detail'),
    path('publications/<slug:slug>/view', views.ViewCountView.as_view(), name='publication-view'),
    path('categories', views.CategoryListView.as_view(), name='category-list'),
    path('search', views.SearchView.as_view(), name='search'),
    path('search/suggest', views.SuggestView.as_view(), name='search-suggest'),
    path('prices', views.PriceView.as_view(), name='prices'),
    path('me/favorites', views.FavoriteListView.as_view(), name='favorite-list'),
    path('me/favorites/slugs', views.FavoriteSlugsView.as_view(), name='favorite-slugs'),
    path('me/favorites/<slug:slug>', views.FavoriteView.as_view(), name='favorite'),
    path('sitemap.xml', feeds.sitemap, name='sitemap'),
    path('news-sitemap.xml', feeds.news_sitemap, name='news-sitemap'),
    path('rss.xml', feeds.rss, name='rss'),
]
