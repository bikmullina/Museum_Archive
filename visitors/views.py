from django.shortcuts import render
from django.db import connection
from django.http import Http404
import qrcode
from io import BytesIO
import base64

def dictfetchall(cursor):
    """Преобразует результат запроса в список словарей"""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def public_exhibit_list(request):
    """Публичный список экспонатов с поиском"""
    search_query = request.GET.get('search', '')
    
    with connection.cursor() as cursor:
        if search_query:
            cursor.execute("""
                SELECT 
                    e.id,
                    e.inventory_number,
                    e.exhibit_name,
                    e.dating,
                    e.dimensions,
                    e.description,
                    e.location_in_museum,
                    e.is_on_display
                FROM exhibits e
                WHERE e.exhibit_name ILIKE %s
                ORDER BY e.created_at DESC
            """, [f'%{search_query}%'])
        else:
            cursor.execute("""
                SELECT 
                    e.id,
                    e.inventory_number,
                    e.exhibit_name,
                    e.dating,
                    e.dimensions,
                    e.description,
                    e.location_in_museum,
                    e.is_on_display
                FROM exhibits e
                ORDER BY e.created_at DESC
            """)
        
        exhibits = dictfetchall(cursor)
        
        for exhibit in exhibits:
            # Автор
            cursor.execute("""
                SELECT a.full_name 
                FROM authors a
                JOIN exhibits e ON e.author_id = a.id
                WHERE e.id = %s
            """, [exhibit['id']])
            row = cursor.fetchone()
            exhibit['author_name'] = row[0] if row else 'Неизвестен'
            
            # Материалы
            cursor.execute("""
                SELECT m.name 
                FROM materials m
                JOIN exhibit_materials em ON m.id = em.material_id
                WHERE em.exhibit_id = %s
            """, [exhibit['id']])
            materials = cursor.fetchall()
            if materials:
                exhibit['material_names'] = ', '.join([m[0] for m in materials])
            else:
                cursor.execute("""
                    SELECT m.name 
                    FROM materials m
                    JOIN exhibits e ON e.material_id = m.id
                    WHERE e.id = %s
                """, [exhibit['id']])
                row = cursor.fetchone()
                exhibit['material_names'] = row[0] if row else 'Не указан'
            
            # Фото
            cursor.execute("""
                SELECT photo_path FROM exhibit_photos 
                WHERE exhibit_id = %s AND is_main = TRUE 
                LIMIT 1
            """, [exhibit['id']])
            row = cursor.fetchone()
            exhibit['main_photo'] = row[0] if row else None
    
    return render(request, 'visitors/exhibit_list.html', {
        'exhibits': exhibits,
        'search_query': search_query,
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
        
        # Получаем фотографии
        cursor.execute("""
            SELECT photo_path, is_main, description, uploaded_at
            FROM exhibit_photos 
            WHERE exhibit_id = %s
            ORDER BY is_main DESC, uploaded_at DESC
        """, [exhibit_id])
        photos = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
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