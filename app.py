from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from testing_module import init_testing_database, testing_bp
from testing_translations import TESTING_TRANSLATION_BLOCKS
from ui_translations import UI_TRANSLATION_BLOCKS


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "student_task_manager.db"
DEFAULT_LANGUAGE = "ru"

LANGUAGES = {"ru": "Русский", "kk": "Қазақша"}
STATUS_OPTIONS = ["Pending", "In Progress", "Completed"]
PRIORITY_OPTIONS = ["High", "Medium", "Low"]
ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ALLOWED_ROLES = {ROLE_TEACHER, ROLE_STUDENT}

VALUE_TRANSLATION_KEYS = {
    "status": {
        "Pending": "status_pending",
        "In Progress": "status_in_progress",
        "Completed": "status_completed",
    },
    "priority": {
        "High": "priority_high",
        "Medium": "priority_medium",
        "Low": "priority_low",
    },
}


def parse_translation_block(block: str) -> dict[str, str]:
    def repair_mojibake(value: str) -> str:
        # Fix legacy text that was saved as UTF-8 bytes but decoded with a wrong code page.
        # We score each candidate and keep the cleanest one.
        mojibake_markers = (
            "Ð",
            "Ñ",
            "Ã",
            "Â",
            "вЂ",
            "Ђ",
            "Ѓ",
            "‘",
            "’",
            "“",
            "”",
            "•",
            "–",
            "—",
            "™",
        )

        def score_text(text: str) -> int:
            marker_score = sum(text.count(marker) for marker in mojibake_markers)
            latin1_noise = sum(1 for ch in text if 0x00C0 <= ord(ch) <= 0x00FF)
            control_noise = sum(
                1
                for ch in text
                if unicodedata.category(ch).startswith("C") and ch not in "\n\r\t"
            )
            return marker_score * 4 + latin1_noise * 2 + control_noise * 8

        best = value
        best_score = score_text(value)
        for source_encoding in ("cp1251", "latin1", "cp1252"):
            try:
                candidate = value.encode(source_encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            candidate_score = score_text(candidate)
            if candidate and candidate_score < best_score:
                best = candidate
                best_score = candidate_score
        return best

    translations: dict[str, str] = {}
    for raw_line in block.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        translations[key.strip()] = repair_mojibake(value.strip())
    return translations


TRANSLATION_BLOCKS = {
    "ru": """
site_title=ATU Campus Planner
site_tagline=Единая цифровая академическая платформа АТУ
nav_home=Главная
nav_login=Войти
nav_register=Регистрация
nav_dashboard=Панель
nav_add_task=Добавить задачу
nav_statistics=Статистика
nav_logout=Выйти
language_label=Язык
language_ru=РУ
language_kk=ҚАЗ
home_page_title=Главная
home_eyebrow=Платформа Алматинского технологического университета
home_heading=Управляйте заданиями и учебной нагрузкой в экосистеме АТУ.
home_text=ATU Campus Planner помогает студентам АТУ планировать учебу, контролировать дедлайны и отслеживать прогресс в едином цифровом кабинете.
create_account=Создать аккаунт
log_in=Войти
hero_point_1=Контроль дедлайнов
hero_point_2=Планирование по предметам
hero_point_3=Наглядная аналитика
today_glance=Кратко на сегодня
study_clearer_plan=Учиться с более понятным планом
home_feature_1=Отслеживайте ожидающие, активные и завершённые задачи
home_feature_2=Выделяйте просроченные задачи до того, как они станут проблемой
home_feature_3=Фильтруйте задачи по предмету, приоритету и статусу
home_feature_4=Анализируйте статистику для более стабильной успеваемости
task_control=Контроль задач
task_control_text=Создавайте, редактируйте и удаляйте задания с полной защитой владельца.
deadline_focus=Фокус на дедлайнах
deadline_focus_text=Сразу замечайте срочные и просроченные учебные задачи на панели.
smart_organization=Умная организация
smart_organization_text=Группируйте задачи по предметам и сортируйте по сроку, приоритету или дате создания.
register_page_title=Регистрация
register_eyebrow=Новый аккаунт
register_heading=Создайте своё студенческое пространство
register_text=Зарегистрируйтесь, чтобы начать управлять учебными задачами в личной панели.
full_name=Полное имя
email_address=Электронная почта
password=Пароль
confirm_password=Подтвердите пароль
register_button=Зарегистрироваться
already_have_account=Уже есть аккаунт?
login_here=Войдите здесь
login_page_title=Вход
login_eyebrow=С возвращением
login_heading=Войдите в свою панель
login_text=Получите безопасный доступ к задачам, дедлайнам и статистике.
login_button=Войти
need_account=Нужен аккаунт?
create_one_now=Создать сейчас
dashboard_page_title=Панель
dashboard_eyebrow=Панель
dashboard_heading={name}, держите семестр под контролем.
dashboard_text=Просматривайте нагрузку, следите за дедлайнами и обновляйте прогресс в одном месте.
add_new_task=Добавить задачу
total_tasks=Всего задач
total_tasks_text=Все задания в вашем планировщике
completed=Завершено
completed_text=Успешно выполненные задачи
due_soon=Скоро срок
due_soon_text=Дедлайны в течение ближайших 7 дней
overdue=Просрочено
overdue_text_stat=Срок истёк, задача не завершена
task_filters=Фильтры задач
task_filters_text=Отфильтруйте список по предмету, статусу, приоритету, ключевому слову и сортировке.
search=Поиск
search_placeholder=Название или описание
subject=Предмет
all_subjects=Все предметы
status=Статус
all_statuses=Все статусы
priority=Приоритет
all_priorities=Все приоритеты
sort_by=Сортировка
sort_deadline_asc=Срок: сначала ближайшие
sort_deadline_desc=Срок: сначала поздние
sort_created_desc=Сначала новые
sort_created_asc=Сначала старые
sort_priority_high=Приоритет: высокий к низкому
sort_status=По статусу
sort_subject=По предмету
apply_filters=Применить
reset=Сбросить
your_tasks=Ваши задачи
your_tasks_text=Просроченные задачи выделены, чтобы вы сразу видели риски.
no_description=Для этой задачи описание не указано.
deadline_label=Срок
created_label=Создано
overdue_badge=Просрочено
edit=Редактировать
delete=Удалить
delete_confirm=Удалить эту задачу без возможности восстановления?
no_tasks_found=Задачи не найдены
no_tasks_text=Попробуйте изменить фильтры или добавьте новую учебную задачу.
create_first_task=Создать первую задачу
task_management=Управление задачами
task_form_text=Зафиксируйте важные детали, чтобы задания было легче планировать и выполнять.
add_task_page_title=Добавить задачу
edit_task_page_title=Редактировать задачу
task_title=Название задачи
task_title_placeholder=Например: Презентация по проекту базы данных
description=Описание
description_placeholder=Опишите требования, материалы или следующие шаги
subject_placeholder=Например: Программная инженерия
deadline=Дедлайн
cancel=Отмена
statistics_page_title=Статистика
statistics_eyebrow=Статистика
statistics_heading=Аналитика учебной продуктивности
statistics_text=Анализируйте распределение задач, чтобы принимать более точные решения в планировании.
recorded_in_planner=Зафиксировано в планировщике
completed_successfully=Отмечено как успешно выполненное
due_soon_stat_text=Срок наступит в течение 7 дней
overdue_stat_text=Требует немедленного внимания
completion_rate=Процент выполнения
completion_rate_text=Быстрый взгляд на долю уже завершённой работы.
tasks_by_status=Задачи по статусу
tasks_by_status_text=Посмотрите баланс между ожидающими, активными и завершёнными задачами.
no_status_data=Пока нет данных по статусам.
tasks_by_subject=Задачи по предметам
tasks_by_subject_text=Определите, какие дисциплины требуют больше всего внимания.
no_subject_data=Пока нет данных по предметам.
tasks_by_priority=Задачи по приоритету
tasks_by_priority_text=Проверьте, состоит ли ваша нагрузка в основном из срочных или обычных задач.
no_priority_data=Пока нет данных по приоритетам.
please_login_continue=Пожалуйста, войдите в систему, чтобы продолжить.
full_name_required=Полное имя обязательно.
email_required=Электронная почта обязательна.
password_required=Пароль обязателен.
password_min_length=Пароль должен содержать не менее 6 символов.
password_confirmation_mismatch=Подтверждение пароля не совпадает.
account_exists=Аккаунт с таким адресом электронной почты уже существует.
registration_successful=Регистрация прошла успешно. Теперь вы можете войти.
invalid_email_or_password=Неверная почта или пароль.
welcome_back_user=С возвращением, {name}!
logged_out=Вы вышли из аккаунта.
validation_required=Поле «{field}» обязательно.
deadline_format=Поле дедлайна должно быть в формате ГГГГ-ММ-ДД.
task_not_found=Задача не найдена или доступ запрещён.
task_added_successfully=Задача успешно добавлена.
task_updated_successfully=Задача успешно обновлена.
task_deleted_successfully=Задача успешно удалена.
task_title_field=Название задачи
subject_field=Предмет
deadline_field=Дедлайн
priority_field=Приоритет
status_field=Статус
status_pending=Ожидает
status_in_progress=В процессе
status_completed=Завершено
priority_high=Высокий
priority_medium=Средний
priority_low=Низкий
role_label=Роль
role_teacher=Преподаватель
role_student=Студент
group_name=Группа
group_name_optional=Группа (необязательно)
group_name_required_student=Для студентов поле группы обязательно.
password_weak=Используйте минимум 8 символов, включая заглавные, строчные буквы и цифру.
access_denied=У вас нет прав для открытия этой страницы.
teacher_only_access=Доступ только для преподавателей.
student_only_access=Доступ только для студентов.
assigned_tests=Назначенные тесты
completed_tests=Завершенные тесты
pending_tests=Ожидающие тесты
student_dashboard_heading=Ваше личное учебное пространство
student_dashboard_text=Отслеживайте задачи, назначенные тесты и свои результаты в одном месте.
teacher_dashboard_heading=Панель управления преподавателя
teacher_dashboard_text=Управляйте тестами, отслеживайте участие и анализируйте результаты.
total_students_participated=Участвовавшие студенты
manage_tests=Управление тестами
my_results=Мои результаты
teacher_quick_actions=Быстрые действия преподавателя
assigned_group_label=Назначенная группа (необязательно)
assigned_group_hint=Оставьте пустым, чтобы тест был доступен всем группам.
test_not_assigned=Этот тест не назначен вашей группе.
registration_role_invalid=Пожалуйста, выберите корректную роль.
teacher_overview=Обзор преподавателя
""",
    "kk": """
site_title=ATU Campus Planner
site_tagline=АТУ-дың бірыңғай цифрлық академиялық платформасы
nav_home=Басты бет
nav_login=Кіру
nav_register=Тіркелу
nav_dashboard=Басқару панелі
nav_add_task=Тапсырма қосу
nav_statistics=Статистика
nav_logout=Шығу
language_label=Тіл
language_ru=РУ
language_kk=ҚАЗ
home_page_title=Басты бет
home_eyebrow=Алматы технологиялық университетіне арналған платформа
home_heading=АТУ экожүйесінде тапсырмалар мен оқу жүктемесін басқарыңыз.
home_text=ATU Campus Planner АТУ студенттеріне оқуын жоспарлауға, дедлайндарды бақылауға және прогресті бірыңғай цифрлық кабинетте қадағалауға көмектеседі.
create_account=Аккаунт ашу
log_in=Кіру
hero_point_1=Дедлайндарды бақылау
hero_point_2=Пәндер бойынша жоспарлау
hero_point_3=Көрнекі аналитика
today_glance=Бүгінгі қысқаша шолу
study_clearer_plan=Оқуды нақты жоспармен жалғастырыңыз
home_feature_1=Күтілуде, орындалып жатыр және аяқталған тапсырмаларды бақылаңыз
home_feature_2=Мәселе туындамай тұрып мерзімі өткен жұмыстарды белгілеңіз
home_feature_3=Тапсырмаларды пән, басымдық немесе мәртебе бойынша сүзгіден өткізіңіз
home_feature_4=Үлгерімді тұрақты ету үшін статистиканы талдаңыз
task_control=Тапсырмаларды басқару
task_control_text=Тапсырмаларды иесіне ғана қолжетімді қорғаныспен құрыңыз, өңдеңіз және өшіріңіз.
deadline_focus=Дедлайнға назар
deadline_focus_text=Жедел және мерзімі өткен оқу тапсырмаларын панельден бірден көріңіз.
smart_organization=Ақылды ұйымдастыру
smart_organization_text=Тапсырмаларды пән бойынша топтастырып, мерзіміне, басымдығына немесе құрылған уақытына қарай сұрыптаңыз.
register_page_title=Тіркелу
register_eyebrow=Жаңа аккаунт
register_heading=Өзіңіздің студенттік кеңістігіңізді жасаңыз
register_text=Жеке панель арқылы оқу тапсырмаларын басқаруды бастау үшін тіркеліңіз.
full_name=Толық аты-жөні
email_address=Электрондық пошта
password=Құпиясөз
confirm_password=Құпиясөзді растаңыз
register_button=Тіркелу
already_have_account=Аккаунтыңыз бар ма?
login_here=Осы жерден кіріңіз
login_page_title=Кіру
login_eyebrow=Қош келдіңіз
login_heading=Панельге кіріңіз
login_text=Тапсырмаларға, дедлайндарға және статистикаға қауіпсіз қол жеткізіңіз.
login_button=Кіру
need_account=Аккаунт керек пе?
create_one_now=Қазір ашу
dashboard_page_title=Басқару панелі
dashboard_eyebrow=Басқару панелі
dashboard_heading={name}, семестріңізді бақылауда ұстаңыз.
dashboard_text=Жүктемені қарап шығыңыз, дедлайндарды бақылаңыз және прогресті бір жерден жаңартыңыз.
add_new_task=Жаңа тапсырма қосу
total_tasks=Барлық тапсырма
total_tasks_text=Жоспарлағыштағы барлық жұмыс
completed=Аяқталған
completed_text=Сәтті орындалған тапсырмалар
due_soon=Жақында тапсыру керек
due_soon_text=Келесі 7 күн ішіндегі дедлайндар
overdue=Мерзімі өткен
overdue_text_stat=Мерзімі өтіп кеткен және аяқталмаған
task_filters=Тапсырма сүзгілері
task_filters_text=Тізімді пән, мәртебе, басымдық, кілт сөз және сұрыптау бойынша тарылтыңыз.
search=Іздеу
search_placeholder=Атауы немесе сипаттамасы
subject=Пән
all_subjects=Барлық пән
status=Мәртебе
all_statuses=Барлық мәртебе
priority=Басымдық
all_priorities=Барлық басымдық
sort_by=Сұрыптау
sort_deadline_asc=Мерзім: жақыны алдымен
sort_deadline_desc=Мерзім: алысы алдымен
sort_created_desc=Алдымен жаңалары
sort_created_asc=Алдымен ескілері
sort_priority_high=Басымдық: жоғарыдан төменге
sort_status=Мәртебе бойынша
sort_subject=Пән бойынша
apply_filters=Қолдану
reset=Қалпына келтіру
your_tasks=Сіздің тапсырмаларыңыз
your_tasks_text=Қауіпті бірден көру үшін мерзімі өткен жұмыстар ерекшеленіп көрсетіледі.
no_description=Бұл тапсырмаға сипаттама енгізілмеген.
deadline_label=Дедлайн
created_label=Құрылған уақыты
overdue_badge=Мерзімі өткен
edit=Өңдеу
delete=Өшіру
delete_confirm=Бұл тапсырманы біржола өшіргіңіз келе ме?
no_tasks_found=Тапсырмалар табылмады
no_tasks_text=Сүзгілерді өзгертіп көріңіз немесе жаңа оқу тапсырмасын қосыңыз.
create_first_task=Алғашқы тапсырманы жасау
task_management=Тапсырмаларды басқару
task_form_text=Жұмысты жоспарлау мен орындауды жеңілдету үшін маңызды деректерді енгізіңіз.
add_task_page_title=Тапсырма қосу
edit_task_page_title=Тапсырманы өңдеу
task_title=Тапсырма атауы
task_title_placeholder=Мысалы: Дерекқор жобасы бойынша презентация
description=Сипаттама
description_placeholder=Талаптарды, материалдарды немесе келесі қадамдарды жазыңыз
subject_placeholder=Мысалы: Бағдарламалық инженерия
deadline=Дедлайн
cancel=Бас тарту
statistics_page_title=Статистика
statistics_eyebrow=Статистика
statistics_heading=Оқу өнімділігінің талдауы
statistics_text=Жоспарлауда дәлірек шешім қабылдау үшін тапсырмалардың бөлінуін талдаңыз.
recorded_in_planner=Жоспарлағышта тіркелген
completed_successfully=Сәтті аяқталды деп белгіленген
due_soon_stat_text=7 күн ішінде тапсыру қажет
overdue_stat_text=Жедел назар аударуды қажет етеді
completion_rate=Орындалу пайызы
completion_rate_text=Аяқталған жұмыстың үлесін жылдам бағалау.
tasks_by_status=Мәртебе бойынша тапсырмалар
tasks_by_status_text=Күтілуде, орындалып жатыр және аяқталған жұмыстардың арақатынасын көріңіз.
no_status_data=Әзірге мәртебе бойынша дерек жоқ.
tasks_by_subject=Пән бойынша тапсырмалар
tasks_by_subject_text=Қай пәндердің көбірек назар талап ететінін анықтаңыз.
no_subject_data=Әзірге пәндер бойынша дерек жоқ.
tasks_by_priority=Басымдық бойынша тапсырмалар
tasks_by_priority_text=Жүктемеңіз көбіне шұғыл ма, әлде қалыпты ма, соны тексеріңіз.
no_priority_data=Әзірге басымдықтар бойынша дерек жоқ.
please_login_continue=Жалғастыру үшін жүйеге кіріңіз.
full_name_required=Толық аты-жөні міндетті.
email_required=Электрондық пошта міндетті.
password_required=Құпиясөз міндетті.
password_min_length=Құпиясөз кемінде 6 таңбадан тұруы керек.
password_confirmation_mismatch=Құпиясөзді растау сәйкес келмейді.
account_exists=Бұл электрондық поштамен аккаунт бұрыннан бар.
registration_successful=Тіркелу сәтті аяқталды. Енді жүйеге кіре аласыз.
invalid_email_or_password=Электрондық пошта немесе құпиясөз қате.
welcome_back_user=Қайта келгеніңізге қуаныштымыз, {name}!
logged_out=Сіз аккаунттан шықтыңыз.
validation_required=«{field}» өрісі міндетті.
deadline_format=Дедлайн өрісі ЖЖЖЖ-АА-КК форматында болуы керек.
task_not_found=Тапсырма табылмады немесе оған қолжетімділік жоқ.
task_added_successfully=Тапсырма сәтті қосылды.
task_updated_successfully=Тапсырма сәтті жаңартылды.
task_deleted_successfully=Тапсырма сәтті өшірілді.
task_title_field=Тапсырма атауы
subject_field=Пән
deadline_field=Дедлайн
priority_field=Басымдық
status_field=Мәртебе
status_pending=Күтілуде
status_in_progress=Орындалып жатыр
status_completed=Аяқталған
priority_high=Жоғары
priority_medium=Орташа
priority_low=Төмен
role_label=Рөл
role_teacher=Оқытушы
role_student=Студент
group_name=Топ
group_name_optional=Топ (міндетті емес)
group_name_required_student=Студенттер үшін топ өрісі міндетті.
password_weak=Кемінде 8 таңба, бас әріп, кіші әріп және сан қолданыңыз.
access_denied=Сізде бұл бетті ашуға рұқсат жоқ.
teacher_only_access=Тек оқытушыларға арналған.
student_only_access=Тек студенттерге арналған.
assigned_tests=Тағайындалған тесттер
completed_tests=Аяқталған тесттер
pending_tests=Күтілуде тесттер
student_dashboard_heading=Сіздің жеке оқу кеңістігіңіз
student_dashboard_text=Тапсырмаларды, тағайындалған тесттерді және нәтижелерді бір жерден бақылаңыз.
teacher_dashboard_heading=Оқытушы басқару панелі
teacher_dashboard_text=Тесттерді басқарыңыз, қатысуды бақылаңыз және нәтижелерді талдаңыз.
total_students_participated=Қатысқан студенттер
manage_tests=Тесттерді басқару
my_results=Менің нәтижелерім
teacher_quick_actions=Оқытушының жылдам әрекеттері
assigned_group_label=Тағайындалған топ (міндетті емес)
assigned_group_hint=Тест барлық топтарға қолжетімді болуы үшін бос қалдырыңыз.
test_not_assigned=Бұл тест сіздің тобыңызға тағайындалмаған.
registration_role_invalid=Дұрыс рөлді таңдаңыз.
teacher_overview=Оқытушы шолуы
""",
}

TRANSLATIONS = {
    language: parse_translation_block(block)
    for language, block in TRANSLATION_BLOCKS.items()
}
for language, block in TESTING_TRANSLATION_BLOCKS.items():
    TRANSLATIONS.setdefault(language, {}).update(parse_translation_block(block))
for language, block in UI_TRANSLATION_BLOCKS.items():
    TRANSLATIONS.setdefault(language, {}).update(parse_translation_block(block))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "student-task-manager-development-key"
)
app.config["DATABASE"] = DATABASE
app.config["DEFAULT_LANGUAGE"] = DEFAULT_LANGUAGE
app.config["TRANSLATIONS"] = TRANSLATIONS
app.config["QR_CODE_DIR"] = BASE_DIR / "static" / "qr"
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False


@app.after_request
def ensure_utf8_charset(response: Response) -> Response:
    content_type = response.headers.get("Content-Type", "")
    if "charset=" in content_type.lower():
        return response

    utf8_mimetypes = {
        "text/html",
        "text/plain",
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/json",
        "text/csv",
        "application/xml",
        "text/xml",
    }
    if response.mimetype in utf8_mimetypes:
        response.headers["Content-Type"] = f"{response.mimetype}; charset=utf-8"
    return response


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exception: BaseException | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(item[1] == column for item in columns)


def _ensure_users_schema(connection: sqlite3.Connection) -> None:
    if not _column_exists(connection, "users", "password"):
        connection.execute("ALTER TABLE users ADD COLUMN password TEXT")
    if not _column_exists(connection, "users", "role"):
        connection.execute(f"ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT '{ROLE_STUDENT}'")
    if not _column_exists(connection, "users", "group_name"):
        connection.execute("ALTER TABLE users ADD COLUMN group_name TEXT")
    if not _column_exists(connection, "users", "created_at"):
        connection.execute("ALTER TABLE users ADD COLUMN created_at TEXT")

    has_password_hash = _column_exists(connection, "users", "password_hash")
    if has_password_hash:
        connection.execute(
            """
            UPDATE users
            SET password = COALESCE(NULLIF(password, ''), password_hash)
            WHERE password IS NULL OR password = ''
            """
        )

    connection.execute(
        "UPDATE users SET role = COALESCE(NULLIF(role, ''), ?)",
        (ROLE_STUDENT,),
    )
    connection.execute(
        "UPDATE users SET created_at = COALESCE(NULLIF(created_at, ''), datetime('now'))"
    )
    try:
        connection.execute(
            """
            UPDATE users
            SET role = ?
            WHERE role = ?
              AND id IN (SELECT DISTINCT created_by FROM tests)
            """,
            (ROLE_TEACHER, ROLE_STUDENT),
        )
    except sqlite3.Error:
        pass


def init_db() -> None:
    connection = sqlite3.connect(DATABASE)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('teacher', 'student')),
            group_name TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            subject TEXT NOT NULL,
            deadline TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS study_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS group_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            assigned_group TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            subject TEXT NOT NULL,
            deadline TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_group_tasks_group ON group_tasks (assigned_group);
        CREATE INDEX IF NOT EXISTS idx_group_tasks_teacher ON group_tasks (teacher_id);
        CREATE INDEX IF NOT EXISTS idx_activity_logs_user_created ON activity_logs (user_id, created_at);
        """
    )
    _ensure_users_schema(connection)
    connection.commit()
    connection.close()
    init_testing_database(DATABASE)


def get_current_language() -> str:
    language = session.get("language", DEFAULT_LANGUAGE)
    if language not in LANGUAGES:
        language = DEFAULT_LANGUAGE
    session["language"] = language
    return language


def translate(key: str, **kwargs) -> str:
    language = getattr(g, "lang", DEFAULT_LANGUAGE)
    text = TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE]).get(
        key,
        TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key),
    )
    return text.format(**kwargs) if kwargs else text


def translate_value(value: str, group: str) -> str:
    key = VALUE_TRANSLATION_KEYS.get(group, {}).get(value)
    return translate(key) if key else value


def log_activity(
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: str | None = None,
    user_id: int | None = None,
    role: str | None = None,
) -> None:
    actor_id = user_id if user_id is not None else session.get("user_id")
    actor_role = role if role is not None else session.get("role")
    if actor_id is None:
        return
    try:
        get_db().execute(
            """
            INSERT INTO activity_logs (user_id, role, action, entity_type, entity_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor_id,
                actor_role,
                action,
                entity_type,
                entity_id,
                details,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        get_db().commit()
    except sqlite3.Error:
        return


def upsert_study_group(group_name: str, created_by: int | None = None) -> None:
    value = group_name.strip()
    if not value:
        return
    try:
        get_db().execute(
            """
            INSERT INTO study_groups (name, created_by, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (value, created_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        get_db().commit()
    except sqlite3.Error:
        return


def fetch_all_groups() -> list[str]:
    db = get_db()
    rows = db.execute(
        """
        SELECT name FROM study_groups
        UNION
        SELECT group_name AS name FROM users WHERE group_name IS NOT NULL AND group_name != ''
        UNION
        SELECT assigned_group AS name FROM tests WHERE assigned_group IS NOT NULL AND assigned_group != ''
        UNION
        SELECT assigned_group AS name FROM group_tasks WHERE assigned_group IS NOT NULL AND assigned_group != ''
        ORDER BY name COLLATE NOCASE ASC
        """
    ).fetchall()
    return [row["name"] for row in rows]


def get_student_group_tasks(group_name: str, limit: int = 20) -> list[sqlite3.Row]:
    if not group_name:
        return []
    return get_db().execute(
        """
        SELECT gt.*, u.name AS teacher_name
        FROM group_tasks gt
        JOIN users u ON u.id = gt.teacher_id
        WHERE LOWER(gt.assigned_group) = LOWER(?)
        ORDER BY gt.deadline ASC, gt.created_at DESC
        LIMIT ?
        """,
        (group_name, limit),
    ).fetchall()


def get_teacher_group_tasks(teacher_id: int, limit: int = 25) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT *
        FROM group_tasks
        WHERE teacher_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (teacher_id, limit),
    ).fetchall()


def safe_redirect_target() -> str:
    next_url = request.args.get("next", "").strip()
    if next_url.startswith("/"):
        return next_url
    if request.referrer:
        parsed = urlparse(request.referrer)
        if not parsed.netloc or parsed.netloc == request.host:
            return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
    return url_for("home")


def get_password_hash(user_row: sqlite3.Row) -> str:
    password_hash = user_row["password"] if "password" in user_row.keys() else None
    if not password_hash and "password_hash" in user_row.keys():
        password_hash = user_row["password_hash"]
    return password_hash or ""


def is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False
    has_upper = re.search(r"[A-Z]", password) is not None
    has_lower = re.search(r"[a-z]", password) is not None
    has_digit = re.search(r"\d", password) is not None
    return has_upper and has_lower and has_digit


def current_role() -> str:
    role = session.get("role", "")
    return role if role in ALLOWED_ROLES else ""


def current_user_is_teacher() -> bool:
    return current_role() == ROLE_TEACHER


def current_user_is_student() -> bool:
    return current_role() == ROLE_STUDENT


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            flash(translate("please_login_continue"), "warning")
            target = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=target))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(*allowed_roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if session.get("user_id") is None:
                flash(translate("please_login_continue"), "warning")
                target = request.full_path if request.query_string else request.path
                return redirect(url_for("login", next=target))

            if current_role() not in allowed_roles:
                flash(translate("access_denied"), "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


@app.before_request
def load_request_data() -> None:
    g.lang = get_current_language()
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, name, email, role, group_name, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if g.user is None:
            selected_language = get_current_language()
            session.clear()
            session["language"] = selected_language
        else:
            session["user_id"] = g.user["id"]
            session["user_name"] = g.user["name"]
            session["role"] = g.user["role"] if g.user["role"] in ALLOWED_ROLES else ROLE_STUDENT


@app.context_processor
def inject_template_helpers() -> dict[str, object]:
    user_initials = ""
    user_role = ""
    if g.user:
        user_initials = get_user_initials(g.user["name"])
        user_role = infer_user_role(g.user)
    return {
        "today_date": date.today().isoformat(),
        "t": translate,
        "translate_value": translate_value,
        "current_language": g.lang,
        "supported_languages": LANGUAGES,
        "status_options": STATUS_OPTIONS,
        "priority_options": PRIORITY_OPTIONS,
        "user_initials": user_initials,
        "user_role": user_role,
        "current_user_role_code": current_role(),
        "is_teacher": current_user_is_teacher(),
        "is_student": current_user_is_student(),
    }


def validate_task_form(form_data: dict[str, str]) -> list[str]:
    field_keys = {
        "title": "task_title_field",
        "subject": "subject_field",
        "deadline": "deadline_field",
        "priority": "priority_field",
        "status": "status_field",
    }
    errors = [
        translate("validation_required", field=translate(label_key))
        for field, label_key in field_keys.items()
        if not form_data.get(field, "").strip()
    ]

    deadline_value = form_data.get("deadline", "").strip()
    if deadline_value:
        try:
            datetime.strptime(deadline_value, "%Y-%m-%d")
        except ValueError:
            errors.append(translate("deadline_format"))
    return errors


def build_dashboard_filters() -> dict[str, str]:
    return {
        "subject": request.args.get("subject", "").strip(),
        "status": request.args.get("status", "").strip(),
        "priority": request.args.get("priority", "").strip(),
        "search": request.args.get("search", "").strip(),
        "sort": request.args.get("sort", "deadline_asc").strip() or "deadline_asc",
    }


def get_sort_clause(sort_key: str) -> str:
    sort_options = {
        "deadline_asc": "deadline ASC",
        "deadline_desc": "deadline DESC",
        "created_desc": "created_at DESC",
        "created_asc": "created_at ASC",
        "priority_high": (
            "CASE priority "
            "WHEN 'High' THEN 1 "
            "WHEN 'Medium' THEN 2 "
            "ELSE 3 END ASC, deadline ASC"
        ),
        "status": "status ASC, deadline ASC",
        "subject": "subject COLLATE NOCASE ASC, deadline ASC",
    }
    return sort_options.get(sort_key, sort_options["deadline_asc"])


def get_user_task(task_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, session["user_id"]),
    ).fetchone()


def get_teacher_group_task(task_id: int, teacher_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        "SELECT * FROM group_tasks WHERE id = ? AND teacher_id = ?",
        (task_id, teacher_id),
    ).fetchone()


def get_dashboard_statistics(user_id: int) -> dict[str, int]:
    db = get_db()
    today = date.today().isoformat()
    soon = (date.today() + timedelta(days=7)).isoformat()
    return {
        "total": db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0],
        "completed": db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'Completed'",
            (user_id,),
        ).fetchone()[0],
        "overdue": db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND deadline < ? AND status != 'Completed'",
            (user_id, today),
        ).fetchone()[0],
        "due_soon": db.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND deadline BETWEEN ? AND ? AND status != 'Completed'",
            (user_id, today, soon),
        ).fetchone()[0],
    }


def fetch_subjects(user_id: int) -> list[str]:
    rows = get_db().execute(
        "SELECT DISTINCT subject FROM tasks WHERE user_id = ? ORDER BY subject COLLATE NOCASE ASC",
        (user_id,),
    ).fetchall()
    return [row["subject"] for row in rows]


def get_test_summary(user_id: int) -> dict[str, int]:
    db = get_db()
    try:
        tests_created = db.execute(
            "SELECT COUNT(*) FROM tests WHERE created_by = ?",
            (user_id,),
        ).fetchone()[0]
        tests_attempts = db.execute(
            """
            SELECT COUNT(*)
            FROM test_attempts a
            JOIN tests t ON t.id = a.test_id
            WHERE t.created_by = ?
            """,
            (user_id,),
        ).fetchone()[0]
        tests_without_questions = db.execute(
            """
            SELECT COUNT(*)
            FROM tests t
            WHERE t.created_by = ?
              AND NOT EXISTS (SELECT 1 FROM test_questions q WHERE q.test_id = t.id)
            """,
            (user_id,),
        ).fetchone()[0]
    except sqlite3.Error:
        tests_created = 0
        tests_attempts = 0
        tests_without_questions = 0

    return {
        "tests_created": tests_created,
        "tests_attempts": tests_attempts,
        "tests_without_questions": tests_without_questions,
    }


def get_teacher_overview(user_id: int) -> dict[str, object]:
    db = get_db()
    try:
        summary_row = db.execute(
            """
            SELECT
                COUNT(DISTINCT t.id) AS tests_created,
                COUNT(a.id) AS total_attempts,
                COUNT(DISTINCT a.user_id) AS students_participated
            FROM tests t
            LEFT JOIN test_attempts a ON a.test_id = t.id
            WHERE t.created_by = ?
            """,
            (user_id,),
        ).fetchone()
        recent_tests = db.execute(
            """
            SELECT t.*,
                   (SELECT COUNT(*) FROM test_questions q WHERE q.test_id = t.id) AS question_count,
                   (SELECT COUNT(*) FROM test_attempts a WHERE a.test_id = t.id) AS attempt_count
            FROM tests t
            WHERE t.created_by = ?
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT 6
            """,
            (user_id,),
        ).fetchall()
    except sqlite3.Error:
        summary_row = {"tests_created": 0, "total_attempts": 0, "students_participated": 0}
        recent_tests = []

    return {
        "tests_created": summary_row["tests_created"] or 0,
        "total_attempts": summary_row["total_attempts"] or 0,
        "students_participated": summary_row["students_participated"] or 0,
        "recent_tests": [dict(row) for row in recent_tests],
    }


def get_student_test_overview(user_id: int, group_name: str) -> dict[str, object]:
    db = get_db()
    try:
        assigned_rows = db.execute(
            """
            SELECT t.*,
                   (SELECT COUNT(*) FROM test_questions q WHERE q.test_id = t.id) AS question_count,
                   (SELECT COUNT(*) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id = ?) AS attempt_count,
                   (SELECT MAX(a.percentage) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id = ?) AS best_percentage,
                   (SELECT MAX(a.submitted_at) FROM test_attempts a WHERE a.test_id = t.id AND a.user_id = ?) AS last_submitted_at
            FROM tests t
            WHERE t.is_active = 1
              AND EXISTS (SELECT 1 FROM test_questions q WHERE q.test_id = t.id)
              AND (t.assigned_group IS NULL OR t.assigned_group = '' OR LOWER(t.assigned_group) = LOWER(?))
            ORDER BY
                CASE WHEN t.deadline IS NULL OR t.deadline = '' THEN 1 ELSE 0 END ASC,
                t.deadline ASC,
                t.created_at DESC,
                t.id DESC
            """,
            (user_id, user_id, user_id, group_name),
        ).fetchall()
        result_summary = db.execute(
            """
            SELECT
                COUNT(*) AS attempts_count,
                ROUND(AVG(percentage), 1) AS average_score,
                MAX(percentage) AS best_score
            FROM test_attempts
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        recent_results = db.execute(
            """
            SELECT a.*, t.title AS test_title, t.subject AS test_subject, t.token AS test_token
            FROM test_attempts a
            JOIN tests t ON t.id = a.test_id
            WHERE a.user_id = ?
            ORDER BY a.submitted_at DESC, a.id DESC
            LIMIT 8
            """,
            (user_id,),
        ).fetchall()
    except sqlite3.Error:
        assigned_rows = []
        result_summary = {"attempts_count": 0, "average_score": 0, "best_score": 0}
        recent_results = []

    assigned_tests = [dict(row) for row in assigned_rows]
    completed_tests = sum(1 for row in assigned_tests if (row.get("attempt_count") or 0) > 0)
    pending_tests = len(assigned_tests) - completed_tests
    return {
        "assigned_tests": assigned_tests,
        "assigned_count": len(assigned_tests),
        "completed_count": completed_tests,
        "pending_count": pending_tests,
        "attempts_count": result_summary["attempts_count"] or 0,
        "average_score": result_summary["average_score"] or 0,
        "best_score": result_summary["best_score"] or 0,
        "recent_results": [dict(row) for row in recent_results],
    }


def get_subject_overview(user_id: int) -> list[dict[str, object]]:
    rows = get_db().execute(
        """
        SELECT subject,
               COUNT(*) AS total_tasks,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed_tasks,
               SUM(CASE WHEN status != 'Completed' THEN 1 ELSE 0 END) AS pending_tasks
        FROM tasks
        WHERE user_id = ?
        GROUP BY subject
        ORDER BY pending_tasks DESC, total_tasks DESC, subject COLLATE NOCASE ASC
        """,
        (user_id,),
    ).fetchall()

    overview: list[dict[str, object]] = []
    for row in rows:
        total = row["total_tasks"] or 0
        completed = row["completed_tasks"] or 0
        progress = round((completed / total) * 100, 1) if total else 0.0
        overview.append(
            {
                "subject": row["subject"],
                "total_tasks": total,
                "completed_tasks": completed,
                "pending_tasks": row["pending_tasks"] or 0,
                "progress": progress,
            }
        )
    return overview


def get_upcoming_schedule(user_id: int, days: int = 10) -> list[dict[str, object]]:
    today = date.today()
    end_date = today + timedelta(days=days)
    rows = get_db().execute(
        """
        SELECT id, title, subject, deadline, priority, status
        FROM tasks
        WHERE user_id = ?
          AND status != 'Completed'
          AND deadline BETWEEN ? AND ?
        ORDER BY deadline ASC, priority ASC, id ASC
        """,
        (user_id, today.isoformat(), end_date.isoformat()),
    ).fetchall()

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(row["deadline"], []).append(dict(row))
    return [{"date": key, "items": value} for key, value in grouped.items()]


def get_weekly_productivity(user_id: int, days: int = 7) -> dict[str, list[object]]:
    labels = [(date.today() - timedelta(days=offset)).isoformat() for offset in reversed(range(days))]
    created_rows = get_db().execute(
        """
        SELECT substr(created_at, 1, 10) AS created_day, COUNT(*) AS total
        FROM tasks
        WHERE user_id = ?
          AND substr(created_at, 1, 10) BETWEEN ? AND ?
        GROUP BY created_day
        """,
        (user_id, labels[0], labels[-1]),
    ).fetchall()
    created_map = {row["created_day"]: row["total"] for row in created_rows}
    created_series = [created_map.get(label, 0) for label in labels]
    return {"labels": labels, "created": created_series}


def get_completion_band(completion_rate: float) -> str:
    if completion_rate < 40:
        return "low"
    if completion_rate < 70:
        return "medium"
    return "high"


def get_dashboard_insights(
    statistics: dict[str, int],
    subject_overview: list[dict[str, object]],
    completion_rate: float,
    test_summary: dict[str, int],
    due_tomorrow: int,
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []

    if statistics["overdue"] > 0:
        insights.append({"type": "danger", "text": translate("insight_overdue", count=statistics["overdue"])})
    if due_tomorrow > 0:
        insights.append({"type": "warning", "text": translate("insight_due_tomorrow", count=due_tomorrow)})

    if subject_overview and subject_overview[0]["pending_tasks"] > 0:
        top_subject = subject_overview[0]
        insights.append(
            {
                "type": "info",
                "text": translate(
                    "insight_subject_focus",
                    subject=top_subject["subject"],
                    count=top_subject["pending_tasks"],
                ),
            }
        )

    completion_key = {
        "low": "insight_completion_low",
        "medium": "insight_completion_medium",
        "high": "insight_completion_high",
    }[get_completion_band(completion_rate)]
    insights.append({"type": "success", "text": translate(completion_key, percent=completion_rate)})

    if test_summary["tests_without_questions"] > 0:
        insights.append(
            {
                "type": "warning",
                "text": translate("insight_test_without_questions", count=test_summary["tests_without_questions"]),
            }
        )

    return insights


def get_user_initials(name: str) -> str:
    parts = [part.strip() for part in name.split() if part.strip()]
    if not parts:
        return "ST"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def infer_user_role(user: sqlite3.Row) -> str:
    if user["role"] == ROLE_TEACHER:
        return translate("profile_role_teacher")
    return translate("profile_role_student")


@app.route("/language/<lang_code>")
def set_language(lang_code: str):
    session["language"] = lang_code if lang_code in LANGUAGES else DEFAULT_LANGUAGE
    return redirect(safe_redirect_target())


@app.route("/")
def home():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", ROLE_STUDENT).strip().lower()
        group_name = request.form.get("group_name", "").strip()

        errors: list[str] = []
        if not name:
            errors.append(translate("full_name_required"))
        if not email:
            errors.append(translate("email_required"))
        if not password:
            errors.append(translate("password_required"))
        if password and not is_strong_password(password):
            errors.append(translate("password_weak"))
        if password != confirm_password:
            errors.append(translate("password_confirmation_mismatch"))
        if role not in ALLOWED_ROLES:
            errors.append(translate("registration_role_invalid"))
        if role == ROLE_STUDENT and not group_name:
            errors.append(translate("group_name_required_student"))
        if get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            errors.append(translate("account_exists"))

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("register.html")

        db = get_db()
        password_hash = generate_password_hash(password)
        if _column_exists(db, "users", "password_hash"):
            db.execute(
                """
                INSERT INTO users (name, email, password, password_hash, role, group_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    password_hash,
                    password_hash,
                    role,
                    group_name if role == ROLE_STUDENT and group_name else None,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO users (name, email, password, role, group_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    password_hash,
                    role,
                    group_name if role == ROLE_STUDENT and group_name else None,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        get_db().commit()
        if role == ROLE_STUDENT and group_name:
            upsert_study_group(group_name, created_by=None)
        flash(translate("registration_successful"), "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        password_hash = get_password_hash(user) if user is not None else ""
        if user is None or not password_hash or not check_password_hash(password_hash, password):
            flash(translate("invalid_email_or_password"), "danger")
            return render_template("login.html")

        user_role = user["role"] if "role" in user.keys() and user["role"] in ALLOWED_ROLES else ROLE_STUDENT
        session["language"] = get_current_language()
        session["user_id"] = user["id"]
        session["role"] = user_role
        session["user_name"] = user["name"]
        log_activity(action="login", entity_type="auth", entity_id=user["id"], details=f"email={email}")
        flash(translate("welcome_back_user", name=user["name"]), "success")
        next_url = request.args.get("next", "").strip()
        if next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    log_activity(action="logout", entity_type="auth", entity_id=session.get("user_id"))
    selected_language = get_current_language()
    session.clear()
    session["language"] = selected_language
    flash(translate("logged_out"), "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user_id = session["user_id"]

    if current_user_is_teacher():
        summary = get_dashboard_statistics(user_id)
        completion_rate = round((summary["completed"] / (summary["total"] or 1)) * 100, 1)
        completion_band = get_completion_band(completion_rate)
        teacher_overview = get_teacher_overview(user_id)
        recent_group_tasks = get_teacher_group_tasks(user_id, limit=8)
        recent_tasks = db.execute(
            """
            SELECT *
            FROM tasks
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 8
            """,
            (user_id,),
        ).fetchall()
        return render_template(
            "dashboard_teacher.html",
            summary=summary,
            completion_rate=completion_rate,
            completion_band=completion_band,
            teacher_overview=teacher_overview,
            recent_tasks=recent_tasks,
            recent_group_tasks=recent_group_tasks,
            available_groups=fetch_all_groups(),
        )

    filters = build_dashboard_filters()
    query_parts = ["SELECT * FROM tasks WHERE user_id = ?"]
    params: list[object] = [user_id]

    if filters["subject"]:
        query_parts.append("AND subject = ?")
        params.append(filters["subject"])
    if filters["status"]:
        query_parts.append("AND status = ?")
        params.append(filters["status"])
    if filters["priority"]:
        query_parts.append("AND priority = ?")
        params.append(filters["priority"])
    if filters["search"]:
        query_parts.append("AND (title LIKE ? OR description LIKE ?)")
        search_value = f"%{filters['search']}%"
        params.extend([search_value, search_value])

    query_parts.append(f"ORDER BY {get_sort_clause(filters['sort'])}")
    tasks = db.execute(" ".join(query_parts), tuple(params)).fetchall()
    summary = get_dashboard_statistics(user_id)
    subject_overview = get_subject_overview(user_id)
    test_summary = get_test_summary(user_id)
    student_tests = get_student_test_overview(user_id, (g.user["group_name"] or "").strip())
    due_tomorrow = db.execute(
        """
        SELECT COUNT(*)
        FROM tasks
        WHERE user_id = ?
          AND status != 'Completed'
          AND deadline = ?
        """,
        (user_id, (date.today() + timedelta(days=1)).isoformat()),
    ).fetchone()[0]
    completion_rate = round((summary["completed"] / (summary["total"] or 1)) * 100, 1)
    completion_band = get_completion_band(completion_rate)
    recommendations = get_dashboard_insights(summary, subject_overview, completion_rate, test_summary, due_tomorrow)
    upcoming_schedule = get_upcoming_schedule(user_id)
    student_group_tasks = get_student_group_tasks((g.user["group_name"] or "").strip(), limit=12)

    return render_template(
        "dashboard_student.html",
        tasks=tasks,
        statistics=summary,
        filters=filters,
        subjects=fetch_subjects(user_id),
        completion_rate=completion_rate,
        completion_band=completion_band,
        recommendations=recommendations,
        subjects_overview=subject_overview,
        upcoming_schedule=upcoming_schedule,
        test_summary=test_summary,
        student_tests=student_tests,
        student_group_tasks=student_group_tasks,
    )


@app.route("/group-tasks")
@role_required(ROLE_TEACHER)
def manage_group_tasks():
    selected_group = request.args.get("group", "").strip()
    query = ["SELECT * FROM group_tasks WHERE teacher_id = ?"]
    params: list[object] = [session["user_id"]]
    if selected_group:
        query.append("AND LOWER(assigned_group) = LOWER(?)")
        params.append(selected_group)
    query.append("ORDER BY deadline ASC, created_at DESC")
    rows = get_db().execute(" ".join(query), tuple(params)).fetchall()
    groups = fetch_all_groups()
    return render_template(
        "group_tasks.html",
        tasks=rows,
        groups=groups,
        selected_group=selected_group,
    )


@app.route("/group-tasks/add", methods=["GET", "POST"])
@role_required(ROLE_TEACHER)
def add_group_task():
    groups = fetch_all_groups()
    if request.method == "POST":
        form_data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "subject": request.form.get("subject", "").strip(),
            "deadline": request.form.get("deadline", "").strip(),
            "priority": request.form.get("priority", "").strip(),
            "status": request.form.get("status", "Pending").strip() or "Pending",
            "assigned_group": request.form.get("assigned_group", "").strip(),
        }

        errors = validate_task_form(form_data)
        if not form_data["assigned_group"]:
            errors.append("Группа обязательна для назначения.")
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("group_task_form.html", task=form_data, groups=groups)

        get_db().execute(
            """
            INSERT INTO group_tasks (
                teacher_id, assigned_group, title, description, subject, deadline, priority, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                form_data["assigned_group"],
                form_data["title"],
                form_data["description"],
                form_data["subject"],
                form_data["deadline"],
                form_data["priority"],
                form_data["status"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        get_db().commit()
        upsert_study_group(form_data["assigned_group"], created_by=session["user_id"])
        log_activity(
            action="group_task_create",
            entity_type="group_task",
            details=f"group={form_data['assigned_group']};title={form_data['title']}",
        )
        flash("Задача успешно назначена группе.", "success")
        return redirect(url_for("manage_group_tasks"))

    return render_template(
        "group_task_form.html",
        task={
            "title": "",
            "description": "",
            "subject": "",
            "deadline": "",
            "priority": "Medium",
            "status": "Pending",
            "assigned_group": "",
        },
        groups=groups,
    )


@app.route("/group-tasks/<int:task_id>/delete", methods=["POST"])
@role_required(ROLE_TEACHER)
def delete_group_task(task_id: int):
    task = get_teacher_group_task(task_id, session["user_id"])
    if task is None:
        flash("Задача группы не найдена.", "danger")
        return redirect(url_for("manage_group_tasks"))
    get_db().execute("DELETE FROM group_tasks WHERE id = ? AND teacher_id = ?", (task_id, session["user_id"]))
    get_db().commit()
    log_activity(action="group_task_delete", entity_type="group_task", entity_id=task_id)
    flash("Задача группы удалена.", "info")
    return redirect(url_for("manage_group_tasks"))


@app.route("/group-tasks/export.csv")
@role_required(ROLE_TEACHER)
def export_group_tasks_csv():
    selected_group = request.args.get("group", "").strip()
    query = ["SELECT * FROM group_tasks WHERE teacher_id = ?"]
    params: list[object] = [session["user_id"]]
    if selected_group:
        query.append("AND LOWER(assigned_group) = LOWER(?)")
        params.append(selected_group)
    query.append("ORDER BY deadline ASC, created_at DESC")
    rows = get_db().execute(" ".join(query), tuple(params)).fetchall()
    csv_rows: list[list[object]] = [
        ["Группа", "Название", "Описание", "Предмет", "Срок", "Приоритет", "Статус", "Создано"]
    ]
    for row in rows:
        csv_rows.append(
            [
                row["assigned_group"],
                row["title"],
                row["description"] or "",
                row["subject"],
                row["deadline"],
                translate_value(row["priority"], "priority"),
                translate_value(row["status"], "status"),
                row["created_at"],
            ]
        )
    return _csv_response(f"group_tasks_{date.today().isoformat()}", csv_rows)


@app.route("/tasks/add", methods=["GET", "POST"])
@login_required
def add_task():
    if request.method == "POST":
        form_data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "subject": request.form.get("subject", "").strip(),
            "deadline": request.form.get("deadline", "").strip(),
            "priority": request.form.get("priority", "").strip(),
            "status": request.form.get("status", "").strip(),
        }
        errors = validate_task_form(form_data)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("task_form.html", task=form_data, page_title_key="add_task_page_title")

        get_db().execute(
            """
            INSERT INTO tasks (user_id, title, description, subject, deadline, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                form_data["title"],
                form_data["description"],
                form_data["subject"],
                form_data["deadline"],
                form_data["priority"],
                form_data["status"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        get_db().commit()
        log_activity(action="task_create", entity_type="task", details=f"title={form_data['title']}")
        flash(translate("task_added_successfully"), "success")
        return redirect(url_for("dashboard"))

    return render_template(
        "task_form.html",
        task={
            "title": "",
            "description": "",
            "subject": "",
            "deadline": "",
            "priority": "Medium",
            "status": "Pending",
        },
        page_title_key="add_task_page_title",
    )


@app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id: int):
    task = get_user_task(task_id)
    if task is None:
        flash(translate("task_not_found"), "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        form_data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "subject": request.form.get("subject", "").strip(),
            "deadline": request.form.get("deadline", "").strip(),
            "priority": request.form.get("priority", "").strip(),
            "status": request.form.get("status", "").strip(),
        }
        errors = validate_task_form(form_data)
        if errors:
            for error in errors:
                flash(error, "danger")
            task_payload = dict(task)
            task_payload.update(form_data)
            return render_template("task_form.html", task=task_payload, page_title_key="edit_task_page_title")

        get_db().execute(
            """
            UPDATE tasks
            SET title = ?, description = ?, subject = ?, deadline = ?, priority = ?, status = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                form_data["title"],
                form_data["description"],
                form_data["subject"],
                form_data["deadline"],
                form_data["priority"],
                form_data["status"],
                task_id,
                session["user_id"],
            ),
        )
        get_db().commit()
        flash(translate("task_updated_successfully"), "success")
        return redirect(url_for("dashboard"))

    return render_template("task_form.html", task=task, page_title_key="edit_task_page_title")


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id: int):
    task = get_user_task(task_id)
    if task is None:
        flash(translate("task_not_found"), "danger")
        return redirect(url_for("dashboard"))

    get_db().execute(
        "DELETE FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, session["user_id"]),
    )
    get_db().commit()
    flash(translate("task_deleted_successfully"), "info")
    return redirect(url_for("dashboard"))


@app.route("/statistics")
@login_required
def statistics():
    db = get_db()
    user_id = session["user_id"]
    summary = get_dashboard_statistics(user_id)
    status_rows = db.execute(
        "SELECT status, COUNT(*) AS total FROM tasks WHERE user_id = ? GROUP BY status ORDER BY total DESC, status ASC",
        (user_id,),
    ).fetchall()
    subject_rows = db.execute(
        "SELECT subject, COUNT(*) AS total FROM tasks WHERE user_id = ? GROUP BY subject ORDER BY total DESC, subject ASC",
        (user_id,),
    ).fetchall()
    priority_rows = db.execute(
        """
        SELECT priority, COUNT(*) AS total
        FROM tasks
        WHERE user_id = ?
        GROUP BY priority
        ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END
        """,
        (user_id,),
    ).fetchall()

    total_tasks = summary["total"] or 1
    completion_rate = round((summary["completed"] / total_tasks) * 100, 1)
    completion_band = get_completion_band(completion_rate)
    weekly_productivity = get_weekly_productivity(user_id)
    test_summary = get_test_summary(user_id)

    status_chart = {
        "labels": [translate_value(row["status"], "status") for row in status_rows],
        "data": [row["total"] for row in status_rows],
    }
    subject_chart = {
        "labels": [row["subject"] for row in subject_rows],
        "data": [row["total"] for row in subject_rows],
    }
    overdue_chart = {
        "labels": [
            translate("chart_legend_overdue"),
            translate("chart_legend_due_soon"),
            translate("chart_legend_on_track"),
        ],
        "data": [
            summary["overdue"],
            summary["due_soon"],
            max(summary["total"] - summary["overdue"] - summary["due_soon"], 0),
        ],
    }

    return render_template(
        "statistics.html",
        summary=summary,
        status_rows=status_rows,
        subject_rows=subject_rows,
        priority_rows=priority_rows,
        completion_rate=completion_rate,
        completion_band=completion_band,
        weekly_productivity=weekly_productivity,
        status_chart=status_chart,
        subject_chart=subject_chart,
        overdue_chart=overdue_chart,
        test_summary=test_summary,
    )


def _csv_response(filename: str, rows: list[list[object]]) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    response = Response(output.getvalue(), content_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}.csv"
    return response


@app.route("/export/tasks.csv")
@login_required
def export_tasks_csv():
    rows = get_db().execute(
        """
        SELECT title, description, subject, deadline, priority, status, created_at
        FROM tasks
        WHERE user_id = ?
        ORDER BY deadline ASC, created_at DESC
        """,
        (session["user_id"],),
    ).fetchall()
    csv_rows: list[list[object]] = [
        [
            translate("export_col_title"),
            translate("export_col_description"),
            translate("export_col_subject"),
            translate("export_col_deadline"),
            translate("export_col_priority"),
            translate("export_col_status"),
            translate("export_col_created"),
        ]
    ]
    for row in rows:
        csv_rows.append(
            [
                row["title"],
                row["description"] or "",
                row["subject"],
                row["deadline"],
                translate_value(row["priority"], "priority"),
                translate_value(row["status"], "status"),
                row["created_at"],
            ]
        )
    return _csv_response(f"{translate('export_filename_tasks')}_{date.today().isoformat()}", csv_rows)


@app.route("/export/summary.csv")
@login_required
def export_summary_csv():
    summary = get_dashboard_statistics(session["user_id"])
    completion_rate = round((summary["completed"] / (summary["total"] or 1)) * 100, 1)
    test_summary = get_test_summary(session["user_id"])
    csv_rows: list[list[object]] = [
        [translate("export_col_metric"), translate("export_col_value")],
        [translate("metric_total_tasks"), summary["total"]],
        [translate("metric_completed_tasks"), summary["completed"]],
        [translate("metric_due_soon"), summary["due_soon"]],
        [translate("metric_overdue"), summary["overdue"]],
        [translate("metric_completion_rate"), completion_rate],
        [translate("metric_tests_created"), test_summary["tests_created"]],
        [translate("metric_tests_attempts"), test_summary["tests_attempts"]],
    ]
    return _csv_response(f"{translate('export_filename_summary')}_{date.today().isoformat()}", csv_rows)


app.register_blueprint(testing_bp)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
