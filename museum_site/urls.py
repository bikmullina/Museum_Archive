from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from exhibits import views as exhibits_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),
    
    # API маршруты
    path('api/exhibits/', exhibits_views.api_exhibit_list, name='api_exhibit_list'),
    path('api/authors/', exhibits_views.api_authors, name='api_authors'),
    path('api/authors/add/', exhibits_views.api_add_author, name='api_add_author'),
    
    # Основные маршруты exhibits
    path('exhibits/', include('exhibits.urls')),
    path('visitors/', include('visitors.urls')),
]