"""
URL configuration for caterbasepro project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

from client_estimates.views import marketing_home, new_client_inquiry, stripe_webhook, start_trial, trial_expired

urlpatterns = [
    path('', marketing_home, name="marketing_home"),
    path('start-trial/', start_trial, name='start_trial'),
    path('trial-expired/', trial_expired, name='trial_expired'),
    path('new-client-inquiry/', new_client_inquiry, name='public_inquiry_no_slug'),
    path('new-client-inquiry/<slug:caterer_slug>/', new_client_inquiry, name='public_inquiry'),
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook'),
    path('admin/', admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
