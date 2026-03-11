from django.shortcuts import redirect
from django.urls import reverse

class RedirectAdminMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Если пользователь пытается зайти в админку
        if request.path.startswith('/admin/') and request.user.is_authenticated:
            # Если это не суперпользователь или мы просто хотим перенаправить всех
            return redirect(reverse('exhibit_list'))
        
        response = self.get_response(request)
        return response