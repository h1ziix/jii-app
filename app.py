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
site_tagline=Р•РґРёРЅР°СЏ С†РёС„СЂРѕРІР°СЏ Р°РєР°РґРµРјРёС‡РµСЃРєР°СЏ РїР»Р°С‚С„РѕСЂРјР° РђРўРЈ
nav_home=Р“Р»Р°РІРЅР°СЏ
nav_login=Р’РѕР№С‚Рё
nav_register=Р РµРіРёСЃС‚СЂР°С†РёСЏ
nav_dashboard=РџР°РЅРµР»СЊ
nav_add_task=Р”РѕР±Р°РІРёС‚СЊ Р·Р°РґР°С‡Сѓ
nav_statistics=РЎС‚Р°С‚РёСЃС‚РёРєР°
nav_logout=Р’С‹Р№С‚Рё
language_label=РЇР·С‹Рє
language_ru=Р РЈ
language_kk=ТљРђР—
home_page_title=Р“Р»Р°РІРЅР°СЏ
home_eyebrow=РџР»Р°С‚С„РѕСЂРјР° РђР»РјР°С‚РёРЅСЃРєРѕРіРѕ С‚РµС…РЅРѕР»РѕРіРёС‡РµСЃРєРѕРіРѕ СѓРЅРёРІРµСЂСЃРёС‚РµС‚Р°
home_heading=РЈРїСЂР°РІР»СЏР№С‚Рµ Р·Р°РґР°РЅРёСЏРјРё Рё СѓС‡РµР±РЅРѕР№ РЅР°РіСЂСѓР·РєРѕР№ РІ СЌРєРѕСЃРёСЃС‚РµРјРµ РђРўРЈ.
home_text=ATU Campus Planner РїРѕРјРѕРіР°РµС‚ СЃС‚СѓРґРµРЅС‚Р°Рј РђРўРЈ РїР»Р°РЅРёСЂРѕРІР°С‚СЊ СѓС‡РµР±Сѓ, РєРѕРЅС‚СЂРѕР»РёСЂРѕРІР°С‚СЊ РґРµРґР»Р°Р№РЅС‹ Рё РѕС‚СЃР»РµР¶РёРІР°С‚СЊ РїСЂРѕРіСЂРµСЃСЃ РІ РµРґРёРЅРѕРј С†РёС„СЂРѕРІРѕРј РєР°Р±РёРЅРµС‚Рµ.
create_account=РЎРѕР·РґР°С‚СЊ Р°РєРєР°СѓРЅС‚
log_in=Р’РѕР№С‚Рё
hero_point_1=РљРѕРЅС‚СЂРѕР»СЊ РґРµРґР»Р°Р№РЅРѕРІ
hero_point_2=РџР»Р°РЅРёСЂРѕРІР°РЅРёРµ РїРѕ РїСЂРµРґРјРµС‚Р°Рј
hero_point_3=РќР°РіР»СЏРґРЅР°СЏ Р°РЅР°Р»РёС‚РёРєР°
today_glance=РљСЂР°С‚РєРѕ РЅР° СЃРµРіРѕРґРЅСЏ
study_clearer_plan=РЈС‡РёС‚СЊСЃСЏ СЃ Р±РѕР»РµРµ РїРѕРЅСЏС‚РЅС‹Рј РїР»Р°РЅРѕРј
home_feature_1=РћС‚СЃР»РµР¶РёРІР°Р№С‚Рµ РѕР¶РёРґР°СЋС‰РёРµ, Р°РєС‚РёРІРЅС‹Рµ Рё Р·Р°РІРµСЂС€С‘РЅРЅС‹Рµ Р·Р°РґР°С‡Рё
home_feature_2=Р’С‹РґРµР»СЏР№С‚Рµ РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ Р·Р°РґР°С‡Рё РґРѕ С‚РѕРіРѕ, РєР°Рє РѕРЅРё СЃС‚Р°РЅСѓС‚ РїСЂРѕР±Р»РµРјРѕР№
home_feature_3=Р¤РёР»СЊС‚СЂСѓР№С‚Рµ Р·Р°РґР°С‡Рё РїРѕ РїСЂРµРґРјРµС‚Сѓ, РїСЂРёРѕСЂРёС‚РµС‚Сѓ Рё СЃС‚Р°С‚СѓСЃСѓ
home_feature_4=РђРЅР°Р»РёР·РёСЂСѓР№С‚Рµ СЃС‚Р°С‚РёСЃС‚РёРєСѓ РґР»СЏ Р±РѕР»РµРµ СЃС‚Р°Р±РёР»СЊРЅРѕР№ СѓСЃРїРµРІР°РµРјРѕСЃС‚Рё
task_control=РљРѕРЅС‚СЂРѕР»СЊ Р·Р°РґР°С‡
task_control_text=РЎРѕР·РґР°РІР°Р№С‚Рµ, СЂРµРґР°РєС‚РёСЂСѓР№С‚Рµ Рё СѓРґР°Р»СЏР№С‚Рµ Р·Р°РґР°РЅРёСЏ СЃ РїРѕР»РЅРѕР№ Р·Р°С‰РёС‚РѕР№ РІР»Р°РґРµР»СЊС†Р°.
deadline_focus=Р¤РѕРєСѓСЃ РЅР° РґРµРґР»Р°Р№РЅР°С…
deadline_focus_text=РЎСЂР°Р·Сѓ Р·Р°РјРµС‡Р°Р№С‚Рµ СЃСЂРѕС‡РЅС‹Рµ Рё РїСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ СѓС‡РµР±РЅС‹Рµ Р·Р°РґР°С‡Рё РЅР° РїР°РЅРµР»Рё.
smart_organization=РЈРјРЅР°СЏ РѕСЂРіР°РЅРёР·Р°С†РёСЏ
smart_organization_text=Р“СЂСѓРїРїРёСЂСѓР№С‚Рµ Р·Р°РґР°С‡Рё РїРѕ РїСЂРµРґРјРµС‚Р°Рј Рё СЃРѕСЂС‚РёСЂСѓР№С‚Рµ РїРѕ СЃСЂРѕРєСѓ, РїСЂРёРѕСЂРёС‚РµС‚Сѓ РёР»Рё РґР°С‚Рµ СЃРѕР·РґР°РЅРёСЏ.
register_page_title=Р РµРіРёСЃС‚СЂР°С†РёСЏ
register_eyebrow=РќРѕРІС‹Р№ Р°РєРєР°СѓРЅС‚
register_heading=РЎРѕР·РґР°Р№С‚Рµ СЃРІРѕС‘ СЃС‚СѓРґРµРЅС‡РµСЃРєРѕРµ РїСЂРѕСЃС‚СЂР°РЅСЃС‚РІРѕ
register_text=Р—Р°СЂРµРіРёСЃС‚СЂРёСЂСѓР№С‚РµСЃСЊ, С‡С‚РѕР±С‹ РЅР°С‡Р°С‚СЊ СѓРїСЂР°РІР»СЏС‚СЊ СѓС‡РµР±РЅС‹РјРё Р·Р°РґР°С‡Р°РјРё РІ Р»РёС‡РЅРѕР№ РїР°РЅРµР»Рё.
full_name=РџРѕР»РЅРѕРµ РёРјСЏ
email_address=Р­Р»РµРєС‚СЂРѕРЅРЅР°СЏ РїРѕС‡С‚Р°
password=РџР°СЂРѕР»СЊ
confirm_password=РџРѕРґС‚РІРµСЂРґРёС‚Рµ РїР°СЂРѕР»СЊ
register_button=Р—Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°С‚СЊСЃСЏ
already_have_account=РЈР¶Рµ РµСЃС‚СЊ Р°РєРєР°СѓРЅС‚?
login_here=Р’РѕР№РґРёС‚Рµ Р·РґРµСЃСЊ
login_page_title=Р’С…РѕРґ
login_eyebrow=РЎ РІРѕР·РІСЂР°С‰РµРЅРёРµРј
login_heading=Р’РѕР№РґРёС‚Рµ РІ СЃРІРѕСЋ РїР°РЅРµР»СЊ
login_text=РџРѕР»СѓС‡РёС‚Рµ Р±РµР·РѕРїР°СЃРЅС‹Р№ РґРѕСЃС‚СѓРї Рє Р·Р°РґР°С‡Р°Рј, РґРµРґР»Р°Р№РЅР°Рј Рё СЃС‚Р°С‚РёСЃС‚РёРєРµ.
login_button=Р’РѕР№С‚Рё
need_account=РќСѓР¶РµРЅ Р°РєРєР°СѓРЅС‚?
create_one_now=РЎРѕР·РґР°С‚СЊ СЃРµР№С‡Р°СЃ
dashboard_page_title=РџР°РЅРµР»СЊ
dashboard_eyebrow=РџР°РЅРµР»СЊ
dashboard_heading={name}, РґРµСЂР¶РёС‚Рµ СЃРµРјРµСЃС‚СЂ РїРѕРґ РєРѕРЅС‚СЂРѕР»РµРј.
dashboard_text=РџСЂРѕСЃРјР°С‚СЂРёРІР°Р№С‚Рµ РЅР°РіСЂСѓР·РєСѓ, СЃР»РµРґРёС‚Рµ Р·Р° РґРµРґР»Р°Р№РЅР°РјРё Рё РѕР±РЅРѕРІР»СЏР№С‚Рµ РїСЂРѕРіСЂРµСЃСЃ РІ РѕРґРЅРѕРј РјРµСЃС‚Рµ.
add_new_task=Р”РѕР±Р°РІРёС‚СЊ Р·Р°РґР°С‡Сѓ
total_tasks=Р’СЃРµРіРѕ Р·Р°РґР°С‡
total_tasks_text=Р’СЃРµ Р·Р°РґР°РЅРёСЏ РІ РІР°С€РµРј РїР»Р°РЅРёСЂРѕРІС‰РёРєРµ
completed=Р—Р°РІРµСЂС€РµРЅРѕ
completed_text=РЈСЃРїРµС€РЅРѕ РІС‹РїРѕР»РЅРµРЅРЅС‹Рµ Р·Р°РґР°С‡Рё
due_soon=РЎРєРѕСЂРѕ СЃСЂРѕРє
due_soon_text=Р”РµРґР»Р°Р№РЅС‹ РІ С‚РµС‡РµРЅРёРµ Р±Р»РёР¶Р°Р№С€РёС… 7 РґРЅРµР№
overdue=РџСЂРѕСЃСЂРѕС‡РµРЅРѕ
overdue_text_stat=РЎСЂРѕРє РёСЃС‚С‘Рє, Р·Р°РґР°С‡Р° РЅРµ Р·Р°РІРµСЂС€РµРЅР°
task_filters=Р¤РёР»СЊС‚СЂС‹ Р·Р°РґР°С‡
task_filters_text=РћС‚С„РёР»СЊС‚СЂСѓР№С‚Рµ СЃРїРёСЃРѕРє РїРѕ РїСЂРµРґРјРµС‚Сѓ, СЃС‚Р°С‚СѓСЃСѓ, РїСЂРёРѕСЂРёС‚РµС‚Сѓ, РєР»СЋС‡РµРІРѕРјСѓ СЃР»РѕРІСѓ Рё СЃРѕСЂС‚РёСЂРѕРІРєРµ.
search=РџРѕРёСЃРє
search_placeholder=РќР°Р·РІР°РЅРёРµ РёР»Рё РѕРїРёСЃР°РЅРёРµ
subject=РџСЂРµРґРјРµС‚
all_subjects=Р’СЃРµ РїСЂРµРґРјРµС‚С‹
status=РЎС‚Р°С‚СѓСЃ
all_statuses=Р’СЃРµ СЃС‚Р°С‚СѓСЃС‹
priority=РџСЂРёРѕСЂРёС‚РµС‚
all_priorities=Р’СЃРµ РїСЂРёРѕСЂРёС‚РµС‚С‹
sort_by=РЎРѕСЂС‚РёСЂРѕРІРєР°
sort_deadline_asc=РЎСЂРѕРє: СЃРЅР°С‡Р°Р»Р° Р±Р»РёР¶Р°Р№С€РёРµ
sort_deadline_desc=РЎСЂРѕРє: СЃРЅР°С‡Р°Р»Р° РїРѕР·РґРЅРёРµ
sort_created_desc=РЎРЅР°С‡Р°Р»Р° РЅРѕРІС‹Рµ
sort_created_asc=РЎРЅР°С‡Р°Р»Р° СЃС‚Р°СЂС‹Рµ
sort_priority_high=РџСЂРёРѕСЂРёС‚РµС‚: РІС‹СЃРѕРєРёР№ Рє РЅРёР·РєРѕРјСѓ
sort_status=РџРѕ СЃС‚Р°С‚СѓСЃСѓ
sort_subject=РџРѕ РїСЂРµРґРјРµС‚Сѓ
apply_filters=РџСЂРёРјРµРЅРёС‚СЊ
reset=РЎР±СЂРѕСЃРёС‚СЊ
your_tasks=Р’Р°С€Рё Р·Р°РґР°С‡Рё
your_tasks_text=РџСЂРѕСЃСЂРѕС‡РµРЅРЅС‹Рµ Р·Р°РґР°С‡Рё РІС‹РґРµР»РµРЅС‹, С‡С‚РѕР±С‹ РІС‹ СЃСЂР°Р·Сѓ РІРёРґРµР»Рё СЂРёСЃРєРё.
no_description=Р”Р»СЏ СЌС‚РѕР№ Р·Р°РґР°С‡Рё РѕРїРёСЃР°РЅРёРµ РЅРµ СѓРєР°Р·Р°РЅРѕ.
deadline_label=РЎСЂРѕРє
created_label=РЎРѕР·РґР°РЅРѕ
overdue_badge=РџСЂРѕСЃСЂРѕС‡РµРЅРѕ
edit=Р РµРґР°РєС‚РёСЂРѕРІР°С‚СЊ
delete=РЈРґР°Р»РёС‚СЊ
delete_confirm=РЈРґР°Р»РёС‚СЊ СЌС‚Сѓ Р·Р°РґР°С‡Сѓ Р±РµР· РІРѕР·РјРѕР¶РЅРѕСЃС‚Рё РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРёСЏ?
no_tasks_found=Р—Р°РґР°С‡Рё РЅРµ РЅР°Р№РґРµРЅС‹
no_tasks_text=РџРѕРїСЂРѕР±СѓР№С‚Рµ РёР·РјРµРЅРёС‚СЊ С„РёР»СЊС‚СЂС‹ РёР»Рё РґРѕР±Р°РІСЊС‚Рµ РЅРѕРІСѓСЋ СѓС‡РµР±РЅСѓСЋ Р·Р°РґР°С‡Сѓ.
create_first_task=РЎРѕР·РґР°С‚СЊ РїРµСЂРІСѓСЋ Р·Р°РґР°С‡Сѓ
task_management=РЈРїСЂР°РІР»РµРЅРёРµ Р·Р°РґР°С‡Р°РјРё
task_form_text=Р—Р°С„РёРєСЃРёСЂСѓР№С‚Рµ РІР°Р¶РЅС‹Рµ РґРµС‚Р°Р»Рё, С‡С‚РѕР±С‹ Р·Р°РґР°РЅРёСЏ Р±С‹Р»Рѕ Р»РµРіС‡Рµ РїР»Р°РЅРёСЂРѕРІР°С‚СЊ Рё РІС‹РїРѕР»РЅСЏС‚СЊ.
add_task_page_title=Р”РѕР±Р°РІРёС‚СЊ Р·Р°РґР°С‡Сѓ
edit_task_page_title=Р РµРґР°РєС‚РёСЂРѕРІР°С‚СЊ Р·Р°РґР°С‡Сѓ
task_title=РќР°Р·РІР°РЅРёРµ Р·Р°РґР°С‡Рё
task_title_placeholder=РќР°РїСЂРёРјРµСЂ: РџСЂРµР·РµРЅС‚Р°С†РёСЏ РїРѕ РїСЂРѕРµРєС‚Сѓ Р±Р°Р·С‹ РґР°РЅРЅС‹С…
description=РћРїРёСЃР°РЅРёРµ
description_placeholder=РћРїРёС€РёС‚Рµ С‚СЂРµР±РѕРІР°РЅРёСЏ, РјР°С‚РµСЂРёР°Р»С‹ РёР»Рё СЃР»РµРґСѓСЋС‰РёРµ С€Р°РіРё
subject_placeholder=РќР°РїСЂРёРјРµСЂ: РџСЂРѕРіСЂР°РјРјРЅР°СЏ РёРЅР¶РµРЅРµСЂРёСЏ
deadline=Р”РµРґР»Р°Р№РЅ
cancel=РћС‚РјРµРЅР°
statistics_page_title=РЎС‚Р°С‚РёСЃС‚РёРєР°
statistics_eyebrow=РЎС‚Р°С‚РёСЃС‚РёРєР°
statistics_heading=РђРЅР°Р»РёС‚РёРєР° СѓС‡РµР±РЅРѕР№ РїСЂРѕРґСѓРєС‚РёРІРЅРѕСЃС‚Рё
statistics_text=РђРЅР°Р»РёР·РёСЂСѓР№С‚Рµ СЂР°СЃРїСЂРµРґРµР»РµРЅРёРµ Р·Р°РґР°С‡, С‡С‚РѕР±С‹ РїСЂРёРЅРёРјР°С‚СЊ Р±РѕР»РµРµ С‚РѕС‡РЅС‹Рµ СЂРµС€РµРЅРёСЏ РІ РїР»Р°РЅРёСЂРѕРІР°РЅРёРё.
recorded_in_planner=Р—Р°С„РёРєСЃРёСЂРѕРІР°РЅРѕ РІ РїР»Р°РЅРёСЂРѕРІС‰РёРєРµ
completed_successfully=РћС‚РјРµС‡РµРЅРѕ РєР°Рє СѓСЃРїРµС€РЅРѕ РІС‹РїРѕР»РЅРµРЅРЅРѕРµ
due_soon_stat_text=РЎСЂРѕРє РЅР°СЃС‚СѓРїРёС‚ РІ С‚РµС‡РµРЅРёРµ 7 РґРЅРµР№
overdue_stat_text=РўСЂРµР±СѓРµС‚ РЅРµРјРµРґР»РµРЅРЅРѕРіРѕ РІРЅРёРјР°РЅРёСЏ
completion_rate=РџСЂРѕС†РµРЅС‚ РІС‹РїРѕР»РЅРµРЅРёСЏ
completion_rate_text=Р‘С‹СЃС‚СЂС‹Р№ РІР·РіР»СЏРґ РЅР° РґРѕР»СЋ СѓР¶Рµ Р·Р°РІРµСЂС€С‘РЅРЅРѕР№ СЂР°Р±РѕС‚С‹.
tasks_by_status=Р—Р°РґР°С‡Рё РїРѕ СЃС‚Р°С‚СѓСЃСѓ
tasks_by_status_text=РџРѕСЃРјРѕС‚СЂРёС‚Рµ Р±Р°Р»Р°РЅСЃ РјРµР¶РґСѓ РѕР¶РёРґР°СЋС‰РёРјРё, Р°РєС‚РёРІРЅС‹РјРё Рё Р·Р°РІРµСЂС€С‘РЅРЅС‹РјРё Р·Р°РґР°С‡Р°РјРё.
no_status_data=Пока нет данных по статусам.
tasks_by_subject=Р—Р°РґР°С‡Рё РїРѕ РїСЂРµРґРјРµС‚Р°Рј
tasks_by_subject_text=РћРїСЂРµРґРµР»РёС‚Рµ, РєР°РєРёРµ РґРёСЃС†РёРїР»РёРЅС‹ С‚СЂРµР±СѓСЋС‚ Р±РѕР»СЊС€Рµ РІСЃРµРіРѕ РІРЅРёРјР°РЅРёСЏ.
no_subject_data=Пока нет данных по предметам.
tasks_by_priority=Р—Р°РґР°С‡Рё РїРѕ РїСЂРёРѕСЂРёС‚РµС‚Сѓ
tasks_by_priority_text=РџСЂРѕРІРµСЂСЊС‚Рµ, СЃРѕСЃС‚РѕРёС‚ Р»Рё РІР°С€Р° РЅР°РіСЂСѓР·РєР° РІ РѕСЃРЅРѕРІРЅРѕРј РёР· СЃСЂРѕС‡РЅС‹С… РёР»Рё РѕР±С‹С‡РЅС‹С… Р·Р°РґР°С‡.
no_priority_data=Пока нет данных по приоритетам.
please_login_continue=РџРѕР¶Р°Р»СѓР№СЃС‚Р°, РІРѕР№РґРёС‚Рµ РІ СЃРёСЃС‚РµРјСѓ, С‡С‚РѕР±С‹ РїСЂРѕРґРѕР»Р¶РёС‚СЊ.
full_name_required=РџРѕР»РЅРѕРµ РёРјСЏ РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ.
email_required=Р­Р»РµРєС‚СЂРѕРЅРЅР°СЏ РїРѕС‡С‚Р° РѕР±СЏР·Р°С‚РµР»СЊРЅР°.
password_required=РџР°СЂРѕР»СЊ РѕР±СЏР·Р°С‚РµР»РµРЅ.
password_min_length=РџР°СЂРѕР»СЊ РґРѕР»Р¶РµРЅ СЃРѕРґРµСЂР¶Р°С‚СЊ РЅРµ РјРµРЅРµРµ 6 СЃРёРјРІРѕР»РѕРІ.
password_confirmation_mismatch=РџРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РїР°СЂРѕР»СЏ РЅРµ СЃРѕРІРїР°РґР°РµС‚.
account_exists=РђРєРєР°СѓРЅС‚ СЃ С‚Р°РєРёРј Р°РґСЂРµСЃРѕРј СЌР»РµРєС‚СЂРѕРЅРЅРѕР№ РїРѕС‡С‚С‹ СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚.
registration_successful=Р РµРіРёСЃС‚СЂР°С†РёСЏ РїСЂРѕС€Р»Р° СѓСЃРїРµС€РЅРѕ. РўРµРїРµСЂСЊ РІС‹ РјРѕР¶РµС‚Рµ РІРѕР№С‚Рё.
invalid_email_or_password=РќРµРІРµСЂРЅР°СЏ РїРѕС‡С‚Р° РёР»Рё РїР°СЂРѕР»СЊ.
welcome_back_user=РЎ РІРѕР·РІСЂР°С‰РµРЅРёРµРј, {name}!
logged_out=Р’С‹ РІС‹С€Р»Рё РёР· Р°РєРєР°СѓРЅС‚Р°.
validation_required=РџРѕР»Рµ В«{field}В» РѕР±СЏР·Р°С‚РµР»СЊРЅРѕ.
deadline_format=РџРѕР»Рµ РґРµРґР»Р°Р№РЅР° РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ РІ С„РѕСЂРјР°С‚Рµ Р“Р“Р“Р“-РњРњ-Р”Р”.
task_not_found=Р—Р°РґР°С‡Р° РЅРµ РЅР°Р№РґРµРЅР° РёР»Рё РґРѕСЃС‚СѓРї Р·Р°РїСЂРµС‰С‘РЅ.
task_added_successfully=Р—Р°РґР°С‡Р° СѓСЃРїРµС€РЅРѕ РґРѕР±Р°РІР»РµРЅР°.
task_updated_successfully=Р—Р°РґР°С‡Р° СѓСЃРїРµС€РЅРѕ РѕР±РЅРѕРІР»РµРЅР°.
task_deleted_successfully=Р—Р°РґР°С‡Р° СѓСЃРїРµС€РЅРѕ СѓРґР°Р»РµРЅР°.
task_title_field=РќР°Р·РІР°РЅРёРµ Р·Р°РґР°С‡Рё
subject_field=РџСЂРµРґРјРµС‚
deadline_field=Р”РµРґР»Р°Р№РЅ
priority_field=РџСЂРёРѕСЂРёС‚РµС‚
status_field=РЎС‚Р°С‚СѓСЃ
status_pending=РћР¶РёРґР°РµС‚
status_in_progress=Р’ РїСЂРѕС†РµСЃСЃРµ
status_completed=Р—Р°РІРµСЂС€РµРЅРѕ
priority_high=Р’С‹СЃРѕРєРёР№
priority_medium=РЎСЂРµРґРЅРёР№
priority_low=РќРёР·РєРёР№
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
site_tagline=РђРўРЈ-РґС‹ТЈ Р±С–СЂС‹ТЈТ“Р°Р№ С†РёС„СЂР»С‹Т› Р°РєР°РґРµРјРёСЏР»С‹Т› РїР»Р°С‚С„РѕСЂРјР°СЃС‹
nav_home=Р‘Р°СЃС‚С‹ Р±РµС‚
nav_login=РљС–СЂСѓ
nav_register=РўС–СЂРєРµР»Сѓ
nav_dashboard=Р‘Р°СЃТ›Р°СЂСѓ РїР°РЅРµР»С–
nav_add_task=РўР°РїСЃС‹СЂРјР° Т›РѕСЃСѓ
nav_statistics=РЎС‚Р°С‚РёСЃС‚РёРєР°
nav_logout=РЁС‹Т“Сѓ
language_label=РўС–Р»
language_ru=Р РЈ
language_kk=ТљРђР—
home_page_title=Р‘Р°СЃС‚С‹ Р±РµС‚
home_eyebrow=РђР»РјР°С‚С‹ С‚РµС…РЅРѕР»РѕРіРёСЏР»С‹Т› СѓРЅРёРІРµСЂСЃРёС‚РµС‚С–РЅРµ Р°СЂРЅР°Р»Т“Р°РЅ РїР»Р°С‚С„РѕСЂРјР°
home_heading=РђРўРЈ СЌРєРѕР¶ТЇР№РµСЃС–РЅРґРµ С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂ РјРµРЅ РѕТ›Сѓ Р¶ТЇРєС‚РµРјРµСЃС–РЅ Р±Р°СЃТ›Р°СЂС‹ТЈС‹Р·.
home_text=ATU Campus Planner РђРўРЈ СЃС‚СѓРґРµРЅС‚С‚РµСЂС–РЅРµ РѕТ›СѓС‹РЅ Р¶РѕСЃРїР°СЂР»Р°СѓТ“Р°, РґРµРґР»Р°Р№РЅРґР°СЂРґС‹ Р±Р°Т›С‹Р»Р°СѓТ“Р° Р¶У™РЅРµ РїСЂРѕРіСЂРµСЃС‚С– Р±С–СЂС‹ТЈТ“Р°Р№ С†РёС„СЂР»С‹Т› РєР°Р±РёРЅРµС‚С‚Рµ Т›Р°РґР°Т“Р°Р»Р°СѓТ“Р° РєУ©РјРµРєС‚РµСЃРµРґС–.
create_account=РђРєРєР°СѓРЅС‚ Р°С€Сѓ
log_in=РљС–СЂСѓ
hero_point_1=Р”РµРґР»Р°Р№РЅРґР°СЂРґС‹ Р±Р°Т›С‹Р»Р°Сѓ
hero_point_2=РџУ™РЅРґРµСЂ Р±РѕР№С‹РЅС€Р° Р¶РѕСЃРїР°СЂР»Р°Сѓ
hero_point_3=РљУ©СЂРЅРµРєС– Р°РЅР°Р»РёС‚РёРєР°
today_glance=Р‘ТЇРіС–РЅРіС– Т›С‹СЃТ›Р°С€Р° С€РѕР»Сѓ
study_clearer_plan=РћТ›СѓРґС‹ РЅР°Т›С‚С‹ Р¶РѕСЃРїР°СЂРјРµРЅ Р¶Р°Р»Т“Р°СЃС‚С‹СЂС‹ТЈС‹Р·
home_feature_1=РљТЇС‚С–Р»СѓРґРµ, РѕСЂС‹РЅРґР°Р»С‹Рї Р¶Р°С‚С‹СЂ Р¶У™РЅРµ Р°СЏТ›С‚Р°Р»Т“Р°РЅ С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂРґС‹ Р±Р°Т›С‹Р»Р°ТЈС‹Р·
home_feature_2=РњУ™СЃРµР»Рµ С‚СѓС‹РЅРґР°РјР°Р№ С‚Т±СЂС‹Рї РјРµСЂР·С–РјС– У©С‚РєРµРЅ Р¶Т±РјС‹СЃС‚Р°СЂРґС‹ Р±РµР»РіС–Р»РµТЈС–Р·
home_feature_3=РўР°РїСЃС‹СЂРјР°Р»Р°СЂРґС‹ РїУ™РЅ, Р±Р°СЃС‹РјРґС‹Т› РЅРµРјРµСЃРµ РјУ™СЂС‚РµР±Рµ Р±РѕР№С‹РЅС€Р° СЃТЇР·РіС–РґРµРЅ У©С‚РєС–Р·С–ТЈС–Р·
home_feature_4=Т®Р»РіРµСЂС–РјРґС– С‚Т±СЂР°Т›С‚С‹ РµС‚Сѓ ТЇС€С–РЅ СЃС‚Р°С‚РёСЃС‚РёРєР°РЅС‹ С‚Р°Р»РґР°ТЈС‹Р·
task_control=РўР°РїСЃС‹СЂРјР°Р»Р°СЂРґС‹ Р±Р°СЃТ›Р°СЂСѓ
task_control_text=РўР°РїСЃС‹СЂРјР°Р»Р°СЂРґС‹ РёРµСЃС–РЅРµ Т“Р°РЅР° Т›РѕР»Р¶РµС‚С–РјРґС– Т›РѕСЂТ“Р°РЅС‹СЃРїРµРЅ Т›Т±СЂС‹ТЈС‹Р·, У©ТЈРґРµТЈС–Р· Р¶У™РЅРµ У©С€С–СЂС–ТЈС–Р·.
deadline_focus=Р”РµРґР»Р°Р№РЅТ“Р° РЅР°Р·Р°СЂ
deadline_focus_text=Р–РµРґРµР» Р¶У™РЅРµ РјРµСЂР·С–РјС– У©С‚РєРµРЅ РѕТ›Сѓ С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂС‹РЅ РїР°РЅРµР»СЊРґРµРЅ Р±С–СЂРґРµРЅ РєУ©СЂС–ТЈС–Р·.
smart_organization=РђТ›С‹Р»РґС‹ Т±Р№С‹РјРґР°СЃС‚С‹СЂСѓ
smart_organization_text=РўР°РїСЃС‹СЂРјР°Р»Р°СЂРґС‹ РїУ™РЅ Р±РѕР№С‹РЅС€Р° С‚РѕРїС‚Р°СЃС‚С‹СЂС‹Рї, РјРµСЂР·С–РјС–РЅРµ, Р±Р°СЃС‹РјРґС‹Т“С‹РЅР° РЅРµРјРµСЃРµ Т›Т±СЂС‹Р»Т“Р°РЅ СѓР°Т›С‹С‚С‹РЅР° Т›Р°СЂР°Р№ СЃТ±СЂС‹РїС‚Р°ТЈС‹Р·.
register_page_title=РўС–СЂРєРµР»Сѓ
register_eyebrow=Р–Р°ТЈР° Р°РєРєР°СѓРЅС‚
register_heading=УЁР·С–ТЈС–Р·РґС–ТЈ СЃС‚СѓРґРµРЅС‚С‚С–Рє РєРµТЈС–СЃС‚С–РіС–ТЈС–Р·РґС– Р¶Р°СЃР°ТЈС‹Р·
register_text=Р–РµРєРµ РїР°РЅРµР»СЊ Р°СЂТ›С‹Р»С‹ РѕТ›Сѓ С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂС‹РЅ Р±Р°СЃТ›Р°СЂСѓРґС‹ Р±Р°СЃС‚Р°Сѓ ТЇС€С–РЅ С‚С–СЂРєРµР»С–ТЈС–Р·.
full_name=РўРѕР»С‹Т› Р°С‚С‹-Р¶У©РЅС–
email_address=Р­Р»РµРєС‚СЂРѕРЅРґС‹Т› РїРѕС€С‚Р°
password=ТљТ±РїРёСЏСЃУ©Р·
confirm_password=ТљТ±РїРёСЏСЃУ©Р·РґС– СЂР°СЃС‚Р°ТЈС‹Р·
register_button=РўС–СЂРєРµР»Сѓ
already_have_account=РђРєРєР°СѓРЅС‚С‹ТЈС‹Р· Р±Р°СЂ РјР°?
login_here=РћСЃС‹ Р¶РµСЂРґРµРЅ РєС–СЂС–ТЈС–Р·
login_page_title=РљС–СЂСѓ
login_eyebrow=ТљРѕС€ РєРµР»РґС–ТЈС–Р·
login_heading=РџР°РЅРµР»СЊРіРµ РєС–СЂС–ТЈС–Р·
login_text=РўР°РїСЃС‹СЂРјР°Р»Р°СЂТ“Р°, РґРµРґР»Р°Р№РЅРґР°СЂТ“Р° Р¶У™РЅРµ СЃС‚Р°С‚РёСЃС‚РёРєР°Т“Р° Т›Р°СѓС–РїСЃС–Р· Т›РѕР» Р¶РµС‚РєС–Р·С–ТЈС–Р·.
login_button=РљС–СЂСѓ
need_account=РђРєРєР°СѓРЅС‚ РєРµСЂРµРє РїРµ?
create_one_now=ТљР°Р·С–СЂ Р°С€Сѓ
dashboard_page_title=Р‘Р°СЃТ›Р°СЂСѓ РїР°РЅРµР»С–
dashboard_eyebrow=Р‘Р°СЃТ›Р°СЂСѓ РїР°РЅРµР»С–
dashboard_heading={name}, СЃРµРјРµСЃС‚СЂС–ТЈС–Р·РґС– Р±Р°Т›С‹Р»Р°СѓРґР° Т±СЃС‚Р°ТЈС‹Р·.
dashboard_text=Р–ТЇРєС‚РµРјРµРЅС– Т›Р°СЂР°Рї С€С‹Т“С‹ТЈС‹Р·, РґРµРґР»Р°Р№РЅРґР°СЂРґС‹ Р±Р°Т›С‹Р»Р°ТЈС‹Р· Р¶У™РЅРµ РїСЂРѕРіСЂРµСЃС‚С– Р±С–СЂ Р¶РµСЂРґРµРЅ Р¶Р°ТЈР°СЂС‚С‹ТЈС‹Р·.
add_new_task=Р–Р°ТЈР° С‚Р°РїСЃС‹СЂРјР° Т›РѕСЃСѓ
total_tasks=Р‘Р°СЂР»С‹Т› С‚Р°РїСЃС‹СЂРјР°
total_tasks_text=Р–РѕСЃРїР°СЂР»Р°Т“С‹С€С‚Р°Т“С‹ Р±Р°СЂР»С‹Т› Р¶Т±РјС‹СЃ
completed=РђСЏТ›С‚Р°Р»Т“Р°РЅ
completed_text=РЎУ™С‚С‚С– РѕСЂС‹РЅРґР°Р»Т“Р°РЅ С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂ
due_soon=Р–Р°Т›С‹РЅРґР° С‚Р°РїСЃС‹СЂСѓ РєРµСЂРµРє
due_soon_text=РљРµР»РµСЃС– 7 РєТЇРЅ С–С€С–РЅРґРµРіС– РґРµРґР»Р°Р№РЅРґР°СЂ
overdue=РњРµСЂР·С–РјС– У©С‚РєРµРЅ
overdue_text_stat=РњРµСЂР·С–РјС– У©С‚С–Рї РєРµС‚РєРµРЅ Р¶У™РЅРµ Р°СЏТ›С‚Р°Р»РјР°Т“Р°РЅ
task_filters=РўР°РїСЃС‹СЂРјР° СЃТЇР·РіС–Р»РµСЂС–
task_filters_text=РўС–Р·С–РјРґС– РїУ™РЅ, РјУ™СЂС‚РµР±Рµ, Р±Р°СЃС‹РјРґС‹Т›, РєС–Р»С‚ СЃУ©Р· Р¶У™РЅРµ СЃТ±СЂС‹РїС‚Р°Сѓ Р±РѕР№С‹РЅС€Р° С‚Р°СЂС‹Р»С‚С‹ТЈС‹Р·.
search=Р†Р·РґРµСѓ
search_placeholder=РђС‚Р°СѓС‹ РЅРµРјРµСЃРµ СЃРёРїР°С‚С‚Р°РјР°СЃС‹
subject=РџУ™РЅ
all_subjects=Р‘Р°СЂР»С‹Т› РїУ™РЅ
status=РњУ™СЂС‚РµР±Рµ
all_statuses=Р‘Р°СЂР»С‹Т› РјУ™СЂС‚РµР±Рµ
priority=Р‘Р°СЃС‹РјРґС‹Т›
all_priorities=Р‘Р°СЂР»С‹Т› Р±Р°СЃС‹РјРґС‹Т›
sort_by=РЎТ±СЂС‹РїС‚Р°Сѓ
sort_deadline_asc=РњРµСЂР·С–Рј: Р¶Р°Т›С‹РЅС‹ Р°Р»РґС‹РјРµРЅ
sort_deadline_desc=РњРµСЂР·С–Рј: Р°Р»С‹СЃС‹ Р°Р»РґС‹РјРµРЅ
sort_created_desc=РђР»РґС‹РјРµРЅ Р¶Р°ТЈР°Р»Р°СЂС‹
sort_created_asc=РђР»РґС‹РјРµРЅ РµСЃРєС–Р»РµСЂС–
sort_priority_high=Р‘Р°СЃС‹РјРґС‹Т›: Р¶РѕТ“Р°СЂС‹РґР°РЅ С‚У©РјРµРЅРіРµ
sort_status=РњУ™СЂС‚РµР±Рµ Р±РѕР№С‹РЅС€Р°
sort_subject=РџУ™РЅ Р±РѕР№С‹РЅС€Р°
apply_filters=ТљРѕР»РґР°РЅСѓ
reset=ТљР°Р»РїС‹РЅР° РєРµР»С‚С–СЂСѓ
your_tasks=РЎС–Р·РґС–ТЈ С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂС‹ТЈС‹Р·
your_tasks_text=ТљР°СѓС–РїС‚С– Р±С–СЂРґРµРЅ РєУ©СЂСѓ ТЇС€С–РЅ РјРµСЂР·С–РјС– У©С‚РєРµРЅ Р¶Т±РјС‹СЃС‚Р°СЂ РµСЂРµРєС€РµР»РµРЅС–Рї РєУ©СЂСЃРµС‚С–Р»РµРґС–.
no_description=Р‘Т±Р» С‚Р°РїСЃС‹СЂРјР°Т“Р° СЃРёРїР°С‚С‚Р°РјР° РµРЅРіС–Р·С–Р»РјРµРіРµРЅ.
deadline_label=Р”РµРґР»Р°Р№РЅ
created_label=ТљТ±СЂС‹Р»Т“Р°РЅ СѓР°Т›С‹С‚С‹
overdue_badge=РњРµСЂР·С–РјС– У©С‚РєРµРЅ
edit=УЁТЈРґРµСѓ
delete=УЁС€С–СЂСѓ
delete_confirm=Р‘Т±Р» С‚Р°РїСЃС‹СЂРјР°РЅС‹ Р±С–СЂР¶РѕР»Р° У©С€С–СЂРіС–ТЈС–Р· РєРµР»Рµ РјРµ?
no_tasks_found=РўР°РїСЃС‹СЂРјР°Р»Р°СЂ С‚Р°Р±С‹Р»РјР°РґС‹
no_tasks_text=РЎТЇР·РіС–Р»РµСЂРґС– У©Р·РіРµСЂС‚С–Рї РєУ©СЂС–ТЈС–Р· РЅРµРјРµСЃРµ Р¶Р°ТЈР° РѕТ›Сѓ С‚Р°РїСЃС‹СЂРјР°СЃС‹РЅ Т›РѕСЃС‹ТЈС‹Р·.
create_first_task=РђР»Т“Р°С€Т›С‹ С‚Р°РїСЃС‹СЂРјР°РЅС‹ Р¶Р°СЃР°Сѓ
task_management=РўР°РїСЃС‹СЂРјР°Р»Р°СЂРґС‹ Р±Р°СЃТ›Р°СЂСѓ
task_form_text=Р–Т±РјС‹СЃС‚С‹ Р¶РѕСЃРїР°СЂР»Р°Сѓ РјРµРЅ РѕСЂС‹РЅРґР°СѓРґС‹ Р¶РµТЈС–Р»РґРµС‚Сѓ ТЇС€С–РЅ РјР°ТЈС‹Р·РґС‹ РґРµСЂРµРєС‚РµСЂРґС– РµРЅРіС–Р·С–ТЈС–Р·.
add_task_page_title=РўР°РїСЃС‹СЂРјР° Т›РѕСЃСѓ
edit_task_page_title=РўР°РїСЃС‹СЂРјР°РЅС‹ У©ТЈРґРµСѓ
task_title=РўР°РїСЃС‹СЂРјР° Р°С‚Р°СѓС‹
task_title_placeholder=РњС‹СЃР°Р»С‹: Р”РµСЂРµРєТ›РѕСЂ Р¶РѕР±Р°СЃС‹ Р±РѕР№С‹РЅС€Р° РїСЂРµР·РµРЅС‚Р°С†РёСЏ
description=РЎРёРїР°С‚С‚Р°РјР°
description_placeholder=РўР°Р»Р°РїС‚Р°СЂРґС‹, РјР°С‚РµСЂРёР°Р»РґР°СЂРґС‹ РЅРµРјРµСЃРµ РєРµР»РµСЃС– Т›Р°РґР°РјРґР°СЂРґС‹ Р¶Р°Р·С‹ТЈС‹Р·
subject_placeholder=РњС‹СЃР°Р»С‹: Р‘Р°Т“РґР°СЂР»Р°РјР°Р»С‹Т› РёРЅР¶РµРЅРµСЂРёСЏ
deadline=Р”РµРґР»Р°Р№РЅ
cancel=Р‘Р°СЃ С‚Р°СЂС‚Сѓ
statistics_page_title=РЎС‚Р°С‚РёСЃС‚РёРєР°
statistics_eyebrow=РЎС‚Р°С‚РёСЃС‚РёРєР°
statistics_heading=РћТ›Сѓ У©РЅС–РјРґС–Р»С–РіС–РЅС–ТЈ С‚Р°Р»РґР°СѓС‹
statistics_text=Р–РѕСЃРїР°СЂР»Р°СѓРґР° РґУ™Р»С–СЂРµРє С€РµС€С–Рј Т›Р°Р±С‹Р»РґР°Сѓ ТЇС€С–РЅ С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂРґС‹ТЈ Р±У©Р»С–РЅСѓС–РЅ С‚Р°Р»РґР°ТЈС‹Р·.
recorded_in_planner=Р–РѕСЃРїР°СЂР»Р°Т“С‹С€С‚Р° С‚С–СЂРєРµР»РіРµРЅ
completed_successfully=РЎУ™С‚С‚С– Р°СЏТ›С‚Р°Р»РґС‹ РґРµРї Р±РµР»РіС–Р»РµРЅРіРµРЅ
due_soon_stat_text=7 РєТЇРЅ С–С€С–РЅРґРµ С‚Р°РїСЃС‹СЂСѓ Т›Р°Р¶РµС‚
overdue_stat_text=Р–РµРґРµР» РЅР°Р·Р°СЂ Р°СѓРґР°СЂСѓРґС‹ Т›Р°Р¶РµС‚ РµС‚РµРґС–
completion_rate=РћСЂС‹РЅРґР°Р»Сѓ РїР°Р№С‹Р·С‹
completion_rate_text=РђСЏТ›С‚Р°Р»Т“Р°РЅ Р¶Т±РјС‹СЃС‚С‹ТЈ ТЇР»РµСЃС–РЅ Р¶С‹Р»РґР°Рј Р±Р°Т“Р°Р»Р°Сѓ.
tasks_by_status=РњУ™СЂС‚РµР±Рµ Р±РѕР№С‹РЅС€Р° С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂ
tasks_by_status_text=РљТЇС‚С–Р»СѓРґРµ, РѕСЂС‹РЅРґР°Р»С‹Рї Р¶Р°С‚С‹СЂ Р¶У™РЅРµ Р°СЏТ›С‚Р°Р»Т“Р°РЅ Р¶Т±РјС‹СЃС‚Р°СЂРґС‹ТЈ Р°СЂР°Т›Р°С‚С‹РЅР°СЃС‹РЅ РєУ©СЂС–ТЈС–Р·.
no_status_data=Әзірге мәртебе бойынша дерек жоқ.
tasks_by_subject=РџУ™РЅ Р±РѕР№С‹РЅС€Р° С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂ
tasks_by_subject_text=ТљР°Р№ РїУ™РЅРґРµСЂРґС–ТЈ РєУ©Р±С–СЂРµРє РЅР°Р·Р°СЂ С‚Р°Р»Р°Рї РµС‚РµС‚С–РЅС–РЅ Р°РЅС‹Т›С‚Р°ТЈС‹Р·.
no_subject_data=Әзірге пәндер бойынша дерек жоқ.
tasks_by_priority=Р‘Р°СЃС‹РјРґС‹Т› Р±РѕР№С‹РЅС€Р° С‚Р°РїСЃС‹СЂРјР°Р»Р°СЂ
tasks_by_priority_text=Р–ТЇРєС‚РµРјРµТЈС–Р· РєУ©Р±С–РЅРµ С€Т±Т“С‹Р» РјР°, У™Р»РґРµ Т›Р°Р»С‹РїС‚С‹ РјР°, СЃРѕРЅС‹ С‚РµРєСЃРµСЂС–ТЈС–Р·.
no_priority_data=Әзірге басымдықтар бойынша дерек жоқ.
please_login_continue=Р–Р°Р»Т“Р°СЃС‚С‹СЂСѓ ТЇС€С–РЅ Р¶ТЇР№РµРіРµ РєС–СЂС–ТЈС–Р·.
full_name_required=РўРѕР»С‹Т› Р°С‚С‹-Р¶У©РЅС– РјС–РЅРґРµС‚С‚С–.
email_required=Р­Р»РµРєС‚СЂРѕРЅРґС‹Т› РїРѕС€С‚Р° РјС–РЅРґРµС‚С‚С–.
password_required=ТљТ±РїРёСЏСЃУ©Р· РјС–РЅРґРµС‚С‚С–.
password_min_length=ТљТ±РїРёСЏСЃУ©Р· РєРµРјС–РЅРґРµ 6 С‚Р°ТЈР±Р°РґР°РЅ С‚Т±СЂСѓС‹ РєРµСЂРµРє.
password_confirmation_mismatch=ТљТ±РїРёСЏСЃУ©Р·РґС– СЂР°СЃС‚Р°Сѓ СЃУ™Р№РєРµСЃ РєРµР»РјРµР№РґС–.
account_exists=Р‘Т±Р» СЌР»РµРєС‚СЂРѕРЅРґС‹Т› РїРѕС€С‚Р°РјРµРЅ Р°РєРєР°СѓРЅС‚ Р±Т±СЂС‹РЅРЅР°РЅ Р±Р°СЂ.
registration_successful=РўС–СЂРєРµР»Сѓ СЃУ™С‚С‚С– Р°СЏТ›С‚Р°Р»РґС‹. Р•РЅРґС– Р¶ТЇР№РµРіРµ РєС–СЂРµ Р°Р»Р°СЃС‹Р·.
invalid_email_or_password=Р­Р»РµРєС‚СЂРѕРЅРґС‹Т› РїРѕС€С‚Р° РЅРµРјРµСЃРµ Т›Т±РїРёСЏСЃУ©Р· Т›Р°С‚Рµ.
welcome_back_user=ТљР°Р№С‚Р° РєРµР»РіРµРЅС–ТЈС–Р·РіРµ Т›СѓР°РЅС‹С€С‚С‹РјС‹Р·, {name}!
logged_out=РЎС–Р· Р°РєРєР°СѓРЅС‚С‚Р°РЅ С€С‹Т›С‚С‹ТЈС‹Р·.
validation_required=В«{field}В» У©СЂС–СЃС– РјС–РЅРґРµС‚С‚С–.
deadline_format=Р”РµРґР»Р°Р№РЅ У©СЂС–СЃС– Р–Р–Р–Р–-РђРђ-РљРљ С„РѕСЂРјР°С‚С‹РЅРґР° Р±РѕР»СѓС‹ РєРµСЂРµРє.
task_not_found=РўР°РїСЃС‹СЂРјР° С‚Р°Р±С‹Р»РјР°РґС‹ РЅРµРјРµСЃРµ РѕТ“Р°РЅ Т›РѕР»Р¶РµС‚С–РјРґС–Р»С–Рє Р¶РѕТ›.
task_added_successfully=РўР°РїСЃС‹СЂРјР° СЃУ™С‚С‚С– Т›РѕСЃС‹Р»РґС‹.
task_updated_successfully=РўР°РїСЃС‹СЂРјР° СЃУ™С‚С‚С– Р¶Р°ТЈР°СЂС‚С‹Р»РґС‹.
task_deleted_successfully=РўР°РїСЃС‹СЂРјР° СЃУ™С‚С‚С– У©С€С–СЂС–Р»РґС–.
task_title_field=РўР°РїСЃС‹СЂРјР° Р°С‚Р°СѓС‹
subject_field=РџУ™РЅ
deadline_field=Р”РµРґР»Р°Р№РЅ
priority_field=Р‘Р°СЃС‹РјРґС‹Т›
status_field=РњУ™СЂС‚РµР±Рµ
status_pending=РљТЇС‚С–Р»СѓРґРµ
status_in_progress=РћСЂС‹РЅРґР°Р»С‹Рї Р¶Р°С‚С‹СЂ
status_completed=РђСЏТ›С‚Р°Р»Т“Р°РЅ
priority_high=Р–РѕТ“Р°СЂС‹
priority_medium=РћСЂС‚Р°С€Р°
priority_low=РўУ©РјРµРЅ
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
