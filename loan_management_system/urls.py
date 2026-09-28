from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include
from apps.accounts.views import UnifiedAuthView
from apps.loans.views import borrower_portal_view, officer_dashboard_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('accounts:auth'), name='root'),
    path('auth/', UnifiedAuthView.as_view(), name='auth_direct'),
    path('accounts/', include('apps.accounts.urls')),
    path('loans/', include('apps.loans.urls')),
    path('repayments/', include('apps.repayments.urls')),
    path('reports/', include('apps.reports.urls')),
    path('borrower/', borrower_portal_view, name='borrower'),
    path('officer/', officer_dashboard_view, name='officer'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
