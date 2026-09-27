"""Сборка слайдов презентации BinSense.

Текст слайдов и тезисы докладчика лежат здесь, а чертежи подтягиваются из
репозитория: правится чертёж — пересобираются слайды, и картинка на экране
не расходится с тем, что в проекте.

    python make_deck.py      # кладёт HTML слайдов и оглавление в deck/

Разметка слайдов — подмножество HTML с встроенными стилями на холсте
1920 x 1080. Тезисы каждого слайда лежат в его теге <aside>.
"""

import io
import json
import os
import re

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "..")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deck")
SLIDES = os.path.join(ROOT, "project", "slides")

DISPLAY = "'Rubik', Verdana, sans-serif"
TEXT = "'IBM Plex Sans', Arial, sans-serif"
BG = "#f6f8f5"
BG_ALT = "#e9efe9"
DARK = "#10231c"
CARD = "#ffffff"
CARD_DARK = "#1b3a2e"
INK = "#10231c"
BODY = "#4d5f56"
ON_DARK = "#eaf2ec"
BODY_DARK = "#a7bfb2"
GREEN = "#2f9e68"
GREEN_LIGHT = "#5fc08c"
AMBER = "#9c6410"
RED = "#b3402f"
LINE = "#d6ded6"

SECTION = (f"background:{BG}; color:{INK}; font-family:{TEXT}; "
           "padding:128px 128px 160px; display:flex; flex-direction:column; "
           "gap:44px")
SECTION_ALT = SECTION.replace(BG, BG_ALT)
H2 = (f"font-family:{DISPLAY}; font-size:64px; font-weight:600; "
      "line-height:1.1")
LEAD = f"font-size:30px; line-height:1.4; color:{BODY}"


def footer(number, note=""):
    left = note or "BinSense"
    return (
        f'<p style="position:absolute; left:128px; bottom:64px; width:1400px; '
        f'font-size:24px; color:#5f7169">{left}</p>'
        f'<p style="position:absolute; right:128px; bottom:64px; width:120px; '
        f'font-size:24px; color:#5f7169; text-align:right">{number}</p>')


def card(title, body, accent=GREEN, dark=False, extra=""):
    bg = CARD_DARK if dark else CARD
    border = "#2c5244" if dark else LINE
    tcol = ON_DARK if dark else INK
    bcol = BODY_DARK if dark else BODY
    return (
        f'<div style="flex:1; display:flex; flex-direction:column; gap:14px; '
        f'background:{bg}; padding:36px; border:1px solid {border}; '
        f'border-radius:18px; border-top:4px solid {accent}">'
        f'<h3 style="font-family:{DISPLAY}; font-size:32px; font-weight:600; '
        f'color:{tcol}; line-height:1.2">{title}</h3>'
        f'<p style="font-size:24px; line-height:1.45; color:{bcol}">{body}</p>'
        f'{extra}</div>')


def stat(value, label, dark=True):
    tcol = GREEN_LIGHT if dark else GREEN
    lcol = BODY_DARK if dark else BODY
    return (
        f'<div style="flex:1; display:flex; flex-direction:column; gap:8px">'
        f'<p style="font-family:{DISPLAY}; font-size:60px; font-weight:600; '
        f'color:{tcol}; line-height:1.05">{value}</p>'
        f'<p style="font-size:24px; line-height:1.35; color:{lcol}">'
        f'{label}</p></div>')


def table(head, rows, widths, size=26, first_bold=False):
    cells = "".join(
        f'<th style="width:{w}%; text-align:left; padding:14px 18px; '
        f'color:{INK}">{h}</th>' for h, w in zip(head, widths))
    out = [f'<table style="font-family:{TEXT}; font-size:{size}px; '
           f'color:{BODY}">', f"<tr>{cells}</tr>"]
    for row in rows:
        tds = []
        for i, value in enumerate(row):
            colour = INK if (first_bold and i == 0) else BODY
            tds.append(f'<td style="padding:14px 18px; color:{colour}">'
                       f"{value}</td>")
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</table>")
    return "".join(out)


def embed_svg(path, width, height, label):
    """Встраивание готового чертежа: он лежит в репозитории и не копируется."""
    raw = io.open(os.path.join(REPO, path), encoding="utf-8").read()
    raw = raw.replace("\n", "")
    head = re.match(r"<svg[^>]*>", raw).group(0)
    view = re.search(r'viewBox="([^"]*)"', head).group(1)
    font = re.search(r'font-family="([^"]*)"', head)
    attrs = f' viewBox="{view}"'
    if font:
        attrs += f' font-family="{font.group(1)}"'
    body = raw[len(head):]
    vw, vh = view.split()[2], view.split()[3]
    return (f'<svg aria-label="{label}" width="{vw}" height="{vh}"'
            f'{attrs} style="width:{width}px; height:{height}px; '
            f'border:1px solid {LINE}; border-radius:12px; '
            f'background:#ffffff">{body}')


def arch_svg():
    """Диаграмма архитектуры: рисуется здесь, а не берётся из репозитория."""
    w, h = 1580, 520
    box_style = ('fill="#ffffff" stroke="#c8d4cb" stroke-width="2" rx="14"')
    out = [f'<svg aria-label="Схема обмена данными между частями системы" '
           f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'font-family="{TEXT}" style="width:{w}px; height:{h}px">']

    def node(x, y, bw, bh, title, sub, colour=GREEN, fill="#ffffff"):
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" '
                   f'fill="{fill}" stroke="{colour}" stroke-width="2.5" '
                   f'rx="14"/>')
        out.append(f'<text x="{x + bw / 2}" y="{y + 42}" font-size="27" '
                   f'font-weight="600" fill="{INK}" text-anchor="middle">'
                   f'{title}</text>')
        for i, line in enumerate(sub):
            out.append(f'<text x="{x + bw / 2}" y="{y + 76 + i * 28}" '
                       f'font-size="21" fill="{BODY}" text-anchor="middle">'
                       f'{line}</text>')

    def arrow(x1, y1, x2, y2, label, dash=False):
        d = ' stroke-dasharray="7 6"' if dash else ""
        out.append(f'<path d="M {x1} {y1} L {x2} {y2}" stroke="#8fa598" '
                   f'stroke-width="2.5" fill="none"{d}/>')
        ang = 0 if y1 == y2 else (90 if y2 > y1 else -90)
        if ang == 0:
            tip = f"M {x2} {y2} l -14 -7 l 0 14 Z"
            tx, ty = (x1 + x2) / 2, y1 - 14
        else:
            tip = (f"M {x2} {y2} l -7 -14 l 14 0 Z" if y2 > y1
                   else f"M {x2} {y2} l -7 14 l 14 0 Z")
            tx, ty = x1 + 12, (y1 + y2) / 2 + 6
        out.append(f'<path d="{tip}" fill="#8fa598"/>')
        anchor = "middle" if ang == 0 else "start"
        out.append(f'<text x="{tx}" y="{ty}" font-size="21" fill="{AMBER}" '
                   f'text-anchor="{anchor}">{label}</text>')

    node(0, 176, 250, 150, "Устройство", ["ESP32 + УЗ-датчик", "18650, глубокий сон"],
         GREEN, "#eef7f1")
    arrow(250, 251, 356, 251, "MQTT, QoS 1")
    node(356, 176, 210, 150, "Mosquitto", ["права на каждое", "устройство"])
    arrow(566, 251, 672, 251, "подписка")
    node(672, 176, 220, 150, "Ingestor", ["дедупликация,", "правила событий"])
    arrow(892, 251, 998, 251, "SQL")
    node(998, 176, 230, 150, "PostgreSQL", ["история, события,", "пользователи"])
    arrow(1113, 176, 1113, 96, "LISTEN/NOTIFY")
    node(998, 0, 230, 96, "FastAPI", ["REST + WebSocket"])
    arrow(1228, 48, 1334, 48, "HTTPS")
    node(1334, 0, 246, 96, "Веб-приложение", ["карта, история"])
    arrow(782, 326, 782, 406, "события")
    node(672, 406, 230, 114, "Telegram-бот", ["уведомления,", "подтверждения"])
    arrow(1113, 326, 1113, 406, "метрики", dash=True)
    node(998, 406, 230, 114, "Grafana", ["мониторинг", "для разработчика"], AMBER)
    out.append("</svg>")
    return "".join(out)


def flow_svg():
    """Путь измерения: от пробуждения до карты."""
    steps = [("Просыпается", "таймер\nили кнопка"),
             ("Меряет", "медиана 7 замеров,\nскачок — повтор"),
             ("Решает", "delta_pct или\nheartbeat_s"),
             ("Отправляет", "MQTT QoS 1,\nждёт PUBACK"),
             ("Засыпает", "20–150 мкА")]
    w, h = 1580, 210
    out = [f'<svg aria-label="Цикл работы устройства из пяти шагов" '
           f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'font-family="{TEXT}" style="width:{w}px; height:{h}px">']
    bw, gap = 268, 60
    for i, (title, sub) in enumerate(steps):
        x = i * (bw + gap)
        out.append(f'<rect x="{x}" y="10" width="{bw}" height="170" '
                   f'fill="#ffffff" stroke="#c8d4cb" stroke-width="2" rx="16"/>')
        out.append(f'<circle cx="{x + 40}" cy="52" r="22" fill="{GREEN}"/>')
        out.append(f'<text x="{x + 40}" y="61" font-size="24" fill="#ffffff" '
                   f'font-weight="600" text-anchor="middle">{i + 1}</text>')
        out.append(f'<text x="{x + 76}" y="61" font-size="28" '
                   f'font-weight="600" fill="{INK}">{title}</text>')
        for j, line in enumerate(sub.split("\n")):
            out.append(f'<text x="{x + 28}" y="{112 + j * 30}" font-size="22" '
                       f'fill="{BODY}">{line}</text>')
        if i < len(steps) - 1:
            ax = x + bw + 12
            out.append(f'<path d="M {ax} 95 L {ax + 34} 95" stroke="#8fa598" '
                       f'stroke-width="2.5"/>')
            out.append(f'<path d="M {ax + 36} 95 l -12 -6 l 0 12 Z" '
                       f'fill="#8fa598"/>')
    out.append("</svg>")
    return "".join(out)


def stand_svg():
    """Стенд для защиты: плата, ноутбук с сервером и браузер."""
    w, h = 1580, 230
    out = [f'<svg aria-label="Стенд: ESP32 по Wi-Fi подключается к ноутбуку, '
           f'на котором работают сервер и браузер" '
           f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'font-family="{TEXT}" style="width:{w}px; height:{h}px">']

    def node(x, y, bw, bh, title, sub, colour=GREEN, fill="#ffffff"):
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" '
                   f'fill="{fill}" stroke="{colour}" stroke-width="2.5" '
                   f'rx="14"/>')
        out.append(f'<text x="{x + bw / 2}" y="{y + 42}" font-size="27" '
                   f'font-weight="600" fill="{INK}" text-anchor="middle">'
                   f'{title}</text>')
        for i, line in enumerate(sub):
            out.append(f'<text x="{x + bw / 2}" y="{y + 76 + i * 28}" '
                       f'font-size="21" fill="{BODY}" text-anchor="middle">'
                       f'{line}</text>')

    def arrow(x1, x2, y, label):
        out.append(f'<path d="M {x1} {y} L {x2} {y}" stroke="#8fa598" '
                   f'stroke-width="2.5" fill="none"/>')
        out.append(f'<path d="M {x2} {y} l -14 -7 l 0 14 Z" fill="#8fa598"/>')
        out.append(f'<text x="{(x1 + x2) / 2}" y="{y - 14}" font-size="21" '
                   f'fill="{AMBER}" text-anchor="middle">{label}</text>')

    node(0, 55, 270, 150, "ESP32", ["датчик и прошивка", "Wi-Fi 2.4 ГГц"],
         GREEN, "#eef7f1")
    arrow(270, 450, 130, "Wi-Fi")
    # Ноутбук: рамка, внутри хот-спот, сервер в Docker и браузер
    out.append(f'<rect x="420" y="0" width="1160" height="230" fill="#ffffff" '
               f'stroke="{INK}" stroke-width="2.5" rx="18"/>')
    out.append(f'<text x="444" y="36" font-size="24" font-weight="600" '
               f'fill="{INK}">Ноутбук · 192.168.137.1</text>')
    node(450, 60, 280, 140, "Хот-спот", ["Windows, 2.4 ГГц", "адрес не меняется"])
    arrow(730, 870, 130, "MQTT :1883")
    node(870, 60, 300, 140, "docker compose", ["mqtt, api, ingestor,", "db, web, grafana"])
    arrow(1170, 1290, 130, "HTTPS")
    node(1290, 60, 260, 140, "Браузер", ["https://localhost", "карта, привязка"], AMBER)
    out.append("</svg>")
    return "".join(out)


def section(sid, style, inner, notes, transition="fade"):
    aside = f"<aside>{notes}</aside>" if notes else ""
    return (f'<section id="{sid}" data-transition="{transition}" '
            f'style="{style}">{inner}{aside}</section>')


slides = {}

# --- 1. Обложка ----------------------------------------------------------
slides["cover"] = section(
    "cover",
    f"background:{DARK}; color:{ON_DARK}; font-family:{TEXT}; padding:128px; "
    "display:flex; flex-direction:column; justify-content:space-between",
    f'<p style="font-family:{DISPLAY}; font-size:28px; font-weight:500; '
    f'color:{GREEN_LIGHT}; letter-spacing:3px; text-transform:uppercase">'
    f'Курсовой проект · интернет вещей</p>'
    f'<div style="display:flex; flex-direction:column; gap:28px">'
    f'<h1 style="font-family:{DISPLAY}; font-size:150px; font-weight:600; '
    f'line-height:1.0">BinSense</h1>'
    f'<p style="font-size:46px; line-height:1.25; color:{BODY_DARK}; '
    f'width:1180px">Мусорные контейнеры сами сообщают, когда их пора '
    f'вывозить</p></div>'
    f'<div style="display:flex; gap:48px">'
    + stat("≈ 6 месяцев", "работы от одного аккумулятора 18650")
    + stat("107 тестов", "49 на сервере, 58 на логике прошивки")
    + stat("3 человека", "электроника, сервер, интерфейс и корпус")
    + "</div>",
    "Здравствуйте. Проект BinSense: система мониторинга заполненности "
    "мусорных контейнеров. Датчик на ESP32 живёт под крышкой контейнера и "
    "работает от одного аккумулятора около полугода.")

# --- 2. Проблема ---------------------------------------------------------
slides["problem"] = section(
    "problem", SECTION,
    f'<h2 style="{H2}">Вывоз по расписанию промахивается в обе стороны</h2>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Пустые рейсы", "Мусоровоз объезжает контейнеры, до которых "
           "ещё неделя. Топливо и время водителя уходят впустую.", AMBER)
    + card("Переполнение", "Контейнер во дворе с высокой проходимостью "
           "переполняется за два дня, а по графику его вывезут в пятницу.",
           RED)
    + card("Нет данных", "Диспетчер не знает, что происходит во дворах, "
           "пока не позвонят жильцы. Планировать не на чем.", GREEN)
    + "</div>" + footer("2", "Проблема"),
    "Расписание не знает, что происходит во дворе. Отсюда две ошибки сразу: "
    "лишние рейсы и переполненные контейнеры.")

# --- 3. Что делает система ----------------------------------------------
slides["idea"] = section(
    "idea", SECTION,
    f'<h2 style="{H2}">Устройство измеряет уровень и молчит, пока нечего '
    f'сказать</h2>'
    f'<p style="{LEAD}; width:1400px">Ультразвуковой датчик под крышкой '
    f'контейнера меряет расстояние до мусора. Данные уходят по MQTT только '
    f'когда заполненность изменилась заметно — это главная экономия '
    f'батареи.</p>'
    + flow_svg()
    + f'<p style="font-size:24px; color:{BODY}">Интервал опроса и порог '
      f'изменения задаются с сервера и меняются без перепрошивки.</p>'
    + footer("3", "Решение"),
    "Цикл устройства: проснуться, померить, решить, нужно ли отправлять, "
    "отправить и уснуть. Отправка по изменению, а не по таймеру, — главное "
    "решение по энергопотреблению.")

# --- 4. Архитектура ------------------------------------------------------
slides["arch"] = section(
    "arch", SECTION_ALT,
    f'<h2 style="{H2}">Архитектура: пять сервисов и одна база</h2>'
    + arch_svg()
    + f'<p style="font-size:24px; color:{BODY}">Обновления в реальном '
      f'времени сделаны без Redis: ingestor делает pg_notify, API слушает '
      f'канал и рассылает по WebSocket.</p>'
    + footer("4", "Архитектура"),
    "Брокер, приёмник данных, база, API, бот и Grafana. Всё поднимается одной "
    "командой docker compose up.")

# --- 5. Устройство -------------------------------------------------------
slides["device"] = section(
    "device", SECTION,
    f'<h2 style="{H2}">Что внутри устройства</h2>'
    f'<div style="display:flex; gap:44px; flex:1">'
    f'<div style="flex:1">'
    + table(["Узел", "Что стоит", "Почему так"],
            [["Мозг", "LOLIN D32", "малый ток сна, зарядка и делитель на плате"],
             ["Датчик", "A02YYUW, UART", "влагозащищённый, не боится конденсата"],
             ["Питание", "18650 + ключ", "датчик выключается на время сна"],
             ["Замер", "медиана из 7", "скачок уровня перемеряется через минуту"],
             ["Монтаж", "кнопка и RGB", "калибровка и индикация на месте"],
             ["Связь", "Wi-Fi, MQTT", "QoS 1: устройство знает, что дошло"]],
            [16, 26, 58], 25, first_bold=True)
    + "</div>"
    f'<div style="width:520px; display:flex; flex-direction:column; gap:24px">'
    + card("Ток во сне", "20–150 мкА с выключенным датчиком. На обычном "
           "DevKit было бы 5–10 мА — та же батарея села бы за две недели.",
           GREEN)
    + card("Цикл отправки", "Пробуждение на 3 секунды при 120 мА — около "
           "0.1 мА·ч. При интервале 15 минут это примерно 10 мА·ч в сутки.",
           GREEN)
    + "</div></div>" + footer("5", "Устройство"),
    "Ключевая деталь — плата с малым током сна и ключ питания датчика. "
    "Без ключа датчик ест миллиамперы круглосуточно.")

# --- 6. Корпус: компоновка ----------------------------------------------
slides["case"] = section(
    "case", SECTION_ALT,
    f'<h2 style="{H2}">Корпус описан кодом, а не нарисован мышью</h2>'
    f'<div style="display:flex; gap:44px; align-items:center; flex:1">'
    + embed_svg("cad/render/layout.svg", 580, 590,
                "Чертёж расположения элементов внутри корпуса")
    + f'<div style="flex:1; display:flex; flex-direction:column; gap:22px">'
    f'<p style="{LEAD}">Все размеры лежат в одном файле параметров. '
    f'<b>python build.py</b> собирает восемь STL и четыре чертежа, включая '
    f'этот. Чертёж не может разойтись с моделью: он строится из тех же '
    f'чисел.</p>'
    f'<p style="{LEAD}">Перед выгрузкой каждая деталь проверяется на '
    f'замкнутость и целостность — деталь, распавшаяся на два куска, до '
    f'принтера не доедет.</p>'
    f'<p style="font-size:26px; color:{AMBER}; line-height:1.4">Пунктиром '
    f'показан габарит колодок Dupont: провод с колодкой занимает больше '
    f'места, чем кажется, и это частая причина переделки корпуса.</p>'
    f'</div></div>' + footer("6", "Корпус"),
    "Восемь деталей: основание, крышка, уплотнитель, две вставки под датчик, "
    "кронштейн, толкатель кнопки и световод.")

# --- 7. Решения в корпусе ------------------------------------------------
slides["case_why"] = section(
    "case_why", SECTION,
    f'<h2 style="{H2}">Три решения, которые видно только в разрезе</h2>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Винты снаружи уплотнителя",
           "Шесть М3 идут по фланцу за пазом. Поставь винты внутри контура — "
           "вода пойдёт внутрь по резьбе, и уплотнитель потеряет смысл.")
    + card("Паз — в основании, не в крышке",
           "Так обе половины печатаются без поддержек: у основания паз "
           "открыт вверх, у крышки низ ровный. Шнур при сборке лежит сам.")
    + card("Кнопка — в торцевой стенке",
           "Крышка прижата кронштейном к крышке контейнера. Сверху до "
           "кнопки просто не дотянуться.")
    + "</div>" + footer("7", "Корпус"),
    "Эти три вещи выяснились не сразу: первая версия была с винтами внутри "
    "контура и пазом в крышке.")

# --- 8. Принципиальная схема --------------------------------------------
slides["schematic"] = section(
    "schematic", SECTION_ALT,
    f'<h2 style="font-family:{DISPLAY}; font-size:48px; font-weight:600; '
    f'line-height:1.1">Принципиальная схема со всей обвязкой</h2>'
    f'<div style="display:flex; gap:36px; align-items:start; flex:1">'
    + embed_svg("hardware/schematic/schematic.svg", 1000, 682,
                "Принципиальная электрическая схема устройства")
    + f'<div style="width:596px; display:flex; flex-direction:column; gap:20px">'
    f'<p style="font-size:26px; line-height:1.4; color:{BODY}">Схема '
    f'генерируется из той же таблицы распиновки, что и документация: '
    f'править нужно один список, а не три картинки.</p>'
    f'<p style="font-size:26px; line-height:1.4; color:{BODY}">Блоки '
    f'соединены именами цепей, а не проводами через весь лист — так схема '
    f'читается без линейки.</p>'
    f'<p style="font-size:26px; line-height:1.4; color:{BODY}">Второй лист — '
    f'вариант прототипа на HC-SR04 с делителем Echo.</p>'
    f'</div></div>' + footer("8", "Схемотехника"),
    "Вся обвязка на месте: подтяжки, делители, ключи, фильтрующие "
    "конденсаторы. Делитель батареи нарисован пунктиром — он уже распаян "
    "на плате.")

# --- 9. Решения в схеме --------------------------------------------------
slides["sch_why"] = section(
    "sch_why", SECTION,
    f'<h2 style="{H2}">Три решения, за которые отвечает схема</h2>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Ключ питания датчика",
           "Датчик в покое ест несколько миллиампер — в тысячи раз больше, "
           "чем ESP32 во сне. Резистор 10 кОм держит затвор у питания, пока "
           "выводы спящего ESP32 в высокоимпедансном состоянии.")
    + card("Кнопка на RTC-выводе",
           "GPIO32 умеет будить ESP32 из глубокого сна (EXT0). Подтяжка "
           "10 кОм и 100 нФ убирают дребезг: одно нажатие — одно "
           "пробуждение.")
    + card("Батарея на GPIO35",
           "Напряжение меряется только выводами ADC1. ADC2 не работает, "
           "когда включён Wi-Fi, — на этом легко потерять день.")
    + "</div>" + footer("9", "Схемотехника"),
    "Ключ питания превращает две недели работы в полгода. Два других "
    "решения избавляют от ошибок, которые долго ищут.")

# --- 10. Монтажная схема -------------------------------------------------
slides["wiring"] = section(
    "wiring", SECTION_ALT,
    f'<h2 style="{H2}">Монтажная схема: что куда паяется</h2>'
    f'<div style="display:flex; gap:36px; align-items:center; flex:1">'
    + embed_svg("hardware/schematic/wiring.svg", 940, 627,
                "Монтажная схема шилда и проводов к плате")
    + f'<div style="flex:1; display:flex; flex-direction:column; gap:22px">'
    f'<p style="{LEAD}">Обвязка собрана на макетной плате 40 × 60 мм, '
    f'которая надевается на гребёнки ESP32. Плату можно снять и заменить, '
    f'не распаивая обвязку.</p>'
    f'<p style="font-size:26px; color:{AMBER}; line-height:1.4">Ключ Q1 и '
    f'конденсатор C1 стоят рядом: длинные дорожки по питанию датчика дают '
    f'просадку в момент импульса.</p>'
    f'<p style="font-size:26px; color:{BODY}; line-height:1.4">Провода '
    f'датчика идут в клеммник, а не в разъём Dupont: в контейнере разъём '
    f'разбалтывается от вибрации при выгрузке.</p>'
    f'</div></div>' + footer("10", "Сборка"),
    "Монтажная схема нужна не меньше принципиальной: по ней собирают, а не "
    "по принципиальной.")

# --- 11. Энергопотребление ----------------------------------------------
slides["power"] = section(
    "power", SECTION,
    f'<h2 style="{H2}">Откуда берётся полгода работы</h2>'
    f'<div style="display:flex; gap:44px; flex:1">'
    f'<div style="flex:1">'
    + table(["Режим", "LOLIN D32", "ESP32 DevKit v1"],
            [["Глубокий сон, датчик выключен", "20–150 мкА", "5–10 мА"],
             ["Измерение, датчик включён", "40–60 мА", "40–60 мА"],
             ["Передача по Wi-Fi", "120–180 мА", "120–180 мА"]],
            [46, 27, 27], 26, first_bold=True)
    + f'<p style="font-size:26px; line-height:1.45; color:{BODY}; '
      f'padding:24px 0 0">Цикл: пробуждение на 3 секунды при 120 мА — около '
      f'0.1 мА·ч. При интервале 15 минут выходит примерно 10 мА·ч в сутки. '
      f'Аккумулятор 2500 мА·ч с учётом саморазряда даёт около полугода.</p>'
    f'</div>'
    f'<div style="width:520px; display:flex; flex-direction:column; gap:24px">'
    + card("Выбор платы решает всё", "С обычным DevKit тот же аккумулятор "
           "сядет за две–три недели. Разница — только в токе сна.", RED)
    + card("Отправка по изменению", "Порог delta_pct и период heartbeat_s "
           "задаются с сервера: можно подстроить под конкретный двор, не "
           "перепрошивая устройство.", GREEN)
    + "</div></div>" + footer("11", "Энергопотребление"),
    "Цифры замерены мультиметром в разрыве провода от аккумулятора.")

# --- 12. Протокол --------------------------------------------------------
slides["protocol"] = section(
    "protocol", SECTION_ALT,
    f'<h2 style="{H2}">Протокол рассчитан на спящее устройство</h2>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Настройки — retained-сообщение",
           "Команду в произвольный момент спящее устройство не примет. "
           "Оно просыпается, подписывается и получает последнюю версию "
           "настроек. Версия возвращается в телеметрии — сервер видит, что "
           "настройки применены.")
    + card("QoS 1 и дедупликация",
           "Уникальный индекс по устройству, идентификатору включения и "
           "номеру пакета. Разрывы номеров дают метрику потерь, а "
           "перезагрузка не путается с потерей связи.")
    + card("Last Will не используется",
           "Для спящего устройства брокер объявлял бы офлайн после каждого "
           "засыпания. Статус «нет связи» считает сервер по времени "
           "последнего пакета и периоду опроса.", AMBER)
    + "</div>"
    + f'<p style="font-size:24px; color:{BODY}">Протокол описан формально: '
      f'MQTT — в AsyncAPI, REST — в OpenAPI, живая версия на /api/docs.</p>'
    + footer("12", "Протокол"),
    "Три решения, которые отличают протокол для спящего устройства от "
    "обычного MQTT-клиента.")

# --- 13. Приложение ------------------------------------------------------
slides["app"] = section(
    "app", SECTION,
    f'<h2 style="{H2}">Приложение диспетчера</h2>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Карта", "Метки меняют цвет по заполненности. Обновления "
           "приходят по WebSocket — страницу перезагружать не нужно.")
    + card("Карточка контейнера", "Графики за сутки, неделю и месяц, "
           "история событий, прогноз заполнения и кнопка «вывезли».")
    + card("Маршрут", "Контейнеры выше порога собираются в маршрут и "
           "открываются в картах одной ссылкой.")
    + "</div>"
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Привязка по коду", "Код приходит ссылкой из скрипта "
           "подготовки или вводится вручную.", AMBER)
    + card("Роли", "Монтажник, диспетчер, водитель и администратор видят "
           "разное и получают разные уведомления.", AMBER)
    + card("Журнал действий", "Все действия пользователей пишутся в "
           "audit_log: кто отвязал устройство и когда.", AMBER)
    + "</div>" + footer("13", "Интерфейс"),
    "React, Leaflet и Chart.js. Состояние приложения — в одном месте, "
    "сетевые вызовы — через один модуль.")

# --- 14. Telegram --------------------------------------------------------
slides["bot"] = section(
    "bot", SECTION_ALT,
    f'<h2 style="{H2}">Обратная связь, когда диспетчер не за компьютером</h2>'
    f'<p style="{LEAD}; width:1400px">Телеграм-бот отправляет уведомление в '
    f'момент события и принимает подтверждение одной кнопкой. Это закрывает '
    f'требование об обратной связи, когда пользователь не рядом с '
    f'устройством.</p>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Уведомления", "Заполнен на 80 %, переполнен, нет связи, "
           "разряжена батарея, сбой датчика. Каждому событию — свой "
           "получатель.")
    + card("Кнопка «Принято»", "Подтверждение пишется в базу: видно, кто "
           "и когда принял событие в работу.")
    + card("Команды", "Статус контейнера, список переполненных, последние "
           "события и маршрут вывоза ссылкой на карты.")
    + "</div>" + footer("14", "Уведомления"),
    "Бот сделан на aiogram. Правила, по которым рождаются события, — "
    "чистые функции, покрытые тестами.")

# --- 15. Plug and Play ---------------------------------------------------
slides["plugplay"] = section(
    "plugplay", SECTION,
    f'<h2 style="{H2}">Первое включение без компьютера</h2>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("1 · Wi-Fi без прошивки", "Устройство поднимает точку доступа и "
           "показывает портал. Монтажник вводит сеть с телефона — паять и "
           "прошивать ничего не нужно.")
    + card("2 · Привязка по коду", "Скрипт подготовки выдаёт ссылку с "
           "кодом. Код хранится хешем, перебор блокируется. Устройство "
           "появляется на карте сразу после привязки.")
    + card("3 · Калибровка кнопкой", "Одно нажатие на пустом контейнере "
           "задаёт нулевой уровень. Светодиод и зуммер подтверждают, что "
           "замер принят.")
    + "</div>"
    + f'<p style="font-size:24px; color:{BODY}">«Заводская» подготовка '
      f'устройств делается скриптом: он прошивает, заводит учётную запись в '
      f'брокере и выдаёт ссылку для привязки.</p>'
    + footer("15", "Plug and Play"),
    "Сценарий проверен на стенде целиком: от подготовки устройства до "
    "первой телеметрии на карте.")

# --- 16. Стенд на ноутбуке -----------------------------------------------
slides["stand"] = section(
    "stand", SECTION_ALT,
    f'<h2 style="{H2}">Стенд для защиты: всё на одном ноутбуке</h2>'
    + stand_svg()
    + f'<div style="display:flex; gap:32px; flex:1">'
    + card("Сеть", "Мобильный хот-спот Windows на 2.4 ГГц. Адрес ноутбука в "
           "нём по умолчанию 192.168.137.1 — его и получает устройство как "
           "адрес брокера.")
    + card("Сервер", "init-env.sh и docker compose up — тот же набор "
           "сервисов, что на VPS. Ни домен, ни внешний сервер не нужны.")
    + card("Устройство", "provision.py прошивает плату по USB, записывает "
           "адрес брокера и выдаёт ссылку для привязки.")
    + "</div>"
    + f'<p style="font-size:24px; color:{AMBER}">Без интернета не будет только '
      f'плиток карты и Telegram — данные, события и привязка работают.</p>'
    + footer("16", "Демонстрация"),
    "На защите показываем систему целиком на одном ноутбуке: он раздаёт "
    "Wi-Fi плате и держит весь сервер в Docker. Пошаговая инструкция — "
    "docs/LOCAL_TEST.md, включая правило брандмауэра для порта 1883.")

# --- 17. Мониторинг ------------------------------------------------------
slides["monitoring"] = section(
    "monitoring", SECTION,
    f'<h2 style="{H2}">Что видит разработчик, а не диспетчер</h2>'
    f'<div style="display:flex; gap:44px; flex:1">'
    f'<div style="flex:1">'
    + table(["Панель", "Зачем"],
            [["Доступность устройств", "кто перестал выходить на связь"],
             ["Потери сообщений", "разрывы номеров пакетов"],
             ["Задержка доставки", "сколько шло от датчика до базы"],
             ["Время бодрствования", "растёт — батарея сядет раньше срока"],
             ["Уровень сигнала и заряд", "где Wi-Fi на пределе"],
             ["Причины перезагрузок", "паника прошивки видна сразу"]],
            [40, 60], 26, first_bold=True)
    + "</div>"
    f'<div style="width:520px; display:flex; flex-direction:column; gap:24px">'
    + card("Дашборд генерируется", "JSON дашборда собирает скрипт: руками "
           "его не правят, иначе изменения теряются при следующем "
           "обновлении.", AMBER)
    + card("Эмулятор", "Двенадцать виртуальных контейнеров поднимаются "
           "одной командой — систему можно показать без единого железного "
           "устройства.", GREEN)
    + "</div></div>" + footer("17", "Мониторинг"),
    "Это необязательный пункт задания, но без него не видно, что устройство "
    "начало просыпаться чаще, чем должно.")

# --- 18. Путь проб -------------------------------------------------------
slides["trials"] = section(
    "trials", SECTION_ALT,
    f'<h2 style="{H2}">Путь проб: что выкинули и почему</h2>'
    + table(["Было", "Стало", "Почему"],
            [["HC-SR04 на макете", "A02YYUW по UART",
              "влага, 5 В и ширина луча; UART вместо длительности импульса"],
             ["Плата DevKit v1", "LOLIN D32",
              "ток сна 5–10 мА против 20–150 мкА: разница в разы по сроку"],
             ["PubSubClient", "arduino-mqtt",
              "нужен QoS 1: устройство должно знать, что данные дошли"],
             ["Last Will", "расчёт статуса на сервере",
              "для спящего устройства брокер объявлял бы офлайн каждый час"],
             ["Отправка каждые 15 минут", "отправка по изменению",
              "главная экономия батареи"],
             ["Замер при открытой крышке", "повтор при скачке уровня",
              "рука в луче давала ложные 100 %, а геркона в комплекте нет"],
             ["Наклейка с QR-кодом", "ссылка с кодом привязки",
              "печатать наклейки негде, а ссылка сразу открывает форму"],
             ["ArduinoJson", "свой разбор JSON",
              "меньше памяти, а логика тестируется на обычном компьютере"],
             ["Винты внутри уплотнителя", "винты по фланцу снаружи",
              "вода шла внутрь по резьбе"]],
            [23, 25, 52], 24, first_bold=True)
    + footer("18", "Пробы и ошибки"),
    "Почти каждая строка здесь — это день работы. Показываю их специально: "
    "конечная конструкция без них выглядит как удача.")

# --- 19. Состояние -------------------------------------------------------
slides["status"] = section(
    "status", SECTION,
    f'<h2 style="{H2}">Что работает, а что ещё нет</h2>'
    f'<div style="display:flex; gap:36px; flex:1">'
    f'<div style="flex:1; display:flex; flex-direction:column; gap:18px; '
    f'background:{CARD}; padding:40px; border:1px solid {LINE}; '
    f'border-radius:18px; border-top:4px solid {GREEN}">'
    f'<h3 style="font-family:{DISPLAY}; font-size:34px; font-weight:600">'
    f'Проверено на стенде</h3>'
    f'<ul style="font-size:26px; line-height:1.5; color:{BODY}">'
    f'<li>подготовка устройства, привязка по коду, калибровка</li>'
    f'<li>телеметрия, события, уведомления, подтверждение</li>'
    f'<li>история, прогноз, маршрут, метрики</li>'
    f'<li>49 тестов сервера и 58 проверок логики прошивки</li>'
    f'<li>сборка обоих вариантов прошивки и фронтенда</li></ul></div>'
    f'<div style="flex:1; display:flex; flex-direction:column; gap:18px; '
    f'background:{CARD}; padding:40px; border:1px solid {LINE}; '
    f'border-radius:18px; border-top:4px solid {AMBER}">'
    f'<h3 style="font-family:{DISPLAY}; font-size:34px; font-weight:600">'
    f'Ещё не проверено вживую</h3>'
    f'<ul style="font-size:26px; line-height:1.5; color:{BODY}">'
    f'<li>сборка docker-образов: в песочнице был закрыт реестр</li>'
    f'<li>реальный ESP32 на стенде «ноутбук + Wi-Fi»</li>'
    f'<li>реальный Telegram Bot API — использовалась заглушка</li>'
    f'<li>печать корпуса и посадка вставки датчика</li>'
    f'<li>фотографии и видео собранного устройства</li></ul></div>'
    f'</div>' + footer("19", "Состояние"),
    "Честно разделяю: что прогнано на стенде и что осталось. Корпус "
    "смоделирован и проверен геометрически, но ещё не напечатан.")

# --- 20. Команда ---------------------------------------------------------
slides["team"] = section(
    "team", SECTION_ALT,
    f'<h2 style="{H2}">Кто что делал и что дальше</h2>'
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Электроника и прошивка", "Схемы, пайка, прошивка, "
           "энергопотребление, заводская подготовка устройств.")
    + card("Сервер", "Брокер, API, база, правила уведомлений, бот, "
           "развёртывание, эмулятор и мониторинг.")
    + card("Дизайн и интерфейс", "Корпус и CAD, веб-приложение, карта, "
           "фотографии, видео и эта презентация.")
    + "</div>"
    f'<div style="display:flex; gap:32px; flex:1">'
    + card("Дальше: печать", "Напечатать тестовую пластину, уточнить "
           "посадку датчика, затем корпус целиком.", AMBER)
    + card("Дальше: съёмка", "Тринадцать кадров и видео на две с половиной "
           "минуты — сценарий готов, нужны собранное устройство и "
           "контейнер.", AMBER)
    + card("Дальше: поле", "Поставить два устройства на реальные "
           "контейнеры и прожить месяц на батарее.", AMBER)
    + "</div>" + footer("20", "Команда"),
    "Роли разделены по каталогам репозитория, поэтому работа шла "
    "параллельно и без конфликтов.")

# --- 21. Финал -----------------------------------------------------------
slides["final"] = section(
    "final",
    f"background:{DARK}; color:{ON_DARK}; font-family:{TEXT}; padding:128px; "
    "display:flex; flex-direction:column; justify-content:center; gap:44px",
    f'<h2 style="font-family:{DISPLAY}; font-size:96px; font-weight:600; '
    f'line-height:1.1; width:1500px">Вывоз по факту, а не по расписанию</h2>'
    f'<p style="font-size:34px; line-height:1.4; color:{BODY_DARK}; '
    f'width:1300px">Репозиторий с прошивкой, сервером, приложением, схемами '
    f'и моделями корпуса. Документация — от развёртывания до сборки '
    f'устройства своими руками.</p>'
    f'<p style="font-size:30px; color:{GREEN_LIGHT}">Спасибо. '
    f'Готовы ответить на вопросы.</p>',
    "Спасибо за внимание.")

ORDER = ["cover", "problem", "idea", "arch", "device", "case", "case_why",
         "schematic", "sch_why", "wiring", "power", "protocol", "app", "bot",
         "plugplay", "stand", "monitoring", "trials", "status", "team",
         "final"]

SECTIONS = {
    "s1": {"description": "Зачем нужна система и что она делает",
           "start": "cover"},
    "s2": {"description": "Устройство: корпус, схема, энергопотребление",
           "start": "device"},
    "s3": {"description": "Серверная часть, приложение и сценарии "
                          "использования", "start": "protocol"},
    "s4": {"description": "Пройденный путь, состояние проекта и планы",
           "start": "trials"},
}

index = {
    "v": 4,
    "createdOnFiles": {"v": 1, "at": "2026-09-23T16:30:00Z"},
    "title": "BinSense",
    "order": ORDER,
    "cover": "cover",
    "sections": SECTIONS,
    "faces": {
        "rubik": {
            "family": "Rubik",
            "href": "https://fonts.googleapis.com/css2?family=Rubik:"
                    "wght@400;500;600;700&display=swap"},
        "ibm-plex-sans": {
            "family": "IBM Plex Sans",
            "href": "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:"
                    "wght@400;500;600&display=swap"},
    },
    "designSystems": [],
}

os.makedirs(SLIDES, exist_ok=True)
for sid in ORDER:
    with io.open(os.path.join(SLIDES, f"{sid}.html"), "w", encoding="utf-8",
                 newline="\n") as handle:
        handle.write(slides[sid])
with io.open(os.path.join(ROOT, "project", "deck.json"), "w", encoding="utf-8",
             newline="\n") as handle:
    json.dump(index, handle, ensure_ascii=False, indent=2)

for sid in ORDER:
    size = os.path.getsize(os.path.join(SLIDES, f"{sid}.html"))
    print(f"{sid:12s} {size:7d} байт")
print("файлов:", len(ORDER) + 1, "->", ROOT)
