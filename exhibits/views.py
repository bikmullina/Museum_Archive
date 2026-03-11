from datetime import datetime
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from django.http import FileResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import connection
from django.contrib.auth import authenticate, login


from django.contrib.auth import authenticate, login

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
    """Список всех экспонатов с поиском по названию"""
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
        
        # Для каждого экспоната получаем авторов и материалы
        for exhibit in exhibits:
            # Получаем авторов
            cursor.execute("""
                SELECT a.full_name 
                FROM authors a
                JOIN exhibits e ON e.author_id = a.id
                WHERE e.id = %s
            """, [exhibit['id']])
            author_row = cursor.fetchone()
            exhibit['author_name'] = author_row[0] if author_row else 'Неизвестен'
            
            # Получаем материалы (может быть несколько)
            cursor.execute("""
                SELECT m.name 
                FROM materials m
                JOIN exhibit_materials em ON m.id = em.material_id
                WHERE em.exhibit_id = %s
                ORDER BY m.name
            """, [exhibit['id']])
            materials = cursor.fetchall()
            if materials:
                # Объединяем все материалы через запятую
                exhibit['material_names'] = ', '.join([m[0] for m in materials])
            else:
                # Если нет в exhibit_materials, пробуем получить из material_id
                cursor.execute("""
                    SELECT m.name 
                    FROM materials m
                    JOIN exhibits e ON e.material_id = m.id
                    WHERE e.id = %s
                """, [exhibit['id']])
                material_row = cursor.fetchone()
                exhibit['material_names'] = material_row[0] if material_row else 'Не указан'
            
            # Получаем фото
            cursor.execute("""
                SELECT photo_path FROM exhibit_photos 
                WHERE exhibit_id = %s AND is_main = TRUE 
                LIMIT 1
            """, [exhibit['id']])
            photo_row = cursor.fetchone()
            exhibit['main_photo'] = photo_row[0] if photo_row else None
    
    return render(request, 'exhibit_list.html', {
        'exhibits': exhibits,
        'search_query': search_query,
    })

# Существующее представление для добавления экспоната
@login_required
def add_exhibit(request):
    """Добавление нового экспоната"""
    if request.method == 'POST':
        # Получаем данные из формы
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
        
        with connection.cursor() as cursor:
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

            # После добавления экспоната получаем его ID
            cursor.execute("SELECT LASTVAL()")
            exhibit_id = cursor.fetchone()[0]

            # Сохраняем фото, если ссылка передана
            if photo_url:
                cursor.execute("""
                    INSERT INTO exhibit_photos (exhibit_id, photo_path, is_main, uploaded_at)
                    VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
                """, [exhibit_id, photo_url])

        messages.success(request, 'Экспонат успешно добавлен')
        return redirect('exhibit_list')
    
    # Получаем данные для выпадающих списков
    with connection.cursor() as cursor:
        # Авторы
        cursor.execute("SELECT id, full_name FROM authors ORDER BY full_name")
        authors = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        # Материалы
        cursor.execute("SELECT id, name FROM materials ORDER BY name")
        materials = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        # Техники
        cursor.execute("SELECT id, name FROM techniques ORDER BY name")
        techniques = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        # Типы подлинности
        cursor.execute("SELECT id, authenticity_name FROM authenticity_types ORDER BY authenticity_name")
        authenticities = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        
        # Способы поступления
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

# Новые представления для управления
@login_required
def management_menu(request):
    """Меню управления"""
    with connection.cursor() as cursor:
        # Количество реставраций
        cursor.execute("""
            SELECT COUNT(*) FROM exhibit_history 
            WHERE event_type = 'restoration' 
            AND event_date >= CURRENT_DATE - INTERVAL '30 days'
        """)
        restoration_count = cursor.fetchone()[0]
        
        # Проверяем, существует ли таблица exhibitions
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
        
        # Количество списаний в этом году
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


# Реставрация
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
    """Добавление реставрации"""
    if request.method == 'POST':
        exhibit_id = request.POST.get('exhibit')
        start_date = request.POST.get('start_date')
        description = request.POST.get('description')
        document = request.POST.get('document_reference', '')
        
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO exhibit_history 
                (exhibit_id, event_date, event_type, description, document_reference, created_at)
                VALUES (%s, %s, 'restoration', %s, %s, CURRENT_TIMESTAMP)
            """, [exhibit_id, start_date, description, document])
            
            messages.success(request, 'Реставрация успешно добавлена')
        
        return redirect('restoration_list')
    
    # Получаем список экспонатов
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
    return render(request, 'management/add_restoration.html', context)


# Выставки
@login_required
def exhibition_list(request):
    """Список выставок"""
    # Проверяем, существует ли таблица exhibitions
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'exhibitions'
            )
        """)
        has_table = cursor.fetchone()[0]
        
        if not has_table:
            # Создаем таблицу выставок
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
            
            # Создаем таблицу связи выставок с экспонатами
            cursor.execute("""
                CREATE TABLE exhibition_exhibits (
                    exhibition_id INTEGER REFERENCES exhibitions(id) ON DELETE CASCADE,
                    exhibit_id INTEGER REFERENCES exhibits(id) ON DELETE CASCADE,
                    PRIMARY KEY (exhibition_id, exhibit_id)
                )
            """)
        
        # Получаем список выставок
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
            # Вставляем выставку
            cursor.execute("""
                INSERT INTO exhibitions 
                (name, description, start_date, end_date, location, curator, is_active, notes, created_by_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, [name, description, start_date, end_date, location, curator, is_active, notes, request.user.id])
            
            exhibition_id = cursor.fetchone()[0]
            
            # Добавляем связи с экспонатами
            for exhibit_id in exhibit_ids:
                cursor.execute("""
                    INSERT INTO exhibition_exhibits (exhibition_id, exhibit_id)
                    VALUES (%s, %s)
                """, [exhibition_id, exhibit_id])
                
                # Добавляем запись в историю экспоната
                cursor.execute("""
                    INSERT INTO exhibit_history 
                    (exhibit_id, event_date, event_type, description, created_at)
                    VALUES (%s, %s, 'exhibition', %s, CURRENT_TIMESTAMP)
                """, [exhibit_id, datetime.now().date(), f'Включен в выставку: {name}'])
            
            messages.success(request, 'Выставка успешно создана')
        
        return redirect('exhibition_list')
    
    # Получаем список экспонатов
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


# Списание
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
            # Вставляем запись о списании
            cursor.execute("""
                INSERT INTO exhibit_history 
                (exhibit_id, event_date, event_type, description, document_reference, created_at)
                VALUES (%s, %s, 'write_off', %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, [exhibit_id, write_off_date, reason_text, document_reference])
            
            write_off_id = cursor.fetchone()[0]
            
            # Получаем данные экспоната для акта
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
                print("="*50)
                print("Данные из БД:")
                print(f"row[0] (Название): {row[0]}")
                print(f"row[1] (Инв. номер): {row[1]}")
                print(f"row[2] (Учетный шифр): {row[2]}")
                print(f"row[3] (Датировка): {row[3]}")
                print(f"row[4] (Размеры): {row[4]}")
                print(f"row[5] (Место хранения): {row[5]}")
                print(f"row[6] (Автор): {row[6]}")
                print("exhibit_data:", exhibit_data)
                print("reason_text:", reason_text)
                print("write_off_date:", write_off_date)
                print("document_reference:", document_reference)
                print("="*50)
                # Генерируем PDF
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
    
    # Получаем список экспонатов
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
    with connection.cursor() as cursor:
        # Основная информация об экспонате
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
        
        # Получаем историю экспоната (поступления, перемещения, реставрации)
        cursor.execute("""
            SELECT event_date, event_type, description, document_reference, created_at
            FROM exhibit_history
            WHERE exhibit_id = %s
            ORDER BY event_date DESC, created_at DESC
        """, [exhibit_id])
        history = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    
    context = {
        'exhibit': exhibit,
        'photos': photos,
        'history': history,
    }
    return render(request, 'exhibit_detail.html', context)


# 👇 ЭТА ФУНКЦИЯ ДОЛЖНА БЫТЬ ЗДЕСЬ (на одном уровне с exhibit_detail, НЕ внутри неё)
def generate_write_off_act(request, write_off_id, exhibit_data, reason_text, date, document):
    """Генерация PDF акта списания"""
    # Создаём папку для актов, если её нет
    acts_dir = os.path.join('media', 'write_off_acts')
    os.makedirs(acts_dir, exist_ok=True)
    
    # Имя файла: act_списание_дата_время.pdf
    filename = f"act_write_off_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(acts_dir, filename)
    
    # Создаём PDF
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    
    # Заголовок
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "АКТ О СПИСАНИИ МУЗЕЙНОГО ПРЕДМЕТА")
    
    # Дата и номер
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Дата составления: {date}")
    c.drawString(50, height - 100, f"Номер документа: {document if document else 'б/н'}")
    
    # Линия-разделитель
    c.line(50, height - 115, width - 50, height - 115)
    
    # Информация об экспонате
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 140, "Сведения об экспонате:")
    
    c.setFont("Helvetica", 12)
    y = height - 170
    for key, value in exhibit_data.items():
        c.drawString(70, y, f"{key}: {value}")
        y -= 20
    
    # Причина списания
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y - 20, "Причина списания:")
    c.setFont("Helvetica", 12)
    
    # Разбиваем длинный текст на строки
    reason_lines = reason_text.split('\n')
    y -= 50
    for line in reason_lines:
        if len(line) > 80:
            words = line.split(' ')
            current_line = ''
            for word in words:
                if len(current_line + ' ' + word) < 80:
                    current_line += ' ' + word if current_line else word
                else:
                    c.drawString(70, y, current_line)
                    y -= 20
                    current_line = word
            if current_line:
                c.drawString(70, y, current_line)
                y -= 20
        else:
            c.drawString(70, y, line)
            y -= 20
    
    # Подписи
    y -= 40
    c.line(70, y, 200, y)
    c.drawString(70, y - 20, "Директор музея")
    
    c.line(300, y, 430, y)
    c.drawString(300, y - 20, "Главный хранитель")
    
    c.line(70, y - 60, 200, y - 60)
    c.drawString(70, y - 80, "Ответственный сотрудник")
    
    # Сохраняем PDF
    c.save()
    
    return filepath