"""Строки интерфейса: испанский (основной) + русский.

Инвариант (проверяется тестом): наборы ключей es и ru совпадают.
"""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "es": {
        "WELCOME": (
            "👋 ¡Hola! Comparo en tiempo real las cotizaciones del dólar y del USDT "
            "en Argentina.\n\nOficial, blue, MEP, CCL, tarjeta y USDT/ARS "
            "en decenas de plataformas.\n\nElegí una opción:"
        ),
        "HELP": (
            "🤖 <b>Comandos</b>\n\n"
            "/rates — cotizaciones del dólar (oficial, blue, MEP, CCL, tarjeta)\n"
            "/usdt — mejores precios de USDT/ARS\n"
            "/spread — brecha USDT vs Blue\n"
            "/alert — alertas de brecha y de cotización\n"
            "/p2p — anuncios en vivo de Binance P2P\n"
            "/digest — resumen diario\n"
            "/lang — idioma / язык\n\n"
            "🔁 — invertir la pareja en /rates y /usdt (ARS/USD, ARS/USDT)\n"
            "💵 — volumen de cálculo en la pantalla /usdt\n\n"
            "ℹ️ Datos de Bluelytics, DolarAPI y CriptoYa. Solo informativo, "
            "no constituye asesoramiento financiero."
        ),
        "BTN_RATES": "📊 Cotizaciones",
        "BTN_USDT": "💰 USDT/ARS",
        "BTN_SPREAD": "📈 Brecha USDT vs Blue",
        "BTN_LANG": "🌐 Idioma",
        "BTN_BACK": "⬅️ Menú",
        "BTN_REFRESH": "🔄 Actualizar",
        "BTN_SWAP": "🔁 {pair}",
        "RATES_TITLE": "📊 USD/ARS — cotizaciones del dólar",
        "RATES_TITLE_INV": "📊 ARS/USD — dólares por $1.000",
        "RATES_LEGEND_INV": "→ comprar USD · ← vender USD · por $1.000 ARS",
        "ROW_OFICIAL": "Oficial",
        "ROW_BLUE": "Blue",
        "ROW_MEP": "MEP (bolsa)",
        "ROW_CCL": "CCL",
        "ROW_TARJETA": "Tarjeta",
        "PAIR_NOTE": "compra / venta · ARS por 1 USD",
        "SOURCES": "Fuentes",
        "UPDATED": "Actualizado",
        "USDT_TITLE": "💰 USDT/ARS — mejores precios",
        "USDT_TITLE_INV": "💰 ARS/USDT — USDT por $1.000",
        "USDT_BUY_HEADER_INV": "Comprar USDT (más USDT por $1.000):",
        "USDT_SELL_HEADER_INV": "Vender USDT (menos USDT por $1.000):",
        "USDT_NOTE_INV": "USDT que obtenés o entregás por $1.000 · precios con comisiones.",
        "USDT_BUY_HEADER": "Comprar USDT (más barato primero):",
        "USDT_SELL_HEADER": "Vender USDT (más caro primero):",
        "USDT_NOTE": "Precios totales con comisiones de cada plataforma.",
        "USDT_VOLUME_NOTE": "Volumen de cálculo: {vol} USDT",
        "SPREAD_TITLE": "📈 Brecha USDT vs Blue",
        "SPREAD_SELL_TITLE": "Vender",
        "SPREAD_BUY_TITLE": "Comprar",
        "SPREAD_USDT_MEDIAN": "USDT (mediana de plataformas)",
        "SPREAD_BLUE_BUY": "Blue (compra)",
        "SPREAD_BLUE_SELL": "Blue (venta)",
        "SPREAD_SELL_RESULT": "→ Ventaja de vender USDT: {pct}",
        "SPREAD_BUY_RESULT": "→ Sobrecosto de comprar USDT: {pct}",
        "SPREAD_NOTE": "Cálculo por mediana; se filtran precios atípicos (±10 %).",
        "STALE_BANNER": "⚠️ Datos antiguos",
        "PARTIAL": "Algunas fuentes no respondieron",
        "NO_DATA": "😔 No pude obtener cotizaciones ahora. Probá de nuevo en unos minutos.",
        "LANG_PROMPT": "Elegí el idioma:",
        "LANG_SET": "✅ Idioma cambiado.",
        "JUST_NOW": "ahora mismo",
        "CRIPTOYA_CREDIT": "Datos: CriptoYa",
        "BTN_ALERT": "🔔 Alertas",
        "BTN_ALERT_ADD": "➕ Nueva alerta",
        "BTN_CUSTOM": "✏️ Otro valor",
        "ALERT_TITLE": "🔔 Alertas — brecha y cotizaciones",
        "ALERT_LIST": "Alertas activas:",
        "ALERT_EMPTY": "No tenés alertas todavía.",
        "ALERT_ITEM": "• {metric} {op}{th}",
        "ALERT_METRIC_PROMPT": "¿Qué querés vigilar?",
        "ALERT_METRIC_SELL": "📉 Ventaja de vender USDT",
        "ALERT_METRIC_BUY": "📈 Sobrecosto de comprar USDT",
        "M_BLUE_BUYUSD": "💵 Blue — compra de USD",
        "M_BLUE_SELLUSD": "💵 Blue — venta de USD",
        "M_USDT_BUY": "💰 USDT — compra (mediana)",
        "M_USDT_SELL": "💰 USDT — venta (mediana)",
        "ALERT_DIR_PROMPT": "¿Avisar si sube o si baja?",
        "ALERT_DIR_ABOVE": "⬆️ Si sube de un valor",
        "ALERT_DIR_BELOW": "⬇️ Si baja de un valor",
        "ALERT_VALUE_PROMPT": "¿A partir de qué valor?",
        "ALERT_THRESHOLD_PROMPT": "¿A partir de qué brecha avisar?",
        "ALERT_CUSTOM_PROMPT": "Escribí el umbral en % (por ejemplo 3,5):",
        "ALERT_CUSTOM_BAD": "⛔️ No entendí el número. Ejemplo: 3,5 (entre 0,5 y 20).",
        "ALERT_CUSTOM_PROMPT_ABS": "Escribí el valor en ARS (por ejemplo 1600):",
        "ALERT_CUSTOM_BAD_ABS": "⛔️ No entendí el número. Ejemplo: 1600 (entre 100 y 1.000.000).",
        "ALERT_ADDED": "✅ Alerta creada.",
        "ALERT_EXISTS": "⚠️ Ya tenés esa alerta.",
        "ALERT_REMOVED": "🗑 Alerta eliminada.",
        "ALERT_HOW": "Control cada {poll} s · aviso al cruzar el umbral, como máximo cada {cooldown} min.",
        "ALERT_FIRED_SELL_TITLE": "🔔 Brecha de venta USDT: {pct}",
        "ALERT_FIRED_BUY_TITLE": "🔔 Sobrecosto de compra USDT: {pct}",
        "ALERT_FIRED_ABS_TITLE": "🔔 {metric}: {value}",
        "ALERT_THRESHOLD_NOTE": "Umbral: {th}",
        "ALERT_FIRED_FOOTER": "Datos: CriptoYa · /alert para gestionar alertas",
        "BTN_LINKS": "🌍 Abrir todo",
        "LINKS_TITLE": "🌍 Enlaces y fuentes",
        "LINKS_NOTE": "Cotizaciones en vivo en los sitios oficiales de las fuentes:",
        "LINKS_USD_TITLE": "💵 Dónde comprar / vender USD",
        "LINKS_USD_NOTE": (
            "🏦 Banco — curso oficial\n"
            "📈 Brokers y apps — curso MEP: la forma legal y conveniente\n"
            "💵 Blue — mercado informal en efectivo (cuevas), sin sitio web"
        ),
        "BTN_P2P": "🤝 Binance P2P",
        "P2P_TITLE": "🤝 Binance P2P — USDT/ARS (anuncios en vivo)",
        "P2P_BUY_HEADER": "Comprar USDT (vendedores, más barato primero):",
        "P2P_SELL_HEADER": "Vender USDT (compradores, más caro primero):",
        "P2P_NOTE": "Verificá límites, reputación y disponibilidad del anuncio.",
        "P2P_EMPTY": "Ahora no hay anuncios que cumplan los filtros.",
        "P2P_UNAVAILABLE": "⛔️ Binance bloquea esta IP (HTTP 403). Para anuncios en vivo configurá proxies AR en PROXY_LIST.",
        "P2P_FALLBACK": "Mientras tanto, agregado de CriptoYa para Binance P2P:",
        "P2P_FB_LINE": "💵 Binance P2P (CriptoYa): compra {ask} · venta {bid}",
        "BTN_DIGEST": "📣 Digesta diaria",
        "DIGEST_TITLE": "📣 Digesta — {date}",
        "DIGEST_DOLLAR": "Cotizaciones del dólar",
        "DIGEST_USDT_BUY": "compra (mediana)",
        "DIGEST_USDT_SELL": "venta (mediana)",
        "DIGEST_BEST": "mejor",
        "DIGEST_FOOTER": "Datos: CriptoYa · Bluelytics · DolarAPI · /digest para configurar",
        "DIGEST_SUB_TITLE": "📣 Digesta diaria — suscripción",
        "DIGEST_STATUS_ON": "✅ Activa: todos los días a las {hour}:00 (hora de Argentina, UTC−3).",
        "DIGEST_STATUS_OFF": "Desactivada.",
        "DIGEST_HOUR_PROMPT": "¿A qué hora enviar el digesta? (hora de Argentina)",
        "DIGEST_ENABLED": "✅ Digesta activada a las {hour}:00.",
        "DIGEST_DISABLED": "🔕 Digesta desactivada.",
        "DIGEST_BTN_CHANGE": "⏰ Cambiar horario",
        "DIGEST_BTN_OFF": "🔕 Desactivar",
    },
    "ru": {
        "WELCOME": (
            "👋 Привет! Я в реальном времени сравниваю курсы доллара и USDT "
            "в Аргентине.\n\nOficial, blue, MEP, CCL, tarjeta и USDT/ARS "
            "по десяткам площадок.\n\nВыбери раздел:"
        ),
        "HELP": (
            "🤖 <b>Команды</b>\n\n"
            "/rates — курсы доллара (oficial, blue, MEP, CCL, tarjeta)\n"
            "/usdt — лучшие цены USDT/ARS\n"
            "/spread — спред USDT vs Blue\n"
            "/alert — алерты спреда и курсов\n"
            "/p2p — живые объявления Binance P2P\n"
            "/digest — ежедневная сводка\n"
            "/lang — язык / language\n\n"
            "🔁 — инверсия пары на /rates и /usdt (ARS/USD, ARS/USDT)\n"
            "💵 — объём расчёта на экране /usdt\n\n"
            "ℹ️ Данные: Bluelytics, DolarAPI и CriptoYa. Только справочная "
            "информация, не является финансовой рекомендацией."
        ),
        "BTN_RATES": "📊 Курсы",
        "BTN_USDT": "💰 USDT/ARS",
        "BTN_SPREAD": "📈 Спред USDT vs Blue",
        "BTN_LANG": "🌐 Язык",
        "BTN_BACK": "⬅️ Меню",
        "BTN_REFRESH": "🔄 Обновить",
        "BTN_SWAP": "🔁 {pair}",
        "RATES_TITLE": "📊 USD/ARS — курс доллара (Аргентина)",
        "RATES_TITLE_INV": "📊 ARS/USD — доллары за 1.000 ARS",
        "RATES_LEGEND_INV": "→ купить USD · ← продать USD · за 1.000 ARS",
        "ROW_OFICIAL": "Oficial (официальный)",
        "ROW_BLUE": "Blue",
        "ROW_MEP": "MEP (биржа)",
        "ROW_CCL": "CCL",
        "ROW_TARJETA": "Tarjeta (карта)",
        "PAIR_NOTE": "покупка / продажа · ARS за 1 USD",
        "SOURCES": "Источники",
        "UPDATED": "Обновлено",
        "USDT_TITLE": "💰 USDT/ARS — лучшие цены",
        "USDT_TITLE_INV": "💰 ARS/USDT — USDT за 1.000 ARS",
        "USDT_BUY_HEADER_INV": "Купить USDT (больше USDT за 1.000 ARS):",
        "USDT_SELL_HEADER_INV": "Продать USDT (меньше USDT за 1.000 ARS):",
        "USDT_NOTE_INV": "USDT, которые получаете или отдаёте за 1.000 ARS · цены с комиссиями.",
        "USDT_BUY_HEADER": "Купить USDT (дешевле — лучше):",
        "USDT_SELL_HEADER": "Продать USDT (дороже — лучше):",
        "USDT_NOTE": "Цены с учётом комиссий площадок.",
        "USDT_VOLUME_NOTE": "Объём расчёта: {vol} USDT",
        "SPREAD_TITLE": "📈 Спред USDT vs Blue",
        "SPREAD_SELL_TITLE": "Продажа",
        "SPREAD_BUY_TITLE": "Покупка",
        "SPREAD_USDT_MEDIAN": "USDT (медиана площадок)",
        "SPREAD_BLUE_BUY": "Blue (покупка)",
        "SPREAD_BLUE_SELL": "Blue (продажа)",
        "SPREAD_SELL_RESULT": "→ Выгода продажи USDT: {pct}",
        "SPREAD_BUY_RESULT": "→ Переплата за покупку USDT: {pct}",
        "SPREAD_NOTE": "Расчёт по медиане; выбросы отфильтрованы (±10 %).",
        "STALE_BANNER": "⚠️ Данные устарели",
        "PARTIAL": "Часть источников не ответила",
        "NO_DATA": "😔 Не удалось получить котировки. Попробуй через пару минут.",
        "LANG_PROMPT": "Выбери язык:",
        "LANG_SET": "✅ Язык изменён.",
        "JUST_NOW": "только что",
        "CRIPTOYA_CREDIT": "Данные: CriptoYa",
        "BTN_ALERT": "🔔 Алерты",
        "BTN_ALERT_ADD": "➕ Новый алерт",
        "BTN_CUSTOM": "✏️ Другое значение",
        "ALERT_TITLE": "🔔 Алерты — спреды и курсы",
        "ALERT_LIST": "Активные алерты:",
        "ALERT_EMPTY": "Пока нет алертов.",
        "ALERT_ITEM": "• {metric} {op}{th}",
        "ALERT_METRIC_PROMPT": "Что отслеживаем?",
        "ALERT_METRIC_SELL": "📉 Выгода продажи USDT",
        "ALERT_METRIC_BUY": "📈 Переплата за покупку USDT",
        "M_BLUE_BUYUSD": "💵 Blue — покупка USD",
        "M_BLUE_SELLUSD": "💵 Blue — продажа USD",
        "M_USDT_BUY": "💰 USDT — покупка (медиана)",
        "M_USDT_SELL": "💰 USDT — продажа (медиана)",
        "ALERT_DIR_PROMPT": "Уведомить при росте или при падении?",
        "ALERT_DIR_ABOVE": "⬆️ При росте выше значения",
        "ALERT_DIR_BELOW": "⬇️ При падении ниже значения",
        "ALERT_VALUE_PROMPT": "При каком значении?",
        "ALERT_THRESHOLD_PROMPT": "При каком спреде уведомить?",
        "ALERT_CUSTOM_PROMPT": "Введи порог в % (например 3,5):",
        "ALERT_CUSTOM_BAD": "⛔️ Не понял число. Пример: 3,5 (от 0,5 до 20).",
        "ALERT_CUSTOM_PROMPT_ABS": "Введи значение в ARS (например 1600):",
        "ALERT_CUSTOM_BAD_ABS": "⛔️ Не понял число. Пример: 1600 (от 100 до 1.000.000).",
        "ALERT_ADDED": "✅ Алерт создан.",
        "ALERT_EXISTS": "⚠️ Такой алерт уже есть.",
        "ALERT_REMOVED": "🗑 Алерт удалён.",
        "ALERT_HOW": "Проверка каждые {poll} с · уведомление при пересечении порога, не чаще раза в {cooldown} мин.",
        "ALERT_FIRED_SELL_TITLE": "🔔 Спред продажи USDT: {pct}",
        "ALERT_FIRED_BUY_TITLE": "🔔 Переплата за покупку USDT: {pct}",
        "ALERT_FIRED_ABS_TITLE": "🔔 {metric}: {value}",
        "ALERT_THRESHOLD_NOTE": "Порог: {th}",
        "ALERT_FIRED_FOOTER": "Данные: CriptoYa · /alert — управление алертами",
        "BTN_LINKS": "🌍 Открыть всё",
        "LINKS_TITLE": "🌍 Ссылки и источники",
        "LINKS_NOTE": "Живые котировки на официальных сайтах источников:",
        "LINKS_USD_TITLE": "💵 Где купить / продать USD",
        "LINKS_USD_NOTE": (
            "🏦 Банк — официальный курс\n"
            "📈 Брокеры и приложения — курс MEP: легально и обычно выгоднее банка\n"
            "💵 Blue — неформальный наличный рынок (cuevas), сайтов нет"
        ),
        "BTN_P2P": "🤝 Binance P2P",
        "P2P_TITLE": "🤝 Binance P2P — USDT/ARS (живые объявления)",
        "P2P_BUY_HEADER": "Купить USDT (продавцы, дешевле — лучше):",
        "P2P_SELL_HEADER": "Продать USDT (покупатели, дороже — лучше):",
        "P2P_NOTE": "Проверяйте лимиты, репутацию и доступность объявления.",
        "P2P_EMPTY": "Сейчас нет объявлений, проходящих фильтры.",
        "P2P_UNAVAILABLE": "⛔️ Binance блокирует этот IP (HTTP 403). Для живых объявлений настройте AR-прокси в PROXY_LIST.",
        "P2P_FALLBACK": "Пока — агрегат CriptoYa по Binance P2P:",
        "P2P_FB_LINE": "💵 Binance P2P (CriptoYa): покупка {ask} · продажа {bid}",
        "BTN_DIGEST": "📣 Дайджест дня",
        "DIGEST_TITLE": "📣 Дайджест — {date}",
        "DIGEST_DOLLAR": "Курс доллара",
        "DIGEST_USDT_BUY": "покупка (медиана)",
        "DIGEST_USDT_SELL": "продажа (медиана)",
        "DIGEST_BEST": "лучшая",
        "DIGEST_FOOTER": "Данные: CriptoYa · Bluelytics · DolarAPI · /digest — настройки",
        "DIGEST_SUB_TITLE": "📣 Дайджест дня — подписка",
        "DIGEST_STATUS_ON": "✅ Включён: каждый день в {hour}:00 (время Аргентины, UTC−3).",
        "DIGEST_STATUS_OFF": "Выключен.",
        "DIGEST_HOUR_PROMPT": "В какое время присылать дайджест? (время Аргентины)",
        "DIGEST_ENABLED": "✅ Дайджест включён на {hour}:00.",
        "DIGEST_DISABLED": "🔕 Дайджест выключен.",
        "DIGEST_BTN_CHANGE": "⏰ Изменить время",
        "DIGEST_BTN_OFF": "🔕 Отключить",
    },
}


def t(lang: str, key: str, **kwargs: object) -> str:
    table = STRINGS.get(lang, STRINGS["es"])
    template = table.get(key) or STRINGS["es"][key]
    return template.format(**kwargs) if kwargs else template
