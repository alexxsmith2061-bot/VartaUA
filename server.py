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
    "Харківська область": [
        "Харків", "Лозова", "Ізюм", "Чугуїв", "Первомайський", "Зміїв", "Богодухів", "Куп'янськ", "Вовчанськ", 
        "П'ятихатки", "Люботин", "Мерефа", "Золочів", "Красноград", "Барвінкове", "Валки", "Великий Бурлук", 
        "Дворічна", "Коломак", "Нова Водолага", "Печеніги", "Сахновщина", "Шевченкове", "Борівське", "Козача Лопань",
        "Слатине", "Високий", "Покотилівка", "Безлюдівка", "Бабаї", "Південне", "Котляри", "Хорошеве", "Старий Салтів"
    ],
    "Одеська область": [
        "Одеса", "Чорноморськ", "Ізмаїл", "Білгород-Дністровський", "Подільськ", "Южне", "Кілія", "Рені", 
        "Березівка", "Балта", "Ананьїв", "Арциз", "Вилкове", "Болград", "Роздільна", "Татарбунари", "Теплодар", 
        "Овидіополь", "Захарівка", "Лиманське", "Сергіївка", "Чорноморське", "Авангард", "Таїрове", "Великодолинське"
    ],
    "Дніпропетровська область": [
        "Дніпро", "Кривий Ріг", "Кам'янське", "Нікополь", "Павлоград", "Новомосковськ", "Марганець", "Жовті Води", 
        "Покров", "Синельникове", "Тернівка", "Першотравенськ", "П'ятихатки", "Апостолове", "Верхньодніпровськ", 
        "Зеленодольськ", "Широке", "Царичанка", "Петриківка", "Магдалинівка", "Солоне", "Васильківка", "Межова"
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
        "Маріуполь", "Краматорськ", "Слов'янськ", "Бахмут", "Макіївка", "Горлівка", "Єнакієве", "Торецьк", 
        "Покровськ", "Костянтинівка", "Дружківка", "Лиман", "Добропілля", "Селидове", "Вугледар", "Мар'їнка", "Волноваха"
    ],
    "Луганська область": [
        "Луганськ", "Алчевськ", "Сєвєродонецьк", "Лисичанськ", "Рубіжне", "Красний Луч", "Свердловськ", "Стаханов", 
        "Антрацит", "Ровеньки", "Кремінна", "Сватове", "Старобільськ", "Щастя", "Попасна", "Гірське", "Троїцьке"
    ],
    "Республіка Крим": [
        "Сімферополь", "Севастополь", "Керч", "Євпаторія", "Ялта", "Феодосія", "Джанкой", "Красноперекопськ", 
        "Алушта", "Бахчисарай", "Саки", "Армянськ", "Судак", "Білогірськ", "Кіровське", "Чорноморське"
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
            --bg-primary: #0b0f19;
            --bg-secondary: #151c2c;
            --bg-card: #1e293b;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --accent-green: #10b981;
            --accent-blue: #3b82f6;
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
            --border: rgba(255, 255, 255, 0.1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; -webkit-tap-highlight-color: transparent; }
        body { background-color: var(--bg-primary); color: var(--text-main); display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        .header { background-color: var(--bg-secondary); padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
        .logo-title { font-weight: 800; font-size: 0.95rem; color: var(--text-main); }
        .logo-sub { font-size: 0.6rem; color: var(--accent-blue); font-weight: 700; text-transform: uppercase; }
        
        /* Двоколоночний макет на весь екран */
        .dashboard-grid {
            display: flex;
            flex: 1;
            height: calc(100vh - 45px);
            overflow: hidden;
        }
        .column-left {
            width: 50%;
            background-color: var(--bg-secondary);
            border-right: 1px solid var(--border);
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            overflow-y: auto;
        }
        .column-right {
            width: 50%;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            overflow-y: auto;
            background-color: var(--bg-primary);
        }

        .search-box { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 10px; display: flex; flex-direction: column; gap: 8px; position: relative; }
        .select-group { display: flex; flex-direction: column; gap: 4px; position: relative; }
        .select-label { font-size: 0.7rem; font-weight: 700; color: var(--text-sub); text-transform: uppercase; }
        .custom-select, .custom-input { background: var(--bg-primary); border: 1px solid var(--border); color: var(--text-main); padding: 9px; border-radius: 6px; font-size: 0.8rem; font-weight: 700; width: 100%; outline: none; }
        .autocomplete-list { position: absolute; top: 100%; left: 0; right: 0; background: var(--bg-card); border: 1px solid var(--accent-blue); border-radius: 0 0 6px 6px; max-height: 150px; overflow-y: auto; z-index: 100; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
        .autocomplete-item { padding: 8px 10px; font-size: 0.78rem; font-weight: 600; cursor: pointer; border-bottom: 1px solid var(--border); }
        .autocomplete-item:hover { background: rgba(59, 130, 246, 0.25); color: #fff; }

        .result-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 12px; border-left: 4px solid var(--accent-green); transition: all 0.3s ease; }
        .result-card.red { border-left-color: var(--accent-red); background: rgba(239, 68, 68, 0.08); }
        .result-card.yellow { border-left-color: var(--accent-yellow); background: rgba(245, 158, 11, 0.08); }
        
        .res-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
        .res-title { font-size: 0.85rem; font-weight: 800; color: #f1f5f9; }
        .res-badge { font-size: 0.6rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
        .code-red-tag { background: var(--accent-red); color: #fff; }
        .code-green-tag { background: var(--accent-green); color: #000; }
        .code-yellow-tag { background: var(--accent-yellow); color: #000; }
        .res-desc { font-size: 0.75rem; color: var(--text-sub); line-height: 1.35; margin-top: 4px; }

        @media (max-width: 768px) {
            .dashboard-grid { flex-direction: column; }
            .column-left, .column-right { width: 100%; height: auto; overflow: visible; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="logo-title">🛡️ ВАРТА & СВІТЛО</div>
            <div class="logo-sub">Моніторинг України</div>
        </div>
        <div id="update-time" style="font-size: 0.6rem; color: var(--text-sub);">З'єднання...</div>
    </div>

    <div class="dashboard-grid">
        <!-- ЛІВА КОЛОНКА: Вибір області та міста -->
        <div class="column-left">
            <div class="search-box">
                <div style="font-size: 0.78rem; font-weight: 800; color: var(--accent-blue);">📍 Параметри пошуку</div>
                
                <div class="select-group">
                    <div class="select-label">1. Область</div>
                    <select class="custom-select" id="region-select" onchange="onRegionChange()">
                        <option value="">Завантаження областей...</option>
                    </select>
                </div>

                <div class="select-group">
                    <div class="select-label">2. Населений пункт</div>
                    <input type="text" class="custom-input" id="city-input" placeholder="Введіть село чи місто..." oninput="filterCities()" autocomplete="off">
                    <div class="autocomplete-list" id="autocomplete"></div>
                </div>
            </div>
        </div>

        <!-- ПРАВА КОЛОНКА: Статус тривог та графіки світла -->
        <div class="column-right">
            <!-- Картка повітряного моніторингу -->
            <div class="result-card" id="air-result-card">
                <div class="res-top">
                    <div class="res-title" id="air-res-title">Повітряний монітор</div>
                    <span class="res-badge code-green-tag" id="air-res-badge">ТИША</span>
                </div>
                <div class="res-desc" id="air-res-desc">Очікування вибору локації...</div>
            </div>

            <!-- Картка графіків відключення світла -->
            <div class="result-card yellow" id="out-result-card" style="border-left-color: var(--accent-yellow);">
                <div class="res-top">
                    <div class="res-title" id="out-res-title">Графіки світла</div>
                    <span class="res-badge code-yellow-tag" id="out-res-badge">ПЛАН</span>
                </div>
                <div class="res-desc" id="out-res-desc">Стабілізаційні графіки за оперативними планами.</div>
            </div>
        </div>
    </div>

    <script>
        let globalDb = {};
        let airAlerts = {};
        let outageStatuses = {};
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
            if (currentVal && globalDb[currentVal]) regSel.value = currentVal;
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
            const locationName = selectedCity ? `${selectedCity} (${reg})` : (reg || 'Україна');

            // Рендер повітряного монітора
            const airCard = document.getElementById('air-result-card');
            const airTitle = document.getElementById('air-res-title');
            const airBadge = document.getElementById('air-res-badge');
            const airDesc = document.getElementById('air-res-desc');
            
            airTitle.innerText = locationName;
            const alertData = airAlerts[reg] || { code: 'green', text: 'ТИША', detail: 'Повітряна тривога відсутня.' };
            
            if (alertData.code === 'red') {
                airCard.className = 'result-card red';
                airBadge.className = 'res-badge code-red-tag';
                airBadge.innerText = alertData.text;
            } else {
                airCard.className = 'result-card';
                airBadge.className = 'res-badge code-green-tag';
                airBadge.innerText = alertData.text;
            }
            airDesc.innerHTML = `📡 Статус: <b>${alertData.detail}</b>`;

            // Рендер графіків світла
            const outDesc = document.getElementById('out-res-desc');
            const outageText = outageStatuses[reg] || "Діють стабілізаційні графіки відключень.";
            outDesc.innerHTML = `⚡ Статус: <b>${outageText}</b>`;
        }

        async function fetchLiveAlerts() {
            try {
                const res = await fetch('/api/live-status');
                if (!res.ok) throw new Error('Server error');
                const data = await res.json();
                if (!data || !data.regions_db) return;
                
                globalDb = data.regions_db;
                airAlerts = data.air_alerts || {};
                outageStatuses = data.outages_status || {};
                
                if (!isInitialized) {
                    initSelectors();
                } else {
                    renderAll();
                }
                const now = new Date();
                document.getElementById('update-time').innerText = `Оновлено: ${now.toLocaleTimeString()}`;
            } catch (e) {
                console.log("Помилка зв'язку:", e);
                document.getElementById('update-time').innerText = "Помилка зв'язку";
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

                    for reg in REGIONS_DATABASE.keys():
                        is_active = any(r in reg for r in active_regions)
                        if is_active:
                            air_alerts_map[reg] = {
                                "code": "red", 
                                "text": "ТРИВОГА", 
                                "detail": "Оголошено повітряну тривогу!"
                            }
                        else:
                            air_alerts_map[reg] = {
                                "code": "green", 
                                "text": "ТИША", 
                                "detail": "Повітряна тривога відсутня."
                            }
                    success_fetched = True
                    break
            except Exception:
                continue

    if not success_fetched:
        for reg in REGIONS_DATABASE.keys():
            air_alerts_map[reg] = {
                "code": "green", 
                "text": "ТИША", 
                "detail": "Повітряна тривога відсутня."
            }

    outages_map = {reg: "Діють планові стабілізаційні графіки." for reg in REGIONS_DATABASE.keys()}

    return {
        "regions_db": REGIONS_DATABASE,
        "air_alerts": air_alerts_map,
        "outages_status": outages_map
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
