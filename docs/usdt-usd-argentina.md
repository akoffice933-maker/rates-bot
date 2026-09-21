# USDT/USD и USD/USDT в Аргентине: все площадки (наличные и безнал)

Живая проверка: **21.09.2026** (curl/python из песочницы EU). Методика — только реальные запросы к API/страницам, без пересказа статей.

## Ключевые выводы

1. **Прямая пара USDT/USD есть у CriptoYa** (`https://criptoya.com/api/USDT/USD`) — 16 аргентинских площадок, включая **Binance P2P, OKX P2P и KuCoin P2P** через агрегацию. Это решает проблему их прямых блокировок (bapi.binance.com 403, OKX API 404 из дата-центров). Источник CriptoYa уже интегрирован в бота — остаётся добавить пару.
2. **BestChange имеет безнальные Wire-USD направления**: USDT TRC20 → банковский перевод USD (59 обменников) и обратно (13). Направления «наличный USD» не существуют (301 на все варианты слагов).
3. **Наличный рынок — офлайн-канал (cuevas)**: прямых онлайн-котировок нет ни у одной площадки. Разумный прокси — двухшаговый кросс через blue (см. расчёт) или напрямую в cuevas за комиссию ~2–3%.
4. Спреды: безнал — от почти нуля (Xapo 1.0014/0.9989) до 3–6% у розничных приложений; нал — ~2–3% в cuevas против ~5%/2.9% двухшагово.

## Безнал: CriptoYa USDT/USD (живые котировки 21.09.2026)

`GET https://criptoya.com/api/USDT/USD` → JSON по 16 площадкам (ask = цена покупки USDT, bid = цена продажи):

| Площадка | ask (totalAsk) | bid (totalBid) | Комментарий |
|---|---|---|---|
| **xapo** | **1.0014** | **0.9989** | почти паритет; USD-счета, аргентинские корни |
| astropay | 1.005 | 0.995 | |
| banexcoin | 1.015 | 0.995 | |
| x4t | 1.02 | 0.9409 | bid со скидкой за объём/способ |
| binancep2p | 1.023 | 1.0333 | Binance P2P, виден через CriptoYa (прямой API 403) |
| kucoinp2p | 1.04 | — | |
| buenbit | 1.0412 | 1.0149 | |
| fiwind | 1.046 | 1.036 | вывод USDT→USD на банковский счёт |
| satoshitango | 1.0482 | 1.0159 | |
| nexo | 1.0492 | 1.0307 | |
| belo | 1.051 | 1.036 | |
| decrypto | 1.0517 | 0.9944 | |
| tiendacrypto | 1.057 | 1.02 | |
| okexp2p | 1.06 | 1.031 | OKX P2P, виден через CriptoYa (прямой API 404) |
| ripio | 1.0603 | 1.0386 | |
| letsbit | 1.0675 | 1.0098 | «dólar cable» — вывод в США |

Примечание: у binancep2p bid > ask (1.0333 > 1.023) — так отдаёт сам агрегат; использовать totalAsk/totalBid по правилу «лучшая цена», как мы уже делаем для USDT/ARS.

## Безнал: BestChange Wire USD (живые топ-5 из 59)

USDT TRC20 → банковский перевод USD (`tether-trc20-to-wire-usd.html`), курс = сколько USDT отдаёшь за 1 USD:

| # | Обменник | Курс | Мин | Макс | Резерв |
|---|---|---|---|---|---|
| 1 | Wirebit | 1.007 USDT/USD | 5 000 | 3 000 000 | 3.5 млн USD |
| 2 | Payex24 | 1.0141 | 2 029 | 1 014 124 | 414 тыс. |
| 3 | ExchangeMafia | 1.015 | 1 000 | 101 500 | 100 тыс. |
| 4 | DimmarEx | 1.0171 | 1 028 | 1 027 241 | 1 млн |
| 5 | Unomoney | 1.0171 | 20 000 | 1 000 000 | 1.5 млн |

Обратное направление USD-wire → USDT: 13 обменников. Оба направления парсятся нашим существующим парсером BestChange (проверено). Ограничение: BestChange не фильтрует по стране получателя перевода; применимость к аргентинским USD-счетам зависит от конкретного обменника.

## Безнал: Bybit P2P напрямую

`POST https://api2.bybit.com/fiat/otc/item/online` {tokenId: USDT, currencyId: USD}:
- продажа USDT (пользователь покупает): **914 объявлений**, лучшие от **1.030 USD/USDT** (экстремумы до 1.20 — OTC-мусор);
- покупка USDT (пользователь продаёт): **522 объявления**, до **1.000 USD/USDT**.
Методы оплаты отдаются числовыми кодами без публичного маппинга — в веб-интерфейсе это безналичные способы. В наш бот Bybit P2P уже приходит через CriptoYa (для ARS); для USD направления у CriptoYa bybit отсутствует.

## Наличные

### Площадки
- **BestChange**: направлений с Cash USD не существует (301: `tether-trc20-to-cash-usd`, все варианты слагов). City-фильтр Буэнос-Айрес (city=214) существует только для Cash ARS.
- **P2P-биржи**: Binance/OKX P2P наличный USD в Аргентине через API не верифицируется (блокировки); на Bybit методы не расшифровываются.

### Расчётный наличный курс (двухшаговый кросс через blue)

Формулы: `купить USDT = USDT/ARS(best ask) ÷ blue(скупка USD)`; `продать USDT = USDT/ARS(best bid) ÷ blue(продажа USD)`.

Живой расчёт 21.09.2026 (mexcp2p ask 1593.25, satoshitango bid 1595.41; blue 1517/1550):
- купить 1 USDT ≈ **1.0503 USD наличными** (+5.0%)
- продать 1 USDT ≈ **1.0293 USD наличными** (+2.9%)
- спред ≈ 2.1%

### Cuevas (прямой наличный рынок, офлайн)

Прямая сделка в cuevas выгоднее двухшаговой: типичная комиссия **2–3%** от курса. Упомянутые сообществом точки CABA (r/argentina, r/merval, r/BuenosAires): DolarOk / Cambio Baires (~3%), PRJ (Palermo/Belgrano/Microcentro), Mais Brazucas (cala Florida), Bitcomtxm (Florida), caja_crypto (Sarmiento y Reconquista, покупает USDT −2.5%), обменники при ювелирных магазинах (Caesar's Palace, Morón). Онлайн-котировок нет — курс по телефону/WhatsApp. Как источник для бота непригодны; для `/how`-гайда — да, с ориентировкой «blue ± 3%».

## Рекомендация по интеграции в бота

1. **Экран `/usdtusd`**: таблица CriptoYa USDT/USD (лучшая покупка/продажа из 16 площадок, наши `totalAsk/totalBid`-правила) + расчётный наличный кросс через blue + подсказка про cuevas (2–3%). Источник и рендер уже есть — нужен только новый эндпоинт-параметр.
2. **BestChange**: добавить 2 направления в `/bestchange` — `usdt_wire_usd` и `wire_usd_usdt` (слаги проверены, парсер совместим).
3. Bybit P2P USDT/USD напрямую — не нужен: площадки-агрегаты уже видны через CriptoYa.

## Источники

- CriptoYa API: `https://criptoya.com/api/USDT/USD`, `/api/USDT/ARS/1000` (живые, 21.09.2026)
- BestChange: `https://www.bestchange.com/tether-trc20-to-wire-usd.html` (59 строк), `wire-usd-to-tether-trc20.html` (13)
- Bybit: `https://api2.bybit.com/fiat/otc/item/online` (USD, 914/522 объявлений)
- Bluelytics: `https://api.bluelytics.com.ar/v2/latest` (blue 1517/1550)
- Bitso: `https://api.bitso.com/v3/ticker/` (usd_ars есть, usdt_usd — нет)
- Рыночный цвет по cuevas: reddit.com/r/merval (Cueva de venta USDT a USD), r/argentina, r/BuenosAires
