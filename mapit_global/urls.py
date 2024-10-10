from django.urls import include, path
from django.contrib import admin
from django.views.generic.base import RedirectView

urlpatterns = [
    path('admin', RedirectView.as_view(url='admin/', permanent=True)),
    path('admin/', admin.site.urls),
    path('', include('mapit.urls')),
]
