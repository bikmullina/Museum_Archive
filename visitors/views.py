# visitors/views.py
from django.shortcuts import render
from django.db import connection
from django.http import Http404, JsonResponse
from django.core.paginator import Paginator
from django.conf import settings
import qrcode
from io import BytesIO
import base64
import json

def dictfetchall(cursor):
    """Преобразует результат запроса в список словарей"""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def get_full_photo_url(photo_path):
    """Преобразует относительный путь в полный URL для Yandex Cloud"""
    if not photo_path:
        return None
    # Если уже полный URL, возвращаем как есть
    if photo_path.startswith('http://') or photo_path.startswith('https://'):
        return photo_path
    # Формируем полный URL
    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    return f"{media_url.rstrip('/')}/{photo_path.lstrip('/')}"

def public_exhibit_list(request):
    """Публичный список экспонатов с поиском, фильтрацией и пагинацией"""
    search_query = request.GET.get('search', '')
    author_filter = request.GET.get('author', '')
    material_filter = request.GET.get('material', '')
    on_display = request.GET.get('on_display', '')
    
    with connection.cursor() as cursor:
        # Базовый запрос с фильтрацией
        sql = """
            SELECT 
                e.id,
                e.inventory_number,
                e.exhibit_name,
                e.dating,
                e.dimensions,
                e.description,
                e.location_in_museum,
                e.is_on_display,
                a.full_name as author_name
            FROM exhibits e
            LEFT JOIN authors a ON e.author_id = a.id
            WHERE 1=1
        """
        params = []
        
        if search_query:
            sql += " AND e.exhibit_name ILIKE %s"
            params.append(f'%{search_query}%')
        
        if author_filter:
            sql += " AND a.id = %s"
            params.append(author_filter)
        
        if material_filter:
            sql += """ AND e.id IN (
                SELECT exhibit_id FROM exhibit_materials WHERE material_id = %s
            )"""
            params.append(material_filter)
        
        if on_display == 'yes':
            sql += " AND e.is_on_display = TRUE"
        
        sql += " ORDER BY e.created_at DESC"
        
        cursor.execute(sql, params)
        exhibits = dictfetchall(cursor)
        
        # Получаем материалы и фото для каждого экспоната
        for exhibit in exhibits:
            # Получаем материалы
            cursor.execute("""
                SELECT m.name 
                FROM materials m
                JOIN exhibit_materials em ON m.id = em.material_id
                WHERE em.exhibit_id = %s
            """, [exhibit['id']])
            materials = cursor.fetchall()
            exhibit['material_names'] = ', '.join([m[0] for m in materials]) if materials else 'Не указан'
            
            # Получаем главное фото
            cursor.execute("""
                SELECT photo_path FROM exhibit_photos 
                WHERE exhibit_id = %s AND is_main = TRUE 
                LIMIT 1
            """, [exhibit['id']])
            row = cursor.fetchone()
            exhibit['main_photo'] = get_full_photo_url(row[0]) if row else None
    
    # Пагинация (12 экспонатов на страницу)
    paginator = Paginator(exhibits, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Получаем список авторов для фильтра
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, full_name FROM authors ORDER BY full_name")
        authors = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM materials ORDER BY name")
        materials = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    
    return render(request, 'visitors/exhibit_list.html', {
        'exhibits': page_obj,
        'search_query': search_query,
        'authors': authors,
        'materials': materials,
        'selected_author': author_filter,
        'selected_material': material_filter,
        'on_display_filter': on_display,
    })

def public_exhibit_detail(request, exhibit_id):
    """Детальная страница экспоната с QR-кодом"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                e.*,
                a.full_name as author_name,
                a.birth_year,
                a.death_year,
                m.name as material_name,
                t.name as technique_name,
                atype.authenticity_name,
                am.method_name
            FROM exhibits e
            LEFT JOIN authors a ON e.author_id = a.id
            LEFT JOIN materials m ON e.material_id = m.id
            LEFT JOIN techniques t ON e.technique_id = t.id
            LEFT JOIN authenticity_types atype ON e.authenticity_id = atype.id
            LEFT JOIN acquisition_methods am ON e.acquisition_method_id = am.id
            WHERE e.id = %s
        """, [exhibit_id])
        
        row = cursor.fetchone()
        if not row:
            raise Http404("Экспонат не найден")
        
        columns = [col[0] for col in cursor.description]
        exhibit = dict(zip(columns, row))
        
        # Получаем все материалы (если есть в exhibit_materials)
        cursor.execute("""
            SELECT m.name 
            FROM materials m
            JOIN exhibit_materials em ON m.id = em.material_id
            WHERE em.exhibit_id = %s
            ORDER BY m.name
        """, [exhibit_id])
        materials = cursor.fetchall()
        if materials:
            exhibit['all_materials'] = ', '.join([m[0] for m in materials])
        else:
            exhibit['all_materials'] = exhibit.get('material_name', 'Не указан')
        
        # Получаем фотографии и преобразуем пути в полные URL
        cursor.execute("""
            SELECT photo_path, is_main, description, uploaded_at
            FROM exhibit_photos 
            WHERE exhibit_id = %s
            ORDER BY is_main DESC, uploaded_at DESC
        """, [exhibit_id])
        photos = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        # Преобразуем пути в полные URL
        for photo in photos:
            photo['photo_path'] = get_full_photo_url(photo['photo_path'])
        
        # Получаем историю экспоната
        cursor.execute("""
            SELECT event_date, event_type, description, document_reference, created_at
            FROM exhibit_history
            WHERE exhibit_id = %s
            ORDER BY event_date DESC, created_at DESC
        """, [exhibit_id])
        history = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    
    # Генерируем QR-код
    url = request.build_absolute_uri()
    qr = qrcode.make(url)
    
    # Сохраняем в память и кодируем в base64 для вставки в HTML
    buffer = BytesIO()
    qr.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return render(request, 'visitors/exhibit_detail.html', {
        'exhibit': exhibit,
        'photos': photos,
        'history': history,
        'qr_data': url,
        'qr_image': qr_base64,
    })

def scan_qr(request):
    """Страница сканера QR-кодов"""
    return render(request, 'visitors/scan_qr.html')

def filter_exhibits(request):
    """API для фильтрации экспонатов (AJAX)"""
    search_query = request.GET.get('search', '')
    author_filter = request.GET.get('author', '')
    material_filter = request.GET.get('material', '')
    on_display = request.GET.get('on_display', '')
    page = request.GET.get('page', 1)
    
    with connection.cursor() as cursor:
        sql = """
            SELECT 
                e.id,
                e.inventory_number,
                e.exhibit_name,
                e.dating,
                e.dimensions,
                e.location_in_museum,
                a.full_name as author_name
            FROM exhibits e
            LEFT JOIN authors a ON e.author_id = a.id
            WHERE 1=1
        """
        params = []
        
        if search_query:
            sql += " AND e.exhibit_name ILIKE %s"
            params.append(f'%{search_query}%')
        
        if author_filter:
            sql += " AND a.id = %s"
            params.append(author_filter)
        
        if material_filter:
            sql += """ AND e.id IN (
                SELECT exhibit_id FROM exhibit_materials WHERE material_id = %s
            )"""
            params.append(material_filter)
        
        if on_display == 'yes':
            sql += " AND e.is_on_display = TRUE"
        
        sql += " ORDER BY e.created_at DESC"
        
        cursor.execute(sql, params)
        exhibits = dictfetchall(cursor)
        
        # Получаем материалы и фото для каждого экспоната
        for exhibit in exhibits:
            cursor.execute("""
                SELECT m.name 
                FROM materials m
                JOIN exhibit_materials em ON m.id = em.material_id
                WHERE em.exhibit_id = %s
            """, [exhibit['id']])
            materials = cursor.fetchall()
            exhibit['material_names'] = ', '.join([m[0] for m in materials]) if materials else 'Не указан'
            
            cursor.execute("""
                SELECT photo_path FROM exhibit_photos 
                WHERE exhibit_id = %s AND is_main = TRUE 
                LIMIT 1
            """, [exhibit['id']])
            row = cursor.fetchone()
            exhibit['main_photo'] = get_full_photo_url(row[0]) if row else None
    
    # Пагинация
    paginator = Paginator(exhibits, 12)
    page_obj = paginator.get_page(page)
    
    # Формируем HTML для ответа
    from django.template.loader import render_to_string
    html = render_to_string('visitors/exhibit_items.html', {'exhibits': page_obj})
    
    return JsonResponse({
        'html': html,
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
        'current_page': page_obj.number,
        'total_pages': paginator.num_pages,
    })