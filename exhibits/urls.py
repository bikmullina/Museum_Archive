from django.urls import path
from . import views

urlpatterns = [
    # Главные маршруты
    path('', views.exhibit_list, name='exhibit_list'),
    path('add/', views.add_exhibit, name='add_exhibit'),
    path('management/', views.management_menu, name='management_menu'),
    path('accounts/profile/', views.exhibit_list, name='profile_redirect'),
    
    # API маршруты
    path('api/exhibits/', views.api_exhibit_list, name='api_exhibit_list'),
    path('api/authors/', views.api_authors, name='api_authors'),
    path('api/authors/add/', views.api_add_author, name='api_add_author'),
    
    # Экспонаты
    path('exhibit/<int:exhibit_id>/', views.exhibit_detail, name='exhibit_detail'),
    path('exhibit/<int:exhibit_id>/edit/', views.edit_exhibit, name='edit_exhibit'),
    
    # Реставрации
    path('restoration/', views.restoration_list, name='restoration_list'),
    path('restoration/add/', views.add_restoration, name='add_restoration'),
    path('restoration/download/<int:restoration_id>/', views.download_restoration_pdf, name='download_restoration_pdf'),
    
    # Выставки
    path('exhibitions/', views.exhibition_list, name='exhibition_list'),
    path('exhibitions/add/', views.add_exhibition, name='add_exhibition'),
    
    # Списания
    path('write-offs/', views.write_off_list, name='write_off_list'),
    path('write-offs/add/', views.add_write_off, name='add_write_off'),
]