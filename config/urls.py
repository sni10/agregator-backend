from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('', include('accounts.api.urls')),
    path('', include('contact.urls')),
    path('', include('publishing_api.urls')),
    path('', include('public_api.urls')),
]

# Story images; in production Caddy serves MEDIA_ROOT itself (static() adds nothing when DEBUG is off)
urlpatterns += static('media/', document_root=settings.MEDIA_ROOT)
