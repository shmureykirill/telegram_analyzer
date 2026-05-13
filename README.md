Шмурей Кирилл Сергеевич 3 курс 6 семестр ИИ-231 Курсовая работа 

Веб-приложение для сбора и анализа Telegram-каналов.  
Работает в двух режимах: **Telethon API** (полные данные) или **HTML-парсер** (без аккаунта).

---

Быстрый старт (PyCharm)

### 1. Открыть проект
`File → Open` → папка `telegram_analyzer`

### 2. Создать виртуальное окружение
`File → Settings → Project → Python Interpreter → ⚙️ → Add → Virtualenv → OK`

### 3. Установить зависимости
```bash
pip install -r requirements.txt
```

### 4. Настроить `.env`
В корне проекта уже есть файл `.env` — открой его и заполни нужные поля:

```env
# ── Telegram API (https://my.telegram.org) ──────────────────
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_PHONE=+79001234567

# ── Google Gemini AI (https://aistudio.google.com/apikey) ───
GEMINI_API_KEY=AIza...

# ── Приложение ───────────────────────────────────────────────
SECRET_KEY=change-me
COLLECT_INTERVAL_MINUTES=30
```

> **Всё необязательно.** Без Telegram API — работает HTML-парсер.  
> Без Gemini — используются правило-базированные обоснования.

### 5. Инициализировать базу данных
```bash
python init_db.py
```
При наличии `TELEGRAM_API_ID` + `TELEGRAM_API_HASH` скрипт запросит номер телефона и код подтверждения из Telegram. Сессия сохранится в `tg_analyzer.session` — повторный вход не нужен.

### 6. Запустить
```bash
python run.py
```

Открой **http://localhost:5000**

---

## 📁 Структура проекта

```
telegram_analyzer/
├── .env                        # ключи API и настройки (не коммитить!)
├── .env.example                # шаблон для .env
├── config/
│   ├── settings.py             # центральный загрузчик настроек из .env
│   ├── channels.json           # начальный список каналов
│   └── topics.json             # словарь тем с ключевыми словами
├── database/
│   ├── models.py               # DDL схема + миграции ALTER TABLE
│   └── db.py                   # все SQL-запросы
├── scraper/
│   ├── telethon_client.py      # сборщик через Telethon API (полные данные)
│   ├── parser.py               # HTML-парсер t.me/s/ (fallback)
│   └── collector.py            # оркестратор: выбирает Telethon или HTML
├── nlp/
│   ├── preprocessor.py         # очистка текста, токенизация
│   ├── keywords.py             # ключевые слова и n-граммы
│   ├── topics.py               # словарная классификация по темам
│   └── sentiment.py            # анализ тональности (словарь + эмодзи)
├── prediction/
│   ├── trends.py               # прогноз трендов по последним сообщениям
│   └── ai_reason.py            # Gemini API + OpenAI-совместимый fallback
├── web/
│   ├── app.py                  # Flask-роуты
│   ├── charts.py               # matplotlib → base64 PNG
│   ├── exports.py              # CSV / PDF / Excel
│   └── templates/              # Jinja2-шаблоны
├── init_db.py                  # инициализация БД + Telethon auth
├── run.py                      # точка входа: Flask + APScheduler
└── requirements.txt
```

---

## ✨ Возможности v3

| Функция | Описание |
|---|---|
| **Telethon API** | Полные реакции с эмодзи, репосты, ответы, точные просмотры |
| **HTML-парсер** | Fallback без аккаунта через `t.me/s/username` |
| **Анализ тональности** | Словарь ~600 слов RU+EN + эмодзи-сигналы (🚀=+, 👎=−) |
| **Тренды по сообщениям** | Работают сразу после первого сбора — без ожидания |
| **Линейная регрессия** | Сглаживание динамики просмотров (numpy.polyfit) |
| **Инфлюенсеры** | Каналы со средними просмотрами ≥ 3 000 |
| **Прогноз 24 ч** | Явный горизонт на каждой карточке тренда |
| **Gemini AI** | Текстовое обоснование тренда на русском языке |
| **Emoji-реакции** | Топ-10 по периоду, полная детализация в Excel |
| **История (до 10 000+ msg)** | Telethon: без ограничений; HTML: ~4 000 сообщений |
| **Экспорт** | CSV / PDF / Excel с полями sentiment, reactions_total, reactions_detail |
| **Индикаторы режима** | Шапка показывает активный режим: Telethon / HTML / Gemini |

---

## 🔑 Как получить ключи

### Telegram API
1. Зайди на [my.telegram.org](https://my.telegram.org)
2. Войди со своим номером телефона
3. Выбери **API development tools**
4. Создай приложение → скопируй `api_id` и `api_hash`
5. Вставь в `.env`

### Google Gemini API
1. Зайди на [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Нажми **Create API key**
3. Вставь ключ в `.env` как `GEMINI_API_KEY`
4. Бесплатный тариф: ~1 500 запросов/день — хватает для работы

---

## Что показывает интерфейс

| Страница | Содержимое |
|---|---|
| **Дашборд** | Общая статистика, топ-тренды, распределение тональности |
| **Темы и слова** | Частота тем, топ-50 ключевых слов, биграммы, триграммы, топ эмодзи |
| **Тренды** | Карточки с прогнозом, метриками, тональностью и AI-обоснованием |
| **Интересы** | Тематический профиль каналов, рейтинг по охвату |
| **Каналы** | Управление списком, ручной сбор, глубокий сбор истории |
| **Экспорт** | Скачать CSV / PDF / Excel за любой период |
| **О проекте** | Архитектура, методология, таблица ограничений |

---


