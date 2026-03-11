from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from exhibits import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.exhibit_list, name='exhibit_list'),
    path('add/', views.add_exhibit, name='add_exhibit'),
    path('login/', views.custom_login, name='login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('management/', views.management_menu, name='management_menu'),
    path('restoration/', views.restoration_list, name='restoration_list'),
    path('restoration/add/', views.add_restoration, name='add_restoration'),
    path('exhibitions/', views.exhibition_list, name='exhibition_list'),
    path('exhibitions/add/', views.add_exhibition, name='add_exhibition'),
    path('write-offs/', views.write_off_list, name='write_off_list'),
    path('write-offs/add/', views.add_write_off, name='add_write_off'),
    path('accounts/profile/', views.exhibit_list, name='profile_redirect'),
    path('exhibit/<int:exhibit_id>/', views.exhibit_detail, name='exhibit_detail'),
    path('visitors/', include('visitors.urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)