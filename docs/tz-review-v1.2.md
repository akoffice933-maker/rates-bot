# Ревью ТЗ v1.1 «Агрегатор курсов валют Аргентины» + дополнения

Дата ревью: 21.09.2026. Источники проверены живыми запросами (curl) в день ревью.

---

## 1. Вердикт

**Общая оценка: 7/10 — крепкая основа, но статус «К реализации MVP» преждевременен.**
Сначала нужно устранить 7 критических замечаний (раздел 4) — все они правятся за 1–2 дня на уровне документа.

| Аспект | Оценка | Комментарий |
|---|---|---|
| Полнота функциональных требований | 8/10 | Есть таблицы, фильтры, API, критерии приёмки |
| Техническая корректность (схема БД, стек) | 5/10 | 3 бага в схеме: UNIQUE+NULL, SQLite vs Postgres DDL, нет country |
| Работа с данными и методология | 4/10 | Нет определения «лучшего предложения», фильтрации выбросов, семантики buy/sell для P2P |
| Безопасность | 2/10 | Раздела нет вообще |
| Мониторинг и эксплуатация | 3/10 | Есть логи парсеров, нет алертов/health/бэкапов |
| Продукт: SEO и рост | 3/10 | Для публичного сравнительного сайта SEO не упомянуто |
| Реалистичность плана (4 недели) | 6/10 | На пределе для 1 разработчика; есть способ срезать (см. п. 6.9) |
| Раздел рисков | 7/10 | Хороший; ключевой риск (блокировка Binance) подтверждён проверкой |

**Что уже хорошо (не трогаем):**
- Чёткий MVP-скоуп, явный список «что НЕ входит», критерии приёмки — редко кто так пишет.
- Приоритизация источников и план по неделям.
- Схема с индексами, Alembic, .env.example, пиннинг версий зависимостей.
- Риски с mitigation — раздел, который обычно забывают.

---

## 2. Результаты живой проверки источников (21.09.2026)

Проверено запросами из песочницы — это меняет приоритеты в разделе 4 ТЗ.

| Источник | Статус | Что вернул | Вывод |
|---|---|---|---|
| Bluelytics `api.bluelytics.com.ar/v2/latest` | ✅ работает | oficial 1482/1534, blue 1517/1550, обновлено 21.09 10:30 −03:00 | Оставить как есть |
| **DolarAPI** `dolarapi.com/v1/dolares` | ✅ работает | 7 курсов разом: oficial, blue, bolsa (MEP), CCL, mayorista, **cripto, tarjeta** | **Добавить в MVP** — идеальный кросс-чек Bluelytics + даёт «tarjeta» |
| **CriptoYa** `criptoya.com/api/USDT/ARS/1` | ✅ работает | ~20 площадок: buenbit, ripio, satoshitango, decrypto, letsbit, binancep2p, fiwind, **lemoncash**, okexp2p (OKX P2P), vitawallet, belo, tiendacrypto, bybitp2p, huobip2p… | **Главная находка.** Один запрос закрывает почти весь список 4.2 «средний приоритет» (Lemon, Belo, Ripio, Buenbit, Bybit P2P, OKX P2P) |
| CriptoYa `criptoya.com/api/dolar` | ✅ работает | blue, mep (по облигациям AL30/GD30), cripto (usdt/usdc/ccb), tarjeta | Дублирует Bluelytics — второй fallback |
| Bitso `api.bitso.com/v3/ticker?book=usdt_ars` | ✅ работает | last 1594.71, bid/ask, объём 382k USDT | ОК, в MVP |
| **Binance bapi** `p2p.binance.com/bapi/ads/...` | ❌ **403 Forbidden** с датацентрового IP | — | Риск из раздела 12 подтверждён фактически. Нужны AR-резидентные прокси с первого дня + fallback на CriptoYa (там есть агрегат `binancep2p`) |
| Telegram web-preview `t.me/s/ambitodolar` | ✅ HTTP 200 | HTML со постами | **Telethon не нужен как основной способ.** Парсим `t.me/s/<channel>` обычным requests+BS4, userbot — только fallback |

**Сверка котировок из ТЗ с живыми данными:** цифры в ТЗ (blue 1503,50/1550; oficial 1488,95/1535; CCL 1590/1595) близки к реальности, но compra по blue устарел на ~1–2% (живой: 1517–1530). **Рекомендация: убрать конкретные котировки из ТЗ** — это спецификация, а не снимок рынка; цифры устаревают за день.

**Ключевые рыночные цифры на 21.09.2026 (для контекста, не для ТЗ):**
- Разрыв oficial ↔ blue сжался до **~1–3%** после отмены cepo — «классическая» история арбитража blue vs oficial умерла (см. стратегическое замечание С1).
- А вот **спред USDT vs blue жив**: продажа USDT на биржах/P2P ~1590–1624 ARS против blue sell 1550 → **+3…+4,7%**. Это и есть главная метрика продукта.

---

## 3. Стратегическое замечание (не блокер, но важно)

**С1. Конвергенция курсов меняет ценностное предложение.**
После отмены валютного контроля (2025) oficial, MEP и blue сошлись в диапазоне ~1480–1550, разрыв 1–3% — публичные сравнения типа «blue дороже oficial на 200%» больше не являютсяkiller-фичей.

Что это значит для продукта — переакцентировать в разделе 1 ТЗ:
1. **Главная ценность №1:** «Где выгоднее купить/продать USDT прямо сейчас» — сравнение P2P-объявлений и крипто-бирж с учётом способа оплаты (MercadoPago и т.д.) и лимитов. Это никто не делает удобно для Аргентины.
2. **Главная ценность №2:** спред USDT vs blue (~3–4% сейчас) — живая метрика, оставить.
3. **Дифференциатор:** мульти-страновой LatAm-агрегатор (Перу, Чили и т.д. из v4.0) — там Binance P2P остаётся основным рынком.
4. Курсы oficial/blue/MEP/CCL — контекстная справка, а не главный экран.

---

## 4. Критические замечания (устранить до старта)

**К1. UNIQUE-конструкция порождает дубликаты.**
`UNIQUE (source, currency_pair, rate_type, payment_method, timestamp)` — в Postgres `NULL ≠ NULL`, поэтому строки P2P без payment_method (NULL) **никогда не конфликтуют** и UPSERT не срабатывает — дубликаты при каждом цикле.
Fix: `payment_method TEXT NOT NULL DEFAULT ''` (работает и в PG, и в SQLite) либо `UNIQUE NULLS NOT DISTINCT` (только PG 15+).

**К2. DDL несовместим со стеком MVP.**
Схема написана под Postgres (`SERIAL`, `JSONB`, `TIMESTAMPTZ`), а MVP — SQLite: в SQLite этого всего нет, `NUMERIC` деградирует до REAL (потеря точности на курсах), таймзоны — строки.
Fix (рекомендую): **Postgres в docker-compose с первого дня**. Проект и так докеризуется, миграция SQLite→PG на неделе 3 — лишний риск и работа. SQLite оставить только для unit-тестов.

**К3. В таблице rates нет страны** — эндпоинт `GET /rates?country=PE` из раздела 5.3 неработоспособен (фильтровать не по чему).
Fix: `country CHAR(2) NOT NULL DEFAULT 'AR'` + включить в индексы. Заодно это фундамент для раздела 4.4.

**К4. Схема не различает агрегаты и P2P-объявления.**
У объявления (ad) есть ровно одна сторона и одна цена, а в текущей схеме строка содержит и buy, и sell, и advertiser_name, и completion_rate вперемешку с агрегатами типа blue. Плюс не специфицированы единицы измерения (min_amount — в ARS или USDT? available — в USDT?).
Fix: разделить на `rates` (агрегаты и рыночные курсы) и `p2p_ads` (объявления) — готовый DDL в п. 6.4.

**К5. Нет методологии расчётов.** Не определено:
- какой курс P2P берём для спреда (лучший? медиану топ-N?);
- что такое «лучшее предложение» при наличии бait-объявлений (без фильтрации выбросов таблица будет врать — см. живой пример: huobip2p на CriptoYa отдаёт ask 1930 / bid 1122 при рынке ~1596 — мусорные данные реально существуют);
- семантика сторон Binance: `tradeType=SELL` — это объявления продавцов USDT, т.е. **минимальная цена среди них = лучшая покупка USDT пользователем** (классическая ошибка — перепутать стороны, и вся таблица инвертируется).
Fix: новый раздел «Методология и качество данных» — п. 6.2.

**К6. Блокировка Binance подтверждена (403 с датацентровых IP).**
Прокси-пул — не «план Б», а обязательное условие недели 1, притом **резидентные AR-прокси** (датацентровые не проходят). Плюс нужен бюджет: при цикле 3 мин × 2 стороны × 1 страница (rows=20) трафик ~150–300 МБ/день ≈ **$10–30/мес** на прокси. Это надо заложить в ТЗ явно. Fallback: агрегат `binancep2p` из CriptoYa.

**К7. Безопасность отсутствует.** Админка из 5.4 без аутентификации, публичный API без rate limit и CORS-политики, `raw_data` (сырые ответы источников) предполагается к выдаче, секреты Telegram-сессии. Fix: раздел 19 — п. 6.7.

---

## 5. Сводка недостающих разделов

| Пробел | Куда вставить |
|---|---|
| Кэширование, версионирование и rate limit собственного API | 5.3 (доп.) |
| Методология расчёта спреда/лучшего предложения, фильтрация выбросов | новый 5.5 |
| Качество данных: staleness, circuit breaker, sanity-чеки | новый 5.6 |
| Исправленная схема БД (rates / p2p_ads / spreads / агрегаты) | 8 (заменить) |
| Политика ретенции и агрегации истории | 8 (доп.) |
| Безопасность | новый 19 |
| SEO и производительность фронтенда | новый 20 |
| Мониторинг, алерты, бэкапы | новый 21 |
| CI/CD | новый 22 |
| Таймзоны, формат чисел/локалей | 6 (доп.) |
| Бюджет на прокси и допущения по команде | 7/10 (доп.) |
| Day-0 spike (фикстуры реальных ответов) | 10 (доп.) |

---

## 6. Готовые дополнения (вставлять в ТЗ как есть)

### 6.1. Замена раздела 4.1 — источники MVP (после живой проверки)

| Источник | Тип | Что даёт | Приоритет |
|---|---|---|---|
| Binance P2P (bapi, AR-резид. прокси) | P2P | USDT/ARS объявления + способы оплаты | 1 — но через прокси, fallback CriptoYa |
| Bluelytics | API | blue, oficial (+ euro) | 1 |
| **DolarAPI** `dolarapi.com/v1/dolares` | API | oficial, blue, MEP, CCL, mayorista, cripto, tarjeta | 1 (новый: кросс-чек + tarjeta) |
| **CriptoYa** `criptoya.com/api/USDT/ARS/{vol}` и `/api/dolar` | API-агрегатор | ~20 бирж/P2P: lemon, belo, ripio, buenbit, bybitp2p, okexp2p, fiwind, letsbit, satoshitango, tiendacrypto, decrypto, vitawallet, binancep2p… | 1 (новый: закрывает весь список 4.2 одним запросом) |
| Bitso | API | USDT/ARS спот bid/ask + объём | 2 |
| Telegram через `t.me/s/<channel>` | парсинг HTML | blue, oficial от @ambitodolar и др. | 2 — **без Telethon** (userbot → fallback) |

Условия использования CriptoYa: атрибуция на сайте и в API-ответах, кэширование ≥60 сек, частота опроса ≤1 раза в 2–3 мин на эндпоинт.

> Примечание: свои парсеры Lemon/Belo/Ripio/Buenbit из «среднего приоритета» больше не нужны как отдельные задачи — CriptoYa покрывает их все. Собственные парсеры пишем позже только для топ-3 площадок (независимость от агрегатора). Это сжимает план на ~1 неделю.

### 6.2. Новый раздел 5.5 — Методология и расчёты

- **Агрегат P2P по (source, pair, payType):** медиана топ-10 объявлений после фильтров; отдельно min/max.
- **Фильтры объявлений:** completion_rate ≥ 0.90 (настраивается), min_amount ≤ суммы пользователя, отсечение выбросов: объявление отбрасывается, если цена отклоняется от медианы первого прохода более чем на ±10%.
- **«Лучшее предложение»:** max(цена) среди `tradeType=BUY`-объявлений для продажи USDT; min(цена) среди `tradeType=SELL`-объявлений для покупки USDT (семантика сторон Binance — см. К5, тест на инверсию обязателен).
- **Спред USDT vs Blue:** `spread_pct = (p2p_median_sell − blue_sell) / blue_sell × 100`. Знак: «+» = USDT дороже blue. Медиана, а не лучший P2P (лучший часто бait).
- **Сравнение валют без допущения USDT = USD:** всегда через фактические котировки обеих пар.

### 6.3. Новый раздел 5.6 — Качество данных

- **Staleness:** строка помечается `is_stale`, если её возраст > 3× интервал опроса источника; на UI — серым + подпись «устарело».
- **Sanity-чеки при записи:** цена > 0; для агрегатов buy ≤ sell (иначе отбраковка + алерт); |Δ| к предыдущему значению > 25% → записать с флагом anomalous, в агрегаты не брать.
- **Circuit breaker на источник:** 5 подряд ошибок → `sources.enabled = 0`, алерт, авто-retry через 30 мин.
- **Кросс-валидация:** blue/oficial сверяются Bluelytics ↔ DolarAPI; расхождение > 2% → алерт.

### 6.4. Дополнение к разделу 5.3 — API

- Версионирование: все эндпоинты под `/v1/...`.
- Кэш ответов 30–60 сек + `ETag`; rate limit 60 req/min на IP (`429` + `Retry-After`); CORS-allowlist.
- `GET /v1/sources` — публичный статус источников (имя, страна, включён, updated_at) — без internals.
- `GET /v1/history` — параметр `interval=5m|1h|1d` + даунсемплинг до ≤1000 точек на ответ (30 дней 5-минуток = ~8,6k точек — фронт не должен тянуть сырьё).
- `raw_data` никогда не отдаётся наружу.
- Формат ошибок единый: `{"detail": "...", "code": "..."}`.

### 6.5. Замена раздела 8 — схема хранения (исправленная)

> Postgres 15+ с первого дня (SQLite — только для unit-тестов). Все `timestamp` — UTC (TIMESTAMPTZ); отображение — на клиенте в America/Argentina/Buenos_Aires.

```sql
-- Агрегаты и рыночные курсы (blue, oficial, mep, ccl, p2p-медианы, spot)
CREATE TABLE rates (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,             -- bluelytics, dolarapi, criptoya:binancep2p ...
    source_type     TEXT NOT NULL,             -- p2p, api, site, bank, telegram, aggregator
    country         CHAR(2) NOT NULL DEFAULT 'AR',
    currency_pair   TEXT NOT NULL,             -- USDT/ARS, USD/ARS
    rate_type       TEXT NOT NULL,             -- blue, oficial, mep, ccl, p2p, spot
    buy             NUMERIC(14,4),             -- ARS за 1 USDT/USD, источник покупает
    sell            NUMERIC(14,4),             -- ARS за 1 USDT/USD, источник продаёт
    median_price    NUMERIC(14,4),             -- для p2p-агрегатов
    min_price       NUMERIC(14,4),
    max_price       NUMERIC(14,4),
    payment_method  TEXT NOT NULL DEFAULT '',  -- '' = неприменимо (агрегат)
    is_stale        BOOLEAN NOT NULL DEFAULT FALSE,
    timestamp       TIMESTAMPTZ NOT NULL,      -- UTC
    raw_data        JSONB,
    UNIQUE (source, country, currency_pair, rate_type, payment_method, timestamp)
);
CREATE INDEX idx_rates_lookup ON rates (country, currency_pair, rate_type, timestamp DESC);
CREATE INDEX idx_rates_source ON rates (source, timestamp DESC);

-- P2P-объявления (для «лучших предложений» и медиан)
CREATE TABLE p2p_ads (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,             -- binance_p2p, bybit_p2p ...
    country         CHAR(2) NOT NULL DEFAULT 'AR',
    currency_pair   TEXT NOT NULL,             -- USDT/ARS
    side            TEXT NOT NULL,             -- buy: реклама КУПИТ USDT; sell: ПРОДАСТ USDT
    price           NUMERIC(14,4) NOT NULL,    -- ARS за 1 USDT
    payment_method  TEXT NOT NULL DEFAULT '',
    min_amount      NUMERIC(16,2),             -- В FIAT-ВАЛЮТЕ ПАРЫ (ARS)
    max_amount      NUMERIC(16,2),             -- В FIAT-ВАЛЮТЕ ПАРЫ (ARS)
    available       NUMERIC(16,2),             -- В БАЗОВОЙ ВАЛЮТЕ (USDT)
    advertiser_name TEXT,
    completion_rate NUMERIC(5,4),              -- 0..1 (доля, не %)
    adv_no          TEXT,                      -- ID объявления (Binance advNo), если есть
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    raw_data        JSONB
);
CREATE INDEX idx_ads_best ON p2p_ads (country, currency_pair, side, price, last_seen_at DESC);

-- Спреды (обобщённо, без хардкода USDT/blue в имена колонок)
CREATE TABLE spreads (
    id          BIGSERIAL PRIMARY KEY,
    country     CHAR(2) NOT NULL DEFAULT 'AR',
    base_pair   TEXT NOT NULL,                 -- USDT/ARS
    quote_pair  TEXT NOT NULL,                 -- USD/ARS
    base_rate   NUMERIC(14,4),                 -- медиана p2p-продажи USDT
    quote_rate  NUMERIC(14,4),                 -- blue sell
    abs_diff    NUMERIC(14,4),
    spread_pct  NUMERIC(8,4),                  -- + = base дороже quote
    timestamp   TIMESTAMPTZ NOT NULL
);

-- Часовые агрегаты для истории (даунсемплинг)
CREATE TABLE rates_hourly (
    source         TEXT NOT NULL,
    country        CHAR(2) NOT NULL,
    currency_pair  TEXT NOT NULL,
    rate_type      TEXT NOT NULL,
    payment_method TEXT NOT NULL DEFAULT '',
    ts_hour        TIMESTAMPTZ NOT NULL,
    buy_avg NUMERIC(14,4), buy_min NUMERIC(14,4), buy_max NUMERIC(14,4),
    sell_avg NUMERIC(14,4), sell_min NUMERIC(14,4), sell_max NUMERIC(14,4),
    samples INTEGER NOT NULL,
    PRIMARY KEY (source, country, currency_pair, rate_type, payment_method, ts_hour)
);
```

**Ретенция (nightly job):**
- `p2p_ads` — хранить 30 дней (история объявлений не нужна);
- `rates` — сырые 90 дней;
- `rates_hourly` — бессрочно (это и есть «история» после 90 дней);
- `raw_data` — обнулять у записей старше 7 дней (экономия места).

**Дополнение к 8.3 (sources):** добавить поля `poll_interval_seconds INT`, `timeout_seconds INT DEFAULT 10`, `priority INT`. Существующая схема (одна строка на пару, `binance_p2p_ars`, `binance_p2p_pen`) — корректна, оставить.

### 6.6. Дополнение к разделу 6 — нефункциональные

| Требование | Значение |
|---|---|
| p95 задержки API | < 300 мс |
| Кэш ответов API | 30–60 сек, ETag |
| Rate limit публичного API | 60 req/min/IP |
| Время | Хранение UTC; отображение America/Argentina/Buenos_Aires (UTC−3); «обновлено X мин назад» считается на клиенте |
| Формат чисел | Intl по локали: es-AR `1.503,50`; RU `1 503,50` |
| Lighthouse mobile | ≥ 85 |
| Отказ источника | Сайт продолжает работать (graceful degradation), источник помечен |
| Прокси-бюджет | ~$10–30/мес (AR residential, ~150–300 МБ/день при цикле 3 мин) |

### 6.7. Новый раздел 19 — Безопасность

- **Админка (5.4)** — только за аутентификацией: basic-auth или OAuth, отдельный поддомен/путь + IP-allowlist; не индексируется (noindex, X-Robots-Tag).
- Публичный API: CORS-allowlist, rate limit, запрет выдачи `raw_data` и `advertiser`-деталей сверх необходимых полей.
- HTTPS + HSTS, security headers (X-Content-Type-Options, X-Frame-Options, CSP) на nginx.
- Секреты (Telegram session, прокси-креды) — только через env / secret manager, в git никогда; `.env` в `.gitignore` (в репо — только `.env.example`).
- Таймауты на все исходящие запросы парсеров — 10 сек; лимит размера ответа — 5 МБ.
- Зависимости: пины версий + Dependabot; `pip-audit` / `npm audit` в CI.

### 6.8. Новый раздел 20 — SEO и фронтенд

Для сайта-агрегатора трафик = SEO, это фактически функциональное требование:

- Next.js: **SSR/ISR с `revalidate: 60`** для страниц курсов (не чистый CSR — иначе нет индексации).
- Мета-теги + OG для каждой страницы/пары; `sitemap.xml`; `hreflang` для es/ru.
- JSON-LD для данных, где применимо.
- Обновление данных на клиенте: SWR-поллинг 30–60 сек (не WebSocket — MVP не требует).
- Состояние фильтров — в URL (шаряемые ссылки вида `/?pair=USDT/ARS&type=p2p&pay=MercadoPago`).
- i18n через next-intl: `/es/...`, `/ru/...`; рассмотреть `/en` для туристов (низкая цена, высокая отдача).
- Мобильная таблица: карточный режим < 768px вместо горизонтального скролла.

### 6.9. Новый раздел 21 — Мониторинг и эксплуатация

- `GET /health` (liveness) и `GET /ready` (проверка БД + свежесть данных: самый свежий rate < 15 мин).
- Sentry (или self-hosted GlitchTip) — ошибки бэка и фронта.
- **Алерты:** источник недоступен > 15 мин; нет свежих данных по паре > 10 мин; аномальный скачок курса > 10% за 5 мин; circuit breaker сработал.
- Внешний uptime-мониторинг (healthchecks.io / UptimeRobot).
- Бэкапы: pg_dump ежедневно, хранение 7 дней; **проверка восстановления** — один раз вручную, результат зафиксировать.
- Метрики парсеров (успех/ошибка/длительность по источникам) — хотя бы в логи со структурой (JSON-logs), Prometheus `/metrics` — опционально после MVP.

### 6.10. Новый раздел 22 — CI/CD

- GitHub Actions: `ruff` (lint) → `mypy` → `pytest` → build docker-образов.
- Тесты парсеров — на **фикстурах с реальными ответами источников** (снять curl'ом на Day-0), плюс по одному live-smoke-тесту с маркировкой `@pytest.mark.live` (не блокирует CI).
- Деплой по тегу на VPS через watchtower/registry; `.env.example` актуализируется в PR.

### 6.11. Правка раздела 10 — план MVP

**Day 0 (0,5–1 день, обязательный spike):** curl'ом снять и зафиксировать реальные ответы всех источников (Bluelytics, DolarAPI, CriptoYa, Bitso, Binance через прокси, t.me/s) → положить в `tests/fixtures/`. Дальше парсеры пишутся против фикстур, а не вслепую.

| Неделя | Задачи (скорректировано) |
|---|---|
| 1 | Каркас: FastAPI + Postgres + docker-compose + CI; Binance P2P через AR-прокси; Bluelytics + DolarAPI; UPSERT/дедуп; методы фильтрации |
| 2 | **CriptoYa (все ~20 площадок разом) + Bitso**; p2p_ads + медианы + circuit breaker; спред-калькулятор; черновая таблица |
| 3 | Фильтры/сортировка/подсветка лучших; мобильная вёрстка; i18n ES+RU; SEO-база (SSR/ISR, sitemap) |
| 4 | `/v1` API + кэш + rate limit; история + графики; деплой; мониторинг/алерты; стабилизация |

Существенное изменение: за счёт CriptoYa «средний приоритет» из 4.2 попадает в неделю 2 бесплатно. Если не успеваем — режем историю (неделя 4 → v1.3), а не качество данных.

### 6.12. Дополнение к разделу 13 — критерии приёмки

Добавить к существующим:

- ☐ `GET /health` и `/ready` отвечают; при остановке любого источника сайт деградирует корректно
- ☐ p95 API < 300 мс; rate limit и кэш включены
- ☐ Тест на инверсию сторон Binance P2P (лучшая покупка < лучшая продажа) проходит
- ☐ Выбросы (ad с отклонением > 10% от медианы) не попадают в агрегаты и «лучшие предложения»
- ☐ Все времена в API — UTC; на UI — локальное время и «обновлено X мин назад»
- ☐ Бэкап БД развёрнут из копии (проверено)
- ☐ Фикстуры реальных ответов источников в репозитории, тесты парсеров зелёные в CI

### 6.13. Мелкие правки (nitpicks)

1. `BINANCE_MIN_COMPLETION_RATE=0.90` — указать формат: доля 0..1 (Binance отдаёт именно так), не проценты.
2. `NEXT_PUBLIC_API_URL=http://localhost:8000` — для прода: same-origin через nginx (Next rewrites `/api/*` → backend), порт 8000 наружу не светить.
3. requirements.txt дополнить: `httpx`, `slowapi`, `sentry-sdk` (опц.), `orjson`.
4. package.json дополнить: `swr`, `next-intl`, `date-fns`.
5. docker-compose: сервисы `postgres`, `api`, `scheduler`, `frontend`, `nginx` + healthchecks; Adminer — только dev-профиль.
6. `.env.example` дополнить: `API_RATE_LIMIT=60/minute`, `CACHE_TTL_SECONDS=45`, `SENTRY_DSN=`, `ADMIN_TOKEN=`, `CRIPTOYA_BASE=`, `DOLARAPI_BASE=`, `TZ=UTC`.
7. Раздел 4.1 «Ámbito / La Nación (парсинг)» — понизить до последнего fallback'а: DolarAPI+Bluelytics закрывают это API-шно; парсинг новостных сайтов — самый хрупкий путь.
8. В `sources.yaml` сразу заложить `poll_interval`, `timeout`, `priority` на источник.
9. Указать допущение по команде: план 4 недель рассчитан на 1 fullstack-разработчика; при 2 людях можно вернуть историю в неделю 3.
10. CriptoYa отдаёт `time` как unix epoch — нормализовать в UTC ISO при записи (общее правило для всех парсеров).

---

## 7. Что дальше (ответ на «с чего начинаем»)

Рекомендуемый порядок:

1. **Внедрить правки из этого ревью в ТЗ** (1–2 часа) — статус можно менять на «К реализации».
2. **Day-0 spike**: зафиксировать фикстуры всех источников (полдня; бо́шая часть уже сделана — см. раздел 2, могу оформить в файлы).
3. **Блок 4 из вашего списка** (рабочий код `binance_p2p.py` + `bluelytics.py`) — но с учётом К4/К5: сначала модели `rates`/`p2p_ads`, потом парсеры против фикстур.
4. Блоки 1–3 (детализация таблицы, OpenAPI, docker-compose) — по ходу, они быстро пишутся поверх готового кода.

Готов следующим шагом сделать любой из блоков 1–4, либо сразу собрать каркас проекта (docker-compose + модели + два парсера + фикстуры).
