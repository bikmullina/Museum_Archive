import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

def register_fonts():
    """Регистрация шрифтов для кириллицы"""
    try:
        # Пробуем разные пути для шрифтов Windows
        font_paths = [
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/times.ttf',
            'C:/Windows/Fonts/calibri.ttf',
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('CustomFont', font_path))
                return
        # Если шрифт не найден, используем стандартный
        pdfmetrics.registerFont(TTFont('CustomFont', 'Helvetica'))
    except:
        pass

def generate_simple_restoration_pdf(data):
    """Генерация PDF-акта реставрации"""
    register_fonts()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
    )
    
    styles = getSampleStyleSheet()
    
    # Создаем стили для кириллицы
    title_style = ParagraphStyle(
        'RussianTitle',
        parent=styles['Heading1'],
        fontName='CustomFont',
        fontSize=16,
        alignment=1,  # Центр
        spaceAfter=20,
        textColor=colors.HexColor('#79443B')
    )
    
    heading_style = ParagraphStyle(
        'RussianHeading',
        parent=styles['Heading2'],
        fontName='CustomFont',
        fontSize=12,
        alignment=0,
        spaceAfter=10,
        spaceBefore=10,
        textColor=colors.HexColor('#79443B')
    )
    
    normal_style = ParagraphStyle(
        'RussianNormal',
        parent=styles['Normal'],
        fontName='CustomFont',
        fontSize=10,
        alignment=0,
        spaceAfter=6,
        leading=14
    )
    
    story = []
    
    # Заголовок
    story.append(Paragraph("АКТ РЕСТАВРАЦИИ", title_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"№ {data['id']} от {datetime.now().strftime('%d.%m.%Y')}", normal_style))
    story.append(Spacer(1, 20))
    
    # Информация об экспонате
    story.append(Paragraph("1. ИНФОРМАЦИЯ ОБ ЭКСПОНАТЕ", heading_style))
    
    # Обработка дат
    start_date_str = data['start_date'].strftime('%d.%m.%Y') if hasattr(data['start_date'], 'strftime') else str(data['start_date'])
    end_date_str = data['end_date'].strftime('%d.%m.%Y') if hasattr(data['end_date'], 'strftime') else str(data['end_date']) if data['end_date'] else 'Не завершена'
    
    exhibit_data = [
        ["Инвентарный номер:", str(data['inventory_number'])],
        ["Название:", str(data['exhibit_name'])],
        ["Автор:", str(data['author_name'])],
        ["Датировка:", str(data['dating'])],
        ["Материал:", str(data['material_name'])],
        ["Техника:", str(data['technique_name'])],
        ["Размеры:", str(data['dimensions'])],
    ]
    
    exhibit_table = Table(exhibit_data, colWidths=[80, 350])
    exhibit_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'CustomFont'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F5E6E3')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(exhibit_table)
    story.append(Spacer(1, 15))
    
    # Данные реставрации
    story.append(Paragraph("2. ДАННЫЕ О РЕСТАВРАЦИИ", heading_style))
    
    restoration_data = [
        ["Дата начала:", start_date_str],
        ["Дата окончания:", end_date_str],
        ["Реставратор:", str(data['restorer_name']) if data['restorer_name'] else '—'],
        ["Документ:", str(data['document_reference']) if data['document_reference'] else '—'],
    ]
    
    restoration_table = Table(restoration_data, colWidths=[80, 350])
    restoration_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'CustomFont'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F5E6E3')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(restoration_table)
    story.append(Spacer(1, 15))
    
    # Описание работ
    if data.get('description'):
        story.append(Paragraph("3. ОПИСАНИЕ РАБОТ", heading_style))
        story.append(Paragraph(str(data['description']).replace('\n', '<br/>'), normal_style))
        story.append(Spacer(1, 10))
    
    # Материалы
    if data.get('materials_used'):
        story.append(Paragraph("4. ИСПОЛЬЗОВАННЫЕ МАТЕРИАЛЫ", heading_style))
        story.append(Paragraph(str(data['materials_used']).replace('\n', '<br/>'), normal_style))
        story.append(Spacer(1, 10))
    
    # Состояние до
    if data.get('condition_before'):
        story.append(Paragraph("5. СОСТОЯНИЕ ДО РЕСТАВРАЦИИ", heading_style))
        story.append(Paragraph(str(data['condition_before']).replace('\n', '<br/>'), normal_style))
        story.append(Spacer(1, 10))
    
    # Состояние после
    if data.get('condition_after'):
        story.append(Paragraph("6. СОСТОЯНИЕ ПОСЛЕ РЕСТАВРАЦИИ", heading_style))
        story.append(Paragraph(str(data['condition_after']).replace('\n', '<br/>'), normal_style))
        story.append(Spacer(1, 20))
    
    # Подписи
    story.append(Paragraph("7. ПОДПИСИ", heading_style))
    
    signatures_data = [
        ["Руководитель отдела реставрации:", "", "__________________"],
        ["Реставратор:", "", "__________________"],
        ["Хранитель фонда:", "", "__________________"],
        ["", "(должность)", "(подпись)"],
    ]
    
    signatures_table = Table(signatures_data, colWidths=[150, 100, 120])
    signatures_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'CustomFont'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('LINEABOVE', (0, 0), (2, 0), 0.5, colors.black),
        ('LINEABOVE', (0, 1), (2, 1), 0.5, colors.black),
        ('LINEABOVE', (0, 2), (2, 2), 0.5, colors.black),
        ('ALIGN', (2, 0), (2, 2), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
    ]))
    story.append(signatures_table)
    
    # Строим документ
    doc.build(story)
    buffer.seek(0)
    return buffer