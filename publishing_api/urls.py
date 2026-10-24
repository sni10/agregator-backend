from django.urls import path

from . import views

urlpatterns = [
    path('publishing/publications', views.PublicationCreateView.as_view(), name='publishing-create'),
    path('publishing/publications/<str:external_id>', views.PublicationDetailView.as_view(),
         name='publishing-detail'),
    path('health', views.health, name='health'),
]
