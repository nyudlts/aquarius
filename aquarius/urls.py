"""aquarius URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
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
from django.contrib import admin
from django.conf.urls import url
from django.urls import include, re_path
from transformer.models import SourceObject
from transformer.views import HomeView, SourceObjectViewSet, ConsumerObjectViewSet, TransformViewSet
from accession_numbers.views import AccessionNumberViewSet, NextAccessionNumberView
from rest_framework import routers
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

router = routers.DefaultRouter()
router.register(r'accession-numbers', AccessionNumberViewSet)
router.register(r'transform', TransformViewSet, 'transform')
router.register(r'source_objects', SourceObjectViewSet, 'sourceobject')
router.register(r'consumer_objects', ConsumerObjectViewSet, 'consumerobject')

schema_view = get_schema_view(
   openapi.Info(
      title="Aquarius API",
      default_version='v1',
      description="Test description",
      contact=openapi.Contact(email="archive@rockarch.org"),
      license=openapi.License(name="MIT License"),
   ),
   validators=['flex', 'ssv'],
   public=True,
)

urlpatterns = [
    re_path(r'^$', HomeView.as_view(), name='home'),
    url(r'^', include(router.urls)),
    re_path(r'^next-accession-number', NextAccessionNumberView.as_view(), name='next-accession'),
    url(r'^status/', include('health_check.api.urls')),
    url(r'^admin/', admin.site.urls),
    url(r'^schema(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=None), name='schema-json'),
]
