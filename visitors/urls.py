# visitors/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.public_exhibit_list, name='public_exhibit_list'),
    path('exhibit/<int:exhibit_id>/', views.public_exhibit_detail, name='public_exhibit_detail'),
    path('scan/', views.scan_qr, name='scan_qr'),
    path('api/filter/', views.filter_exhibits, name='filter_exhibits'),
]