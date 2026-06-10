from datetime import datetime
import os
import json
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import connection
from django.contrib.auth import authenticate, login
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings  # <-- ДОБАВЛЕНО
from storages.backends.s3boto3 import S3Boto3Storage


def custom_login(request):
    """Кастомная страница входа"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('exhibit_list')
        else:
            messages.error(request, 'Неверное имя пользователя или пароль')
    
    return render(request, 'registration/login.html')


@login_required
def exhibit_list(request):
    """Список всех экспонатов с поиском и фильтрацией"""
    search_query = request.GET.get('search', '')
    
    with connection.cursor() as cursor:
        # Основные данные экспонатов
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
        
        columns = [col[0] for col in cursor.description]
        exhibits = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # Получаем дополнительные данные для каждого экспоната
        for exhibit in exhibits:
            # Автор
            cursor.execute("""
                SELECT a.full_name 
                FROM authors a
                WHERE a.id = (SELECT author_id FROM exhibits WHERE id = %s)
            """, [exhibit['id']])
            row = cursor.fetchone()
            exhibit['author_name'] = row[0] if row else 'Неизвестен'
            
            # Материалы
            cursor.execute("""
                SELECT m.name 
                FROM materials m
                JOIN exhibit_materials em ON m.id = em.material_id
                WHERE em.exhibit_id = %s
                ORDER BY m.name
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
            if row and row[0]:
                photo_path = row[0]
                if not photo_path.startswith(('http://', 'https://')):
                    photo_path = settings.MEDIA_URL + photo_path
                exhibit['main_photo'] = photo_path
            else:
                exhibit['main_photo'] = None
        
        # Получаем данные для фильтров
        cursor.execute("SELECT id, full_name FROM authors ORDER BY full_name")
        authors = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM materials ORDER BY name")
        materials = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM techniques ORDER BY name")
        techniques = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    
    return render(request, 'exhibit_list.html', {
        'exhibits': exhibits,
        'search_query': search_query,
        'authors': authors,
        'materials': materials,
        'techniques': techniques,
    })


@login_required
@require_GET
def api_exhibit_list(request):
    """API для живого поиска и фильтрации"""
    search_query = request.GET.get('search', '')
    author = request.GET.get('author', '')
    material = request.GET.get('material', '')
    technique = request.GET.get('technique', '')
    location = request.GET.get('location', '')
    dating = request.GET.get('dating', '')
    status = request.GET.get('status', '')
    
    with connection.cursor() as cursor:
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
                e.created_at
            FROM exhibits e
            LEFT JOIN authors a ON e.author_id = a.id
            LEFT JOIN materials m ON e.material_id = m.id
            LEFT JOIN techniques t ON e.technique_id = t.id
            LEFT JOIN exhibit_materials em ON e.id = em.exhibit_id
            LEFT JOIN materials m2 ON em.material_id = m2.id
            WHERE 1=1
        """
        params = []
        
        if search_query:
            sql += " AND e.exhibit_name ILIKE %s"
            params.append(f'%{search_query}%')
        
        if author:
            sql += " AND a.full_name = %s"
            params.append(author)
        
        if material:
            sql += " AND (m.name = %s OR m2.name = %s)"
            params.extend([material, material])
        
        if technique:
            sql += " AND t.name = %s"
            params.append(technique)
        
        if location:
            sql += " AND e.location_in_museum ILIKE %s"
            params.append(f'%{location}%')
        
        if dating:
            sql += " AND e.dating ILIKE %s"
            params.append(f'%{dating}%')
        
        if status == 'display':
            sql += " AND e.is_on_display = TRUE"
        elif status == 'storage':
            sql += " AND e.is_on_display = FALSE"
        
        sql += " GROUP BY e.id ORDER BY e.created_at DESC"
        
        cursor.execute(sql, params)
        
        columns = [col[0] for col in cursor.description]
        exhibits = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        for exhibit in exhibits:
            cursor.execute("""
                SELECT a.full_name 
                FROM authors a
                WHERE a.id = (SELECT author_id FROM exhibits WHERE id = %s)
            """, [exhibit['id']])
            row = cursor.fetchone()
            exhibit['author_name'] = row[0] if row else 'Неизвестен'
            
            cursor.execute("""
                SELECT m.name 
                FROM materials m
                JOIN exhibit_materials em ON m.id = em.material_id
                WHERE em.exhibit_id = %s
                ORDER BY m.name
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
            
            cursor.execute("""
                SELECT photo_path FROM exhibit_photos 
                WHERE exhibit_id = %s AND is_main = TRUE 
                LIMIT 1
            """, [exhibit['id']])
            row = cursor.fetchone()
            if row and row[0]:
                photo_path = row[0]
                if not photo_path.startswith(('http://', 'https://')):
                    photo_path = settings.MEDIA_URL + photo_path
                exhibit['main_photo'] = photo_path
            else:
                exhibit['main_photo'] = None
    
    return render(request, 'exhibit_cards.html', {
        'exhibits': exhibits,
        'search_query': search_query,
    })


@login_required
def api_authors(request):
    """API для поиска авторов"""
    search_query = request.GET.get('search', '')
    
    with connection.cursor() as cursor:
        if search_query:
            cursor.execute("""
                SELECT id, full_name, birth_year, death_year
                FROM authors
                WHERE full_name ILIKE %s
                ORDER BY full_name
                LIMIT 10
            """, [f'%{search_query}%'])
        else:
            cursor.execute("""
                SELECT id, full_name, birth_year, death_year
                FROM authors
                ORDER BY full_name
                LIMIT 10
            """)
        
        columns = [col[0] for col in cursor.description]
        authors = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    return JsonResponse({'authors': authors})


@login_required
@csrf_exempt
def api_add_author(request):
    """API для добавления нового автора"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            full_name = data.get('full_name', '').strip()
            birth_year = data.get('birth_year') or None
            death_year = data.get('death_year') or None
            
            if not full_name:
                return JsonResponse({'success': False, 'error': 'Имя автора обязательно'})
            
            with connection.cursor() as cursor:
                # Проверяем, существует ли уже такой автор
                cursor.execute("""
                    SELECT id FROM authors WHERE full_name = %s
                """, [full_name])
                existing = cursor.fetchone()
                
                if existing:
                    return JsonResponse({
                        'success': True, 
                        'author_id': existing[0],
                        'message': 'Автор уже существует'
                    })
                
                # Добавляем нового автора
                cursor.execute("""
                    INSERT INTO authors (full_name, birth_year, death_year)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, [full_name, birth_year, death_year])
                
                author_id = cursor.fetchone()[0]
                
                return JsonResponse({
                    'success': True, 
                    'author_id': author_id,
                    'message': 'Автор успешно добавлен'
                })
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Метод не поддерживается'})


@login_required
def add_exhibit(request):
    """Добавление нового экспоната"""
    if request.method == 'POST':
        inventory_number = request.POST.get('inventory_number')
        object_code = request.POST.get('object_code')
        exhibit_name = request.POST.get('exhibit_name')
        author_id = request.POST.get('author_id') or None
        dating = request.POST.get('dating')
        material_id = request.POST.get('material_id') or None
        technique_id = request.POST.get('technique_id') or None
        dimensions = request.POST.get('dimensions')
        weight = request.POST.get('weight') or None
        authenticity_id = request.POST.get('authenticity_id') or None
        acquisition_method_id = request.POST.get('acquisition_method_id') or None
        acquisition_date = request.POST.get('acquisition_date')
        source_of_acquisition = request.POST.get('source_of_acquisition')
        document_reference = request.POST.get('document_reference')
        location_in_museum = request.POST.get('location_in_museum')
        condition = request.POST.get('condition')
        description = request.POST.get('description')
        is_on_display = request.POST.get('is_on_display') == 'on'
        
        # Получаем файл
        photo_file = request.FILES.get('photo')
        
        # Диагностика
        print(f"=== ДИАГНОСТИКА ЗАГРУЗКИ ФАЙЛА ===")
        print(f"Файл получен: {photo_file.name if photo_file else 'Нет файла'}")
        print(f"IS_PRODUCTION: {settings.IS_PRODUCTION}")
        print(f"MEDIA_URL: {settings.MEDIA_URL}")
        
        # Базовая валидация
        errors = []
        if not inventory_number:
            errors.append('Инвентарный номер обязателен')
        if not exhibit_name:
            errors.append('Название экспоната обязательно')
        if not acquisition_date:
            errors.append('Дата поступления обязательна')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('add_exhibit')
        
        # ПОДГОТАВЛИВАЕМ ФАЙЛ ДО СОХРАНЕНИЯ ЭКСПОНАТА
        saved_photo_path = None
        if photo_file:
            # Валидация файла
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            ext = os.path.splitext(photo_file.name)[1].lower()
            
            if ext not in valid_extensions:
                messages.error(request, f'Неподдерживаемый формат файла. Разрешены: {", ".join(valid_extensions)}')
                return redirect('add_exhibit')
            
            if photo_file.size > 5 * 1024 * 1024:
                messages.error(request, 'Файл слишком большой. Максимальный размер: 5 МБ')
                return redirect('add_exhibit')
            
            # Генерируем уникальное имя файла
            filename = f"exhibits/{inventory_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
            print(f"Попытка сохранить файл: {filename}")
            
            try:
                # ПРИНУДИТЕЛЬНО создаём storage с настройками из settings
                from storages.backends.s3boto3 import S3Boto3Storage
                
                s3_storage = S3Boto3Storage(
                    bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                    access_key=settings.AWS_ACCESS_KEY_ID,
                    secret_key=settings.AWS_SECRET_ACCESS_KEY,
                    default_acl='public-read',
                )
                
                # Сохраняем файл
                saved_photo_path = s3_storage.save(filename, ContentFile(photo_file.read()))
                print(f"Файл сохранён через S3Boto3Storage: {saved_photo_path}")
                
                # Проверяем существование
                if s3_storage.exists(saved_photo_path):
                    print(f"✅ Файл подтверждён в хранилище")
                else:
                    print(f"❌ Файл НЕ найден после сохранения!")
                    saved_photo_path = None
                    
            except Exception as e:
                print(f"❌ Ошибка при сохранении файла: {e}")
                messages.error(request, f'Ошибка при сохранении фото: {e}')
                return redirect('add_exhibit')
        
        try:
            with connection.cursor() as cursor:
                # Проверяем уникальность инвентарного номера
                cursor.execute("""
                    SELECT id, exhibit_name FROM exhibits WHERE inventory_number = %s
                """, [inventory_number])
                existing = cursor.fetchone()
                
                if existing:
                    messages.error(request, f'Экспонат с инвентарным номером "{inventory_number}" уже существует: "{existing[1]}"')
                    return redirect('add_exhibit')
                
                # Вставляем новый экспонат
                cursor.execute("""
                    INSERT INTO exhibits (
                        inventory_number, object_code, exhibit_name, author_id, dating,
                        material_id, technique_id, dimensions, weight, authenticity_id,
                        acquisition_method_id, acquisition_date, source_of_acquisition,
                        document_reference, location_in_museum, condition, description,
                        is_on_display, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, [inventory_number, object_code, exhibit_name, author_id, dating,
                      material_id, technique_id, dimensions, weight, authenticity_id,
                      acquisition_method_id, acquisition_date, source_of_acquisition,
                      document_reference, location_in_museum, condition, description,
                      is_on_display])

                cursor.execute("SELECT LASTVAL()")
                exhibit_id = cursor.fetchone()[0]
                print(f"Экспонат создан с ID: {exhibit_id}")

                # Сохраняем путь к фото в БД
                if saved_photo_path:
                    cursor.execute("""
                        INSERT INTO exhibit_photos (exhibit_id, photo_path, is_main, uploaded_at)
                        VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
                    """, [exhibit_id, saved_photo_path])
                    print(f"Путь к фото сохранён в БД: {saved_photo_path}")

            messages.success(request, 'Экспонат успешно добавлен')
            return redirect('exhibit_list')
            
        except Exception as e:
            error_message = str(e)
            print(f"❌ Ошибка при сохранении экспоната: {error_message}")
            messages.error(request, f'Ошибка при сохранении: {error_message}')
            return redirect('add_exhibit')
    
    # GET запрос - показываем форму
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, full_name FROM authors ORDER BY full_name")
        authors = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM materials ORDER BY name")
        materials = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM techniques ORDER BY name")
        techniques = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, authenticity_name FROM authenticity_types ORDER BY authenticity_name")
        authenticities = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, method_name FROM acquisition_methods ORDER BY method_name")
        methods = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    
    context = {
        'authors': authors,
        'materials': materials,
        'techniques': techniques,
        'authenticities': authenticities,
        'methods': methods,
    }
    return render(request, 'add_exhibit.html', context)


@login_required
def management_menu(request):
    """Меню управления"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM exhibit_history 
            WHERE event_type = 'restoration' 
            AND event_date >= CURRENT_DATE - INTERVAL '30 days'
        """)
        restoration_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'exhibitions'
            )
        """)
        has_exhibitions_table = cursor.fetchone()[0]
        
        active_exhibitions = 0
        if has_exhibitions_table:
            cursor.execute("SELECT COUNT(*) FROM exhibitions WHERE is_active = true")
            active_exhibitions = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM exhibit_history 
            WHERE event_type = 'write_off' 
            AND EXTRACT(YEAR FROM event_date) = EXTRACT(YEAR FROM CURRENT_DATE)
        """)
        recent_write_offs = cursor.fetchone()[0]
    
    context = {
        'restoration_count': restoration_count,
        'active_exhibitions': active_exhibitions,
        'recent_write_offs': recent_write_offs,
    }
    return render(request, 'management/menu.html', context)


@login_required
def restoration_list(request):
    """Список реставраций"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                eh.id,
                e.id as exhibit_id,
                e.exhibit_name,
                e.inventory_number,
                eh.event_date as start_date,
                eh.description,
                eh.document_reference,
                eh.created_at
            FROM exhibit_history eh
            JOIN exhibits e ON e.id = eh.exhibit_id
            WHERE eh.event_type = 'restoration'
            ORDER BY eh.event_date DESC
        """)
        columns = [col[0] for col in cursor.description]
        restorations = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    context = {
        'restorations': restorations,
    }
    return render(request, 'management/restoration_list.html', context)


@login_required
def add_restoration(request):
    if request.method == 'POST':
        exhibit_id = request.POST.get('exhibit')
        start_date = request.POST.get('start_date')
        description = request.POST.get('description')
        document_reference = request.POST.get('document_reference', '')
        
        # Дополнительные поля
        end_date = request.POST.get('end_date', None) or None
        restorer_name = request.POST.get('restorer_name', '')
        materials_used = request.POST.get('materials_used', '')
        condition_before = request.POST.get('condition_before', '')
        condition_after = request.POST.get('condition_after', '')
        
        # Вставляем запись о реставрации
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO restorations (
                    exhibit_id, start_date, end_date, restorer_name, 
                    description, materials_used, condition_before, 
                    condition_after, document_reference, created_by_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, [
                exhibit_id, start_date, end_date, restorer_name,
                description, materials_used, condition_before,
                condition_after, document_reference, request.user.id,
                datetime.now()
            ])
            restoration_id = cursor.fetchone()[0]
        
        messages.success(request, 'Реставрация успешно добавлена!')
        
        # Проверяем, нужно ли скачать PDF
        if 'save_and_download' in request.POST:
            return redirect('download_restoration_pdf', restoration_id=restoration_id)
        
        return redirect('restoration_list')
    
    # GET запрос - получаем список экспонатов для формы
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, exhibit_name, inventory_number 
            FROM exhibits 
            ORDER BY exhibit_name
        """)
        exhibits = cursor.fetchall()
    
    # Преобразуем в список словарей для удобства в шаблоне
    exhibits_list = []
    for row in exhibits:
        exhibits_list.append({
            'id': row[0],
            'exhibit_name': row[1],
            'inventory_number': row[2]
        })
    
    return render(request, 'management/add_restoration.html', {
        'exhibits': exhibits_list
    })

@login_required
def download_restoration_pdf(request, restoration_id):
    # Получаем данные о реставрации и экспонате
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                r.id,
                r.exhibit_id,
                r.start_date,
                r.end_date,
                r.restorer_name,
                r.description,
                r.materials_used,
                r.condition_before,
                r.condition_after,
                r.document_reference,
                r.created_at,
                e.inventory_number,
                e.exhibit_name,
                e.dating,
                e.dimensions,
                COALESCE(a.full_name, 'Не указан') as author_name,
                COALESCE(m.name, 'Не указан') as material_name,
                COALESCE(t.name, 'Не указана') as technique_name
            FROM restorations r
            JOIN exhibits e ON r.exhibit_id = e.id
            LEFT JOIN authors a ON e.author_id = a.id
            LEFT JOIN materials m ON e.material_id = m.id
            LEFT JOIN techniques t ON e.technique_id = t.id
            WHERE r.id = %s
        """, [restoration_id])
        
        row = cursor.fetchone()
    
    if not row:
        messages.error(request, 'Реставрация не найдена')
        return redirect('restoration_list')
    
    # Создаем простой словарь с данными
    restoration_data = {
        'id': row[0],
        'exhibit_id': row[1],
        'start_date': row[2],
        'end_date': row[3],
        'restorer_name': row[4] or '',
        'description': row[5] or '',
        'materials_used': row[6] or '',
        'condition_before': row[7] or '',
        'condition_after': row[8] or '',
        'document_reference': row[9] or '',
        'created_at': row[10],
        'inventory_number': row[11],
        'exhibit_name': row[12],
        'dating': row[13] or '',
        'dimensions': row[14] or '',
        'author_name': row[15],
        'material_name': row[16],
        'technique_name': row[17],
    }
    
    # Генерируем PDF
    from .pdf_generator_simple import generate_simple_restoration_pdf
    pdf_buffer = generate_simple_restoration_pdf(restoration_data)
    
    return FileResponse(
        pdf_buffer,
        as_attachment=True,
        filename=f'restoration_act_{restoration_id}_{datetime.now().strftime("%Y%m%d")}.pdf'
    )


@login_required
def exhibition_list(request):
    """Список выставок"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'exhibitions'
            )
        """)
        has_table = cursor.fetchone()[0]
        
        if not has_table:
            cursor.execute("""
                CREATE TABLE exhibitions (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    location VARCHAR(255),
                    curator VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by_id INTEGER
                )
            """)
            
            cursor.execute("""
                CREATE TABLE exhibition_exhibits (
                    exhibition_id INTEGER REFERENCES exhibitions(id) ON DELETE CASCADE,
                    exhibit_id INTEGER REFERENCES exhibits(id) ON DELETE CASCADE,
                    PRIMARY KEY (exhibition_id, exhibit_id)
                )
            """)
        
        show_all = request.GET.get('show_all')
        if show_all:
            cursor.execute("""
                SELECT 
                    e.*,
                    (SELECT COUNT(*) FROM exhibition_exhibits ee WHERE ee.exhibition_id = e.id) as exhibits_count
                FROM exhibitions e
                ORDER BY e.start_date DESC
            """)
        else:
            cursor.execute("""
                SELECT 
                    e.*,
                    (SELECT COUNT(*) FROM exhibition_exhibits ee WHERE ee.exhibition_id = e.id) as exhibits_count
                FROM exhibitions e
                WHERE e.is_active = true
                ORDER BY e.start_date DESC
            """)
        
        columns = [col[0] for col in cursor.description]
        exhibitions = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    context = {
        'exhibitions': exhibitions,
        'show_all': show_all,
    }
    return render(request, 'management/exhibition_list.html', context)


@login_required
def add_exhibition(request):
    """Добавление выставки"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        location = request.POST.get('location')
        curator = request.POST.get('curator')
        is_active = request.POST.get('is_active') == 'on'
        notes = request.POST.get('notes', '')
        exhibit_ids = request.POST.getlist('exhibits')
        
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO exhibitions 
                (name, description, start_date, end_date, location, curator, is_active, notes, created_by_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, [name, description, start_date, end_date, location, curator, is_active, notes, request.user.id])
            
            exhibition_id = cursor.fetchone()[0]
            
            for exhibit_id in exhibit_ids:
                cursor.execute("""
                    INSERT INTO exhibition_exhibits (exhibition_id, exhibit_id)
                    VALUES (%s, %s)
                """, [exhibition_id, exhibit_id])
                
                cursor.execute("""
                    INSERT INTO exhibit_history 
                    (exhibit_id, event_date, event_type, description, created_at)
                    VALUES (%s, %s, 'exhibition', %s, CURRENT_TIMESTAMP)
                """, [exhibit_id, datetime.now().date(), f'Включен в выставку: {name}'])
            
            messages.success(request, 'Выставка успешно создана')
        
        return redirect('exhibition_list')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, exhibit_name, inventory_number 
            FROM exhibits 
            ORDER BY exhibit_name
        """)
        columns = [col[0] for col in cursor.description]
        exhibits = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    context = {
        'exhibits': exhibits,
    }
    return render(request, 'management/add_exhibition.html', context)


@login_required
def write_off_list(request):
    """Список списаний"""
    search_query = request.GET.get('search', '')
    
    with connection.cursor() as cursor:
        if search_query:
            cursor.execute("""
                SELECT 
                    eh.id,
                    e.id as exhibit_id,
                    e.exhibit_name,
                    e.inventory_number,
                    eh.event_date as write_off_date,
                    eh.description as reason_description,
                    eh.document_reference,
                    eh.created_at
                FROM exhibit_history eh
                JOIN exhibits e ON e.id = eh.exhibit_id
                WHERE eh.event_type = 'write_off'
                AND (e.exhibit_name ILIKE %s OR e.inventory_number ILIKE %s OR eh.document_reference ILIKE %s)
                ORDER BY eh.event_date DESC
            """, [f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])
        else:
            cursor.execute("""
                SELECT 
                    eh.id,
                    e.id as exhibit_id,
                    e.exhibit_name,
                    e.inventory_number,
                    eh.event_date as write_off_date,
                    eh.description as reason_description,
                    eh.document_reference,
                    eh.created_at
                FROM exhibit_history eh
                JOIN exhibits e ON e.id = eh.exhibit_id
                WHERE eh.event_type = 'write_off'
                ORDER BY eh.event_date DESC
            """)
        
        columns = [col[0] for col in cursor.description]
        write_offs = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    context = {
        'write_offs': write_offs,
        'search_query': search_query,
    }
    return render(request, 'management/write_off_list.html', context)


@login_required
def add_write_off(request):
    """Добавление списания с генерацией PDF"""
    if request.method == 'POST':
        exhibit_id = request.POST.get('exhibit')
        write_off_date = request.POST.get('write_off_date')
        reason = request.POST.get('reason')
        reason_description = request.POST.get('reason_description')
        document_reference = request.POST.get('document_reference')
        
        reason_text = f"{reason}: {reason_description}"
        
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO exhibit_history 
                (exhibit_id, event_date, event_type, description, document_reference, created_at)
                VALUES (%s, %s, 'write_off', %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, [exhibit_id, write_off_date, reason_text, document_reference])
            
            write_off_id = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT 
                    e.exhibit_name,
                    e.inventory_number,
                    e.object_code,
                    e.dating,
                    e.dimensions,
                    e.location_in_museum,
                    a.full_name as author
                FROM exhibits e
                LEFT JOIN authors a ON e.author_id = a.id
                WHERE e.id = %s
            """, [exhibit_id])
            
            row = cursor.fetchone()
            if row:
                exhibit_data = {
                    'Название': row[0],
                    'Инвентарный номер': row[1],
                    'Учетный шифр': row[2] or '—',
                    'Датировка': row[3] or '—',
                    'Размеры': row[4] or '—',
                    'Место хранения': row[5] or '—',
                    'Автор': row[6] or 'Неизвестен',
                }
                
                pdf_path = generate_write_off_act(
                    request, 
                    write_off_id, 
                    exhibit_data, 
                    reason_text, 
                    write_off_date, 
                    document_reference
                )
                
                messages.success(request, f'Списание оформлено. Акт сохранён: {pdf_path}')
            else:
                messages.success(request, 'Списание успешно добавлено')
        
        return redirect('write_off_list')
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, exhibit_name, inventory_number 
            FROM exhibits 
            ORDER BY exhibit_name
        """)
        columns = [col[0] for col in cursor.description]
        exhibits = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    context = {
        'exhibits': exhibits,
    }
    return render(request, 'management/add_write_off.html', context)


@login_required
def exhibit_detail(request, exhibit_id):
    """Детальная информация об экспонате"""
    from django.conf import settings
    
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
        
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
        if not row:
            messages.error(request, 'Экспонат не найден')
            return redirect('exhibit_list')
        exhibit = dict(zip(columns, row))
        
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
        
        cursor.execute("""
            SELECT photo_path, is_main, description, uploaded_at
            FROM exhibit_photos 
            WHERE exhibit_id = %s
            ORDER BY is_main DESC, uploaded_at DESC
        """, [exhibit_id])
        
        # 🔧 ИСПРАВЛЕНО: правильно формируем полные URL для фото
        photos = []
        for row in cursor.fetchall():
            photo_path = row[0]
            if photo_path:
                # Если путь не начинается с http, добавляем MEDIA_URL
                if not photo_path.startswith(('http://', 'https://')):
                    photo_path = settings.MEDIA_URL + photo_path
            photos.append({
                'photo_path': photo_path,
                'is_main': row[1],
                'description': row[2],
                'uploaded_at': row[3]
            })
        
        cursor.execute("""
            SELECT event_date, event_type, description, document_reference, created_at
            FROM exhibit_history
            WHERE exhibit_id = %s
            ORDER BY event_date DESC, created_at DESC
        """, [exhibit_id])
        history = []
        for row in cursor.fetchall():
            history.append({
                'event_date': row[0],
                'event_type': row[1],
                'description': row[2],
                'document_reference': row[3],
                'created_at': row[4]
            })
    
    context = {
        'exhibit': exhibit,
        'photos': photos,
        'history': history,
        'MEDIA_URL': settings.MEDIA_URL,  # ← ДОБАВЛЯЕМ MEDIA_URL В КОНТЕКСТ
    }
    return render(request, 'exhibit_detail.html', context)


@login_required
def edit_exhibit(request, exhibit_id):
    """Редактирование экспоната"""
    if request.method == 'POST':
        inventory_number = request.POST.get('inventory_number')
        object_code = request.POST.get('object_code')
        exhibit_name = request.POST.get('exhibit_name')
        author_id = request.POST.get('author_id') or None
        dating = request.POST.get('dating')
        material_id = request.POST.get('material_id') or None
        technique_id = request.POST.get('technique_id') or None
        dimensions = request.POST.get('dimensions')
        weight = request.POST.get('weight') or None
        authenticity_id = request.POST.get('authenticity_id') or None
        acquisition_method_id = request.POST.get('acquisition_method_id') or None
        acquisition_date = request.POST.get('acquisition_date')
        source_of_acquisition = request.POST.get('source_of_acquisition')
        document_reference = request.POST.get('document_reference')
        location_in_museum = request.POST.get('location_in_museum')
        condition = request.POST.get('condition')
        description = request.POST.get('description')
        is_on_display = request.POST.get('is_on_display') == 'on'
        photo_url = request.POST.get('photo_url')
        
        # Базовая валидация
        errors = []
        if not inventory_number:
            errors.append('Инвентарный номер обязателен')
        if not exhibit_name:
            errors.append('Название экспоната обязательно')
        if not acquisition_date:
            errors.append('Дата поступления обязательна')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('edit_exhibit', exhibit_id=exhibit_id)
        
        try:
            with connection.cursor() as cursor:
                # Проверяем уникальность инвентарного номера (исключая текущий экспонат)
                cursor.execute("""
                    SELECT id, exhibit_name FROM exhibits 
                    WHERE inventory_number = %s AND id != %s
                """, [inventory_number, exhibit_id])
                existing = cursor.fetchone()
                
                if existing:
                    messages.error(request, f'Экспонат с инвентарным номером "{inventory_number}" уже существует: "{existing[1]}"')
                    
                    # Получаем данные для формы
                    with connection.cursor() as cursor2:
                        cursor2.execute("SELECT id, full_name FROM authors ORDER BY full_name")
                        authors = [dict(zip([col[0] for col in cursor2.description], row)) for row in cursor2.fetchall()]
                        
                        cursor2.execute("SELECT id, name FROM materials ORDER BY name")
                        materials = [dict(zip([col[0] for col in cursor2.description], row)) for row in cursor2.fetchall()]
                        
                        cursor2.execute("SELECT id, name FROM techniques ORDER BY name")
                        techniques = [dict(zip([col[0] for col in cursor2.description], row)) for row in cursor2.fetchall()]
                        
                        cursor2.execute("SELECT id, authenticity_name FROM authenticity_types ORDER BY authenticity_name")
                        authenticities = [dict(zip([col[0] for col in cursor2.description], row)) for row in cursor2.fetchall()]
                        
                        cursor2.execute("SELECT id, method_name FROM acquisition_methods ORDER BY method_name")
                        methods = [dict(zip([col[0] for col in cursor2.description], row)) for row in cursor2.fetchall()]
                    
                    context = {
                        'authors': authors,
                        'materials': materials,
                        'techniques': techniques,
                        'authenticities': authenticities,
                        'methods': methods,
                        'exhibit_id': exhibit_id,
                        'is_edit': True,
                        'form_data': {
                            'inventory_number': inventory_number,
                            'object_code': object_code,
                            'exhibit_name': exhibit_name,
                            'author_id': author_id,
                            'dating': dating,
                            'material_id': material_id,
                            'technique_id': technique_id,
                            'dimensions': dimensions,
                            'weight': weight,
                            'authenticity_id': authenticity_id,
                            'acquisition_method_id': acquisition_method_id,
                            'acquisition_date': acquisition_date,
                            'source_of_acquisition': source_of_acquisition,
                            'document_reference': document_reference,
                            'location_in_museum': location_in_museum,
                            'condition': condition,
                            'description': description,
                            'is_on_display': request.POST.get('is_on_display') == 'on',
                            'photo_url': photo_url,
                        }
                    }
                    return render(request, 'edit_exhibit.html', context)
                
                # Обновляем экспонат
                cursor.execute("""
                    UPDATE exhibits SET
                        inventory_number = %s,
                        object_code = %s,
                        exhibit_name = %s,
                        author_id = %s,
                        dating = %s,
                        material_id = %s,
                        technique_id = %s,
                        dimensions = %s,
                        weight = %s,
                        authenticity_id = %s,
                        acquisition_method_id = %s,
                        acquisition_date = %s,
                        source_of_acquisition = %s,
                        document_reference = %s,
                        location_in_museum = %s,
                        condition = %s,
                        description = %s,
                        is_on_display = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, [inventory_number, object_code, exhibit_name, author_id, dating,
                      material_id, technique_id, dimensions, weight, authenticity_id,
                      acquisition_method_id, acquisition_date, source_of_acquisition,
                      document_reference, location_in_museum, condition, description,
                      is_on_display, exhibit_id])
                
                # Обновляем фото, если указано
                if photo_url:
                    # Проверяем, есть ли уже главное фото
                    cursor.execute("""
                        SELECT id FROM exhibit_photos 
                        WHERE exhibit_id = %s AND is_main = TRUE
                    """, [exhibit_id])
                    existing_photo = cursor.fetchone()
                    
                    if existing_photo:
                        # Обновляем существующее фото
                        cursor.execute("""
                            UPDATE exhibit_photos SET photo_path = %s, uploaded_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, [photo_url, existing_photo[0]])
                    else:
                        # Добавляем новое фото
                        cursor.execute("""
                            INSERT INTO exhibit_photos (exhibit_id, photo_path, is_main, uploaded_at)
                            VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
                        """, [exhibit_id, photo_url])

            messages.success(request, 'Экспонат успешно обновлён')
            return redirect('exhibit_detail', exhibit_id=exhibit_id)
            
        except Exception as e:
            error_message = str(e)
            messages.error(request, f'Ошибка при обновлении: {error_message}')
            return redirect('edit_exhibit', exhibit_id=exhibit_id)
    
    # GET запрос - загружаем данные экспоната
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                e.*,
                a.full_name as author_name
            FROM exhibits e
            LEFT JOIN authors a ON e.author_id = a.id
            WHERE e.id = %s
        """, [exhibit_id])
        
        row = cursor.fetchone()
        if not row:
            messages.error(request, 'Экспонат не найден')
            return redirect('exhibit_list')
        
        columns = [col[0] for col in cursor.description]
        exhibit = dict(zip(columns, row))
        
        # Получаем списки для выпадающих меню
        cursor.execute("SELECT id, full_name FROM authors ORDER BY full_name")
        authors = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM materials ORDER BY name")
        materials = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM techniques ORDER BY name")
        techniques = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, authenticity_name FROM authenticity_types ORDER BY authenticity_name")
        authenticities = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, method_name FROM acquisition_methods ORDER BY method_name")
        methods = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        # Получаем главное фото
        cursor.execute("""
            SELECT photo_path FROM exhibit_photos 
            WHERE exhibit_id = %s AND is_main = TRUE 
            LIMIT 1
        """, [exhibit_id])
        photo_row = cursor.fetchone()
        exhibit['main_photo'] = photo_row[0] if photo_row else ''
    
    # Форматируем даты для формы
    if exhibit.get('acquisition_date'):
        if hasattr(exhibit['acquisition_date'], 'strftime'):
            exhibit['acquisition_date'] = exhibit['acquisition_date'].strftime('%Y-%m-%d')
        elif isinstance(exhibit['acquisition_date'], str):
            exhibit['acquisition_date'] = str(exhibit['acquisition_date'])[:10]
    
    context = {
        'authors': authors,
        'materials': materials,
        'techniques': techniques,
        'authenticities': authenticities,
        'methods': methods,
        'exhibit_id': exhibit_id,
        'is_edit': True,
        'form_data': {
            'inventory_number': exhibit.get('inventory_number', ''),
            'object_code': exhibit.get('object_code', ''),
            'exhibit_name': exhibit.get('exhibit_name', ''),
            'author_id': str(exhibit.get('author_id')) if exhibit.get('author_id') else '',
            'author_name': exhibit.get('author_name', ''),
            'dating': exhibit.get('dating', ''),
            'material_id': str(exhibit.get('material_id')) if exhibit.get('material_id') else '',
            'technique_id': str(exhibit.get('technique_id')) if exhibit.get('technique_id') else '',
            'dimensions': exhibit.get('dimensions', ''),
            'weight': exhibit.get('weight', ''),
            'authenticity_id': str(exhibit.get('authenticity_id')) if exhibit.get('authenticity_id') else '',
            'acquisition_method_id': str(exhibit.get('acquisition_method_id')) if exhibit.get('acquisition_method_id') else '',
            'acquisition_date': exhibit.get('acquisition_date', ''),
            'source_of_acquisition': exhibit.get('source_of_acquisition', ''),
            'document_reference': exhibit.get('document_reference', ''),
            'location_in_museum': exhibit.get('location_in_museum', ''),
            'condition': exhibit.get('condition', ''),
            'description': exhibit.get('description', ''),
            'is_on_display': exhibit.get('is_on_display', False),
            'photo_url': exhibit.get('main_photo', ''),
        }
    }
    return render(request, 'edit_exhibit.html', context)