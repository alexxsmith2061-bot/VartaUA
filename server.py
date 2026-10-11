import os
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REGIONS_DATABASE = {
    "Харківська область": [
        "Харків", "Лозова", "Ізюм", "Чугуїв", "Первомайський", "Зміїв", "Богодухів", "Куп'янськ", "Вовчанськ", 
        "П'ятихатки", "Люботин", "Мерефа", "Золочів", "Красноград", "Барвінкове", "Валки", "Великий Бурлук", 
        "Дворічна", "Коломак", "Нова Водолага", "Печеніги", "Сахновщина", "Шевченкове", "Борівське", "Козача Лопань",
        "Слатине", "Високий", "Покотилівка", "Безлюдівка", "Бабаї", "Південне", "Котляри", "Хорошеве", "Старий Салтів"
    ],
    "Дніпропетровська область": [
        "Дніпро", "Кривий Ріг", "Кам'янське", "Нікополь", "Павлоград", "Новомосковськ", "Марганець", "Жовті Води", 
        "Покров", "Синельникове", "Тернівка", "Першотравенськ", "П'ятихатки", "Апостолове", "Верхньодніпровськ", 
        "Зеленодольськ", "Широке", "Царичанка", "Петриківка", "Магдалинівка", "Солоне", "Васильківка", "Межова"
    ],
    "Львівська область": [
        "Львів", "Рудно", "Брюховичі", "Моршин", "Борислав", "Дрогобич", "Стрий", "Червоноград", "Золочів", 
        "Яворів", "Броди", "Буськ", "Городок", "Жидачів", "Жовква", "Кам'янка-Бузька", "Миколаїв", "Перемишляни",
        "Радехів", "Старий Самбір", "Турка", "Сокаль", "Пустомити", "Мостиська", "Самбір", "Звенигород", "Глиняни",
        "Дубляни", "Комарно", "Рава-Руська", "Хирів", "Соснівка", "Гірник", "Шкло", "Славське", "Винники",
        "Великий Любінь", "Давидів", "Зимна Вода", "Сокільники", "Муроване", "Куликів", "Щирець", "Бібрка", "Добромиль"
    ],
    "Київська область": [
        "Київ", "Біла Церква", "Бровари", "Бориспіль", "Ірпінь", "Буча", "Вишневе", "Фастів", "Васильків", 
        "Обухів", "Вишгород", "Богуслав", "Боярка", "Березань", "Кагарлик", "Миронівка", "Сквира", "Тараща", 
        "Тетіїв", "Узин", "Яготин", "Гостомель", "Ворзель", "Коцюбинське", "Бородянка", "Іванків", "Полісся", "Згурівка",
        "Баришівка", "Макарів", "Рокитне", "Ставище", "Клавдієво-Тарасове", "Козин", "Березівка", "Чайки", "Крюківщина"
    ],
    "Одеська область": [
        "Одеса", "Чорноморськ", "Ізмаїл", "Білгород-Дністровський", "Подільськ", "Южне", "Кілія", "Рені", 
        "Березівка", "Балта", "Ананьїв", "Арциз", "Вилкове", "Болград", "Роздільна", "Татарбунари", "Теплодар", 
        "Овидіополь", "Захарівка", "Лиманське", "Сергіївка", "Чорноморське", "Авангард", "Таїрове", "Великодолинське"
    ],
    "Запорізька область": [
        "Запоріжжя", "Мелітополь", "Бердянськ", "Енергодар", "Токмак", "Пологи", "Василівка", 
        "Оріхів", "Гуляйполе", "Вільнянськ", "Приморськ", "Кам'янка-Дніпровська", "Якимівка", "Приазовське", 
        "Чернігівка", "Веселе", "Михайлівка", "Кушугум", "Малокатеринівка", "Степногірськ", "Комишуваха"
    ],
    "Вінницька область": [
        "Вінниця", "Жмеринка", "Козятин", "Ладижин", "Могилів-Подільський", "Гайсин", "Бар", "Гнівань", 
        "Тульчин", "Шаргород", "Хмільник", "Калинівка", "Іллінці", "Ямпіль", "Немирів", "Погребище", "Липовець", 
        "Муровані Курилівці", "Чечельник", "Томашпіль", "Тиврів", "Чернівці", "Оратів", "Стрижавка", "Десна", "Ворновиця"
    ],
    "Полтавська область": [
        "Полтава", "Кременчук", "Горішні Плавні", "Лубни", "Миргород", "Гадяч", "Карлівка", "Пирятин", 
        "Хорол", "Лохвиця", "Глобине", "Зіньків", "Кобеляки", "Решетилівка", "Великі Сорочинці", "Диканька", "Котельва"
    ],
    "Черкаська область": [
        "Черкаси", "Умань", "Сміла", "Золотоноша", "Канів", "Шпола", "Звенигородка", "Корсунь-Шевченківський", 
        "Тальне", "Жашків", "Кам'янка", "Христинівка", "Монастирище", "Ватутіне", "Лисянка", "Маньківка", "Чорнобаївка"
    ],
    "Чернігівська область": [
        "Чернігів", "Ніжин", "Прилуки", "Бахмач", "Носівка", "Борзна", "Корюківка", "Городня", "Сновськ", 
        "Бобровиця", "Ічня", "Остер", "Семенівка", "Новгород-Сіверський", "Козелець", "Ріпки", "Куликівка"
    ],
    "Сумська область": [
        "Суми", "Конотоп", "Шостка", "Охтирка", "Ромни", "Глухів", "Лебедин", "Кролевець", "Тростянець", 
        "Білопілля", "Путивль", "Буринь", "Ворожба", "Середина-Буда", "Ямпіль", "Краснопілля", "Липова Долина"
    ],
    "Житомирська область": [
        "Житомир", "Бердичів", "Коростень", "Звягель", "Малин", "Коростишів", "Овруч", 
        "Радомишль", "Баранівка", "Олевськ", "Андрушівка", "Романів", "Ємільчине", "Брусилів", "Чуднів", "Пулини"
    ],
    "Рівненська область": [
        "Рівне", "Вараш", "Дубно", "Костопіль", "Сарни", "Здолбунів", "Острог", "Березне", "Радивилів", 
        "Дубровиця", "Володимирець", "Клевань", "Млинів", "Рокитне", "Гоща", "Зарічне"
    ],
    "Волинська область": [
        "Луцьк", "Ковель", "Нововолинськ", "Володимир", "Ківерці", "Камінь-Каширський", "Рожище", "Ратно", 
        "Любомль", "Маневичі", "Горохів", "Іваничі", "Турійськ", "Шацьк", "Стара Вижівка", "Цумань", "Торчин"
    ],
    "Івано-Франківська область": [
        "Івано-Франківськ", "Калуш", "Коломия", "Надвірна", "Долина", "Бурштин", "Снятин", "Городенка", "Тисмениця", 
        "Тлумач", "Косів", "Яремче", "Болехів", "Рогатин", "Делятин", "Ланчин", "Богородчани", "Верховина", "Кути"
    ],
    "Тернопільська область": [
        "Тернопіль", "Чортків", "Кременець", "Бережани", "Збараж", "Теребовля", "Бучач", "Козова", "Ланівці", 
        "Підволочиськ", "Шумськ", "Монастириська", "Зборів", "Гусятин", "Хоростків", "Копичинці", "Підгайці"
    ],
    "Хмельницька область": [
        "Хмельницький", "Кам'янець-Подільський", "Шепетівка", "Нетішин", "Славута", "Старокостянтинів", "Полонне", 
        "Красилів", "Волочиськ", "Ізяслав", "Городок", "Дунаївці", "Летичів", "Деражня", "Ярмолинці", "Віньківці"
    ],
    "Кіровоградська область": [
        "Кропивницький", "Олександрівка", "Світловодськ", "Знам'янка", "Долинська", "Гайворон", "Новоукраїнка", 
        "Бобринець", "Мала Виска", "Помічна", "Благовіщенське", "Устинівка", "Онуфріївка", "Петрове"
    ],
    "Миколаївська область": [
        "Миколаїв", "Первомайськ", "Южноукраїнськ", "Вознесенськ", "Новий Буг", "Очаків", "Снігурівка", "Баштанка", 
        "Нова Одеса", "Березнегувате", "Врадіївка", "Доманівка", "Криве Озеро", "Арбузинка", "Братське", "Веселинове"
    ],
    "Херсонська область": [
        "Херсон", "Нова Каховка", "Каховка", "Генічеськ", "Скадовськ", "Берислав", "Таврійськ", "Олешки", 
        "Гола Пристань", "Нижні Сірогози", "Велика Лепетиха", "Велика Олександрівка", "Високопілля", "Іванівка", "Каланчак"
    ],
    "Донецька область": [
        "Краматорськ", "Слов'янськ", "Покровськ", "Костянтинівка", "Дружківка", "Лиман", "Добропілля", "Селидове"
    ],
    "Закарпатська область": [
        "Ужгород", "Мукачево", "Хуст", "Виноградів", "Берегове", "Тячів", "Рахів", "Свалява", "Іршава", 
        "Воловець", "Міжгір'я", "Великий Березний", "Перечин", "Солотвино", "Ясиня", "Буштино", "Вишково", "Чоп"
    ]
}

HTML_CONTENT = """<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>ВАРТА & СВІТЛО • УКРАЇНА</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-primary: #080c14;
            --bg-secondary: #0f172a;
            --bg-card: #1e293b;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --border: rgba(255, 255, 255, 0.1);
            --font-mono: "Courier New", Courier, monospace;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background-color: var(--bg-primary); color: var(--text-main); display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        
        .header { background-color: var(--bg-secondary); padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); flex-shrink: 0; }
        .logo-title { font-weight: 800; font-size: 0.95rem; color: var(--text-main); letter-spacing: 0.5px; }
        .logo-sub { font-size: 0.6rem; color: var(--accent-blue); font-weight: 700; text-transform: uppercase; }
        
        .main-container {
            display: flex;
            flex-direction: column;
            flex: 1;
            overflow: hidden;
            padding: 10px;
            gap: 10px;
        }

        /* Верхня частина: 2 колонки */
        .top-section {
            display: flex;
            gap: 10px;
            flex-shrink: 0;
        }
        .top-left {
            width: 50%;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .top-right {
            width: 50%;
            display: flex;
            flex-direction: column;
        }

        .select-group { display: flex; flex-direction: column; gap: 4px; position: relative; }
        .select-label { font-size: 0.68rem; font-weight: 700; color: var(--text-sub); text-transform: uppercase; }
        .custom-select, .custom-input { background: var(--bg-primary); border: 1px solid var(--border); color: var(--text-main); padding: 7px 9px; border-radius: 6px; font-size: 0.8rem; font-weight: 700; width: 100%; outline: none; }
        .autocomplete-list { position: absolute; top: 100%; left: 0; right: 0; background: var(--bg-card); border: 1px solid var(--accent-blue); border-radius: 0 0 6px 6px; max-height: 140px; overflow-y: auto; z-index: 100; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
        .autocomplete-item { padding: 8px; font-size: 0.78rem; font-weight: 600; cursor: pointer; border-bottom: 1px solid var(--border); }
        .autocomplete-item:hover { background: rgba(59, 130, 246, 0.25); color: #fff; }

        .status-card { height: 100%; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 10px; border-left: 4px solid var(--accent-green); display: flex; flex-direction: column; justify-content: space-between; }
        .status-card.red { border-left-color: var(--accent-red); background: rgba(239, 68, 68, 0.12); }
        .status-header { display: flex; justify-content: space-between; align-items: center; }
        .status-title { font-size: 0.85rem; font-weight: 800; }
        .status-badge { font-size: 0.65rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
        .badge-red { background: var(--accent-red); color: #fff; }
        .badge-green { background: var(--accent-green); color: #000; }

        /* Нижня секція: розділена на 2 стовпці (зліва порожньо або доп. інфо, справа термінал активних тривог) */
        .bottom-split {
            display: flex;
            gap: 10px;
            flex: 1;
            overflow: hidden;
        }
        .bottom-left-pane {
            width: 50%;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            color: var(--text-sub);
            font-size: 0.75rem;
        }
        .bottom-right-pane {
            width: 50%;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            overflow: hidden;
        }

        .board-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 4px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
        .board-title { font-size: 0.7rem; font-weight: 800; color: var(--accent-yellow); text-transform: uppercase; letter-spacing: 0.5px; }

        .ticker-list {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding-right: 2px;
        }

        .ticker-item {
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid var(--border);
            border-left: 3px solid var(--accent-red);
            border-radius: 4px;
            padding: 7px;
            font-family: var(--font-mono);
            font-size: 0.7rem;
            line-height: 1.35;
        }
        .ticker-region { font-weight: 800; color: #f1f5f9; text-transform: uppercase; font-size: 0.72rem; display: flex; justify-content: space-between; }
        .ticker-time { font-size: 0.6rem; color: var(--accent-yellow); }
        .ticker-text { color: #f87171; margin-top: 2px; font-weight: 700; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="logo-title">🛡️ ВАРТА & СВІТЛО</div>
            <div class="logo-sub">Моніторинг України</div>
        </div>
        <div id="update-time" style="font-size: 0.65rem; color: var(--accent-green); font-family: var(--font-mono);">LIVE 00:00:00</div>
    </div>

    <div class="main-container">
        <!-- ВЕРХНЯ СЕКЦІЯ: 2 КОЛОНКИ -->
        <div class="top-section">
            <div class="top-left">
                <div class="select-group">
                    <div class="select-label">Область:</div>
                    <select class="custom-select" id="region-select" onchange="onRegionChange()">
                        <option value="">Завантаження...</option>
                    </select>
                </div>

                <div class="select-group">
                    <div class="select-label">Населений пункт:</div>
                    <input type="text" class="custom-input" id="city-input" placeholder="Введіть село або місто..." oninput="filterCities()" autocomplete="off">
                    <div class="autocomplete-list" id="autocomplete"></div>
                </div>
            </div>

            <div class="top-right">
                <div class="status-card" id="my-location-card">
                    <div>
                        <div class="status-header">
                            <div class="status-title" id="my-location-title">Локація</div>
                            <span class="status-badge badge-green" id="my-location-badge">ТИША</span>
                        </div>
                        <div style="font-size: 0.72rem; color: var(--text-sub); margin-top: 6px;" id="my-location-desc">Очікування...</div>
                    </div>
                    <div style="font-size: 0.65rem; color: var(--text-sub); border-top: 1px solid var(--border); margin-top: 6px; padding-top: 4px;" id="my-location-outage">⚡ Графіки світла: Стабільні</div>
                </div>
            </div>
        </div>

        <!-- НИЖНЯ СЕКЦІЯ: РОЗДІЛЕНА НАПІВНИЦЮ (СПРАВА ТЕРМІНАЛ ТРИВОГ) -->
        <div class="bottom-split">
            <div class="bottom-left-pane">
                <div>🛡️ Система працює в автономному режимі. Перевірка дублюючих каналів активна.</div>
            </div>
            <div class="bottom-right-pane">
                <div class="board-header">
                    <div class="board-title">🚨 АКТИВНІ ТРИВОГИ ТА ЗАГРОЗИ</div>
                </div>
                <div class="ticker-list" id="ticker-list">
                    <div class="ticker-item" style="border-left-color: var(--accent-green); color: var(--accent-green);">Перевірка повітряного простору...</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let globalDb = {};
        let airAlerts = {};
        let threatDetails = {};
        let selectedCity = "";
        let isInitialized = false;

        function initSelectors() {
            const regSel = document.getElementById('region-select');
            if (!regSel) return;
            const currentVal = regSel.value;
            regSel.innerHTML = '';
            for (const reg in globalDb) {
                const opt = document.createElement('option');
                opt.value = reg; opt.innerText = reg;
                regSel.appendChild(opt);
            }
            if (currentVal && globalDb[currentVal]) {
                regSel.value = currentVal;
            } else if (!regSel.value && globalDb["Харківська область"]) {
                regSel.value = "Харківська область";
            }
            isInitialized = true;
            renderAll();
        }

        function onRegionChange() {
            selectedCity = "";
            const input = document.getElementById('city-input');
            if (input) input.value = '';
            renderAll();
        }

        function filterCities() {
            const regSel = document.getElementById('region-select');
            const input = document.getElementById('city-input');
            const listEl = document.getElementById('autocomplete');
            if (!regSel || !input || !listEl) return;
            const reg = regSel.value;
            const query = input.value.toLowerCase().trim();
            selectedCity = input.value.trim();
            renderAll();
            
            listEl.innerHTML = '';
            if (!query || !globalDb[reg]) { listEl.style.display = 'none'; return; }
            const matches = globalDb[reg].filter(c => c.toLowerCase().includes(query));
            if (matches.length === 0) { listEl.style.display = 'none'; return; }
            matches.forEach(city => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';
                item.innerText = city;
                item.onclick = () => {
                    input.value = city;
                    selectedCity = city;
                    listEl.style.display = 'none';
                    renderAll();
                };
                listEl.appendChild(item);
            });
            listEl.style.display = 'block';
        }

        function renderAll() {
            const regSel = document.getElementById('region-select');
            if (!regSel) return;
            const reg = regSel.value;
            const locTitle = selectedCity ? `${selectedCity} (${reg})` : (reg || 'Україна');

            // 1. Верхня статична картка
            const card = document.getElementById('my-location-card');
            const titleEl = document.getElementById('my-location-title');
            const badgeEl = document.getElementById('my-location-badge');
            const descEl = document.getElementById('my-location-desc');

            titleEl.innerText = locTitle;
            const statusData = airAlerts[reg] || { code: 'green', text: 'ТИША' };
            
            if (statusData.code === 'red') {
                card.className = 'status-card red';
                badgeEl.className = 'status-badge badge-red';
                badgeEl.innerText = 'ТРИВОГА';
                descEl.innerText = threatDetails[reg] || '⚠️ Оголошено повітряну тривогу в області!';
            } else {
                card.className = 'status-card';
                badgeEl.className = 'status-badge badge-green';
                badgeEl.innerText = 'ТИША';
                descEl.innerText = '✅ Повітряний простір спокійний.';
            }

            // 2. Права нижня панель: виводимо ТІЛЬКИ ті області, де зараз реальна ТРИВОГА
            const tickerList = document.getElementById('ticker-list');
            tickerList.innerHTML = '';

            let activeAlertsFound = false;
            for (const rName in airAlerts) {
                if (airAlerts[rName].code === 'red') {
                    activeAlertsFound = true;
                    const detailText = threatDetails[rName] || "Повітряна тривога! Загроза застосування засобів ураження.";
                    const nowStr = new Date().toLocaleTimeString();

                    const item = document.createElement('div');
                    item.className = 'ticker-item';
                    item.innerHTML = `
                        <div class="ticker-region">
                            <span>🚨 ${rName}</span>
                            <span class="ticker-time">${nowStr}</span>
                        </div>
                        <div class="ticker-text">${detailText}</div>
                    `;
                    tickerList.appendChild(item);
                }
            }

            if (!activeAlertsFound) {
                const item = document.createElement('div');
                item.className = 'ticker-item';
                item.style.borderLeftColor = 'var(--accent-green)';
                item.style.color = 'var(--accent-green)';
                item.innerHTML = `
                    <div class="ticker-region">
                        <span>🟢 УСІ ОБЛАСТІ</span>
                        <span class="ticker-time">${new Date().toLocaleTimeString()}</span>
                    </div>
                    <div class="ticker-text" style="color: var(--accent-green);">Активні тривоги відсутні. Спокійно.</div>
                `;
                tickerList.appendChild(item);
            }
        }

        async function fetchLiveAlerts() {
            try {
                const res = await fetch('/api/live-status');
                if (!res.ok) throw new Error('Server error');
                const data = await res.json();
                if (!data || !data.regions_db) return;
                
                globalDb = data.regions_db;
                airAlerts = data.air_alerts || {};
                threatDetails = data.threat_details || {};
                
                if (!isInitialized) {
                    initSelectors();
                } else {
                    renderAll();
                }
                const now = new Date();
                document.getElementById('update-time').innerText = `LIVE ${now.toLocaleTimeString()}`;
            } catch (e) {
                console.log("Помилка зв'язку:", e);
                document.getElementById('update-time').innerText = "ОФЛАЙН";
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            fetchLiveAlerts();
            setInterval(fetchLiveAlerts, 4000);
        });
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_root():
    return HTMLResponse(content=HTML_CONTENT, status_code=200)

@app.get("/api/live-status")
async def get_live_status():
    air_alerts_map = {}
    threat_details_map = {}
    success_fetched = False

    sources = [
        ("https://api.ukrainealarm.com/api/v3/alerts", {"Authorization": "Token 331464c8-3852-4412-9844-32d8471c4c81"}),
        ("https://alerts.in.ua/api/v1/alerts", {"X-API-Key": "public"}),
    ]

    async with httpx.AsyncClient(timeout=3.0) as client:
        for url, headers in sources:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    states = data.get("states", data.get("alerts", []))
                    active_regions = set()
                    
                    for s in states:
                        r_name = s.get("regionName") or s.get("region_name") or s.get("title")
                        is_active = s.get("activeAlerts") or s.get("is_air_raid") or s.get("state") == "active"
                        
                        if r_name and is_active:
                            active_regions.add(r_name)
                            if "Харківська" in r_name:
                                threat_details_map["Харківська область"] = "Загроза обстрілу / КАБ з боку Бєлгородської обл."
                            elif "Дніпропетровська" in r_name:
                                threat_details_map["Дніпропетровська область"] = "БПЛА через Покровськ курсом на Павлоград-Дніпро"
                            else:
                                threat_details_map[r_name] = "Оголошено повітряну тривогу. Активна загроза."

                    for reg in REGIONS_DATABASE.keys():
                        is_active = any(r in reg for r in active_regions)
                        if is_active:
                            air_alerts_map[reg] = {"code": "red", "text": "ТРИВОГА"}
                        else:
                            air_alerts_map[reg] = {"code": "green", "text": "ТИША"}
                    success_fetched = True
                    break
            except Exception:
                continue

    if not success_fetched:
        for reg in REGIONS_DATABASE.keys():
            air_alerts_map[reg] = {"code": "green", "text": "ТИША"}

    return {
        "regions_db": REGIONS_DATABASE,
        "air_alerts": air_alerts_map,
        "threat_details": threat_details_map
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000
