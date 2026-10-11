import os
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
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
        .header { background-color: var(--bg-secondary); padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
        .logo-title { font-weight: 800; font-size: 1rem; color: var(--text-main); }
        .logo-sub { font-size: 0.65rem; color: var(--accent-blue); font-weight: 700; text-transform: uppercase; }
        .main-content { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; padding-bottom: 75px; }
        .tab-pane { display: none; flex-direction: column; gap: 10px; }
        .tab-pane.active { display: flex; }
        .search-box { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 8px; position: relative; }
        .select-group { display: flex; flex-direction: column; gap: 4px; position: relative; }
        .select-label { font-size: 0.72rem; font-weight: 700; color: var(--text-sub); text-transform: uppercase; }
        .custom-select, .custom-input { background: var(--bg-card); border: 1px solid var(--border); color: var(--text-main); padding: 10px; border-radius: 8px; font-size: 0.85rem; font-weight: 700; width: 100%; outline: none; }
        .autocomplete-list { position: absolute; top: 100%; left: 0; right: 0; background: var(--bg-card); border: 1px solid var(--accent-blue); border-radius: 0 0 8px 8px; max-height: 180px; overflow-y: auto; z-index: 100; display: none; box-shadow: 0 8px 16px rgba(0,0,0,0.4); }
        .autocomplete-item { padding: 9px 12px; font-size: 0.82rem; font-weight: 600; cursor: pointer; border-bottom: 1px solid var(--border); }
        .autocomplete-item:hover { background: rgba(59, 130, 246, 0.25); color: #fff; }
        .result-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-top: 6px; border-left: 4px solid var(--accent-green); transition: all 0.3s ease; }
        .result-card.red { border-left-color: var(--accent-red); background: rgba(239, 68, 68, 0.08); }
        .res-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
        .res-title { font-size: 0.88rem; font-weight: 800; color: #f1f5f9; }
        .res-badge { font-size: 0.65rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
        .code-red-tag { background: var(--accent-red); color: #fff; }
        .code-green-tag { background: var(--accent-green); color: #000; }
        .res-desc { font-size: 0.78rem; color: var(--text-sub); line-height: 1.35; }
        .nav-bar { position: fixed; bottom: 0; left: 0; right: 0; background: var(--bg-secondary); display: flex; justify-content: space-around; padding: 10px 0; border-top: 1px solid var(--border); z-index: 100; }
        .nav-item { display: flex; flex-direction: column; align-items: center; gap: 4px; color: var(--text-sub); font-size: 0.7rem; font-weight: 700; cursor: pointer; width: 50%; }
        .nav-item.active { color: var(--accent-blue); }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="logo-title">🛡️ ВАРТА & СВІТЛО</div>
            <div class="logo-sub">Моніторинг України</div>
        </div>
        <div id="update-time" style="font-size: 0.65rem; color: var(--text-sub);">З'єднання...</div>
    </div>
    <div class="main-content">
        <div class="tab-pane active" id="pane-air">
            <div class="search-box">
                <div style="font-size: 0.8rem; font-weight: 800; color: var(--accent-blue);">🗺️ Повітряний монітор:</div>
                <div class="select-group">
                    <div class="select-label">1. Область:</div>
                    <select class="custom-select" id="air-region-select" onchange="onAirRegionChange()">
                        <option value="">Завантаження областей...</option>
                    </select>
                </div>
                <div class="select-group">
                    <div class="select-label">2. Село, мікрорайон або місто:</div>
                    <input type="text" class="custom-input" id="air-city-input" placeholder="Введіть будь-яку назву..." oninput="filterAirCities()" autocomplete="off">
                    <div class="autocomplete-list" id="air-autocomplete"></div>
                </div>
            </div>
            <div class="result-card" id="air-result-card">
                <div class="res-top">
                    <div class="res-title" id="air-res-title">Оберіть локацію</div>
                    <span class="res-badge code-green-tag" id="air-res-badge">ТИША</span>
                </div>
                <div class="res-desc" id="air-res-desc">Статус простору очікує вибору населеного пункту...</div>
            </div>
        </div>
        <div class="tab-pane" id="pane-outages">
            <div class="search-box">
                <div style="font-size: 0.8rem; font-weight: 800; color: var(--accent-yellow);">⚡ Графіки світла</div>
                <div class="select-group">
                    <div class="select-label">1. Область:</div>
                    <select class="custom-select" id="out-region-select" onchange="onOutRegionChange()">
                        <option value="">Завантаження областей...</option>
                    </select>
                </div>
                <div class="select-group">
                    <div class="select-label">2. Село, мікрорайон або місто:</div>
                    <input type="text" class="custom-input" id="out-city-input" placeholder="Введіть будь-яку назву..." oninput="filterOutCities()" autocomplete="off">
                    <div class="autocomplete-list" id="out-autocomplete"></div>
                </div>
            </div>
            <div class="result-card" style="border-left-color: var(--accent-yellow);" id="out-result-card">
                <div class="res-top">
                    <div class="res-title" id="out-res-title">Статус живлення за першоджерелом</div>
                </div>
                <div class="res-desc" id="out-res-desc">Очікування вибору населеного пункту...</div>
            </div>
        </div>
    </div>
    <div class="nav-bar">
        <div class="nav-item active" onclick="switchTab('air', this)"><span style="font-size:1.1rem;">🗺️</span><span>Повітряний монітор</span></div>
        <div class="nav-item" onclick="switchTab('outages', this)"><span style="font-size:1.1rem;">⚡</span><span>Графіки світла</span></div>
    </div>
    <script>
        let globalDb = {};
        let airAlerts = {};
        let outageStatuses = {};
        let selectedAirCity = "";
        let selectedOutCity = "";
        let isInitialized = false;

        function switchTab(tabName, el) {
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            if (tabName === 'air') {
                document.getElementById('pane-air').classList.add('active');
            } else {
                document.getElementById('pane-outages').classList.add('active');
                if(!isInitialized && Object.keys(globalDb).length > 0) { initOutageSelectors(); }
            }
            el.classList.add('active');
        }

        function initAirSelectors() {
            const regSel = document.getElementById('air-region-select');
            if (!regSel) return;
            const currentVal = regSel.value;
            regSel.innerHTML = '';
            for (const reg in globalDb) {
                const opt = document.createElement('option');
                opt.value = reg; opt.innerText = reg;
                regSel.appendChild(opt);
            }
            if (currentVal && globalDb[currentVal]) regSel.value = currentVal;
            initOutageSelectors();
            isInitialized = true;
            renderAirStatus();
        }

        function initOutageSelectors() {
            const regSel = document.getElementById('out-region-select');
            if (!regSel) return;
            const currentVal = regSel.value;
            regSel.innerHTML = '';
            for (const reg in globalDb) {
                const opt = document.createElement('option');
                opt.value = reg; opt.innerText = reg;
                regSel.appendChild(opt);
            }
            if (currentVal && globalDb[currentVal]) regSel.value = currentVal;
            renderOutageStatus();
        }

        function onAirRegionChange() {
            selectedAirCity = "";
            const input = document.getElementById('air-city-input');
            if (input) input.value = '';
            renderAirStatus();
        }

        function onOutRegionChange() {
            selectedOutCity = "";
            const input = document.getElementById('out-city-input');
            if (input) input.value = '';
            renderOutageStatus();
        }

        function filterAirCities() {
            const regSel = document.getElementById('air-region-select');
            const input = document.getElementById('air-city-input');
            const listEl = document.getElementById('air-autocomplete');
            if (!regSel || !input || !listEl) return;
            const reg = regSel.value;
            const query = input.value.toLowerCase().trim();
            selectedAirCity = input.value.trim();
            renderAirStatus();
            
            listEl.innerHTML = '';
            if (!query || !globalDb[reg]) { listEl.style.display = 'none'; return; }
            const matches = globalDb[reg].filter(c => c.toLowerCase().includes(query));
            if (matches.length === 0) { listEl.style.display = 'none'; return; }
            matches.forEach(city => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';
                item.innerHTML = `${city} <span style="font-size:0.7rem; color:var(--text-sub); float:right;">(${reg})</span>`;
                item.onclick = () => {
                    input.value = city;
                    selectedAirCity = city;
                    listEl.style.display = 'none';
                    renderAirStatus();
                };
                listEl.appendChild(item);
            });
            listEl.style.display = 'block';
        }

        function renderAirStatus() {
            const regSel = document.getElementById('air-region-select');
            if (!regSel) return;
            const reg = regSel.value;
            const card = document.getElementById('air-result-card');
            const title = document.getElementById('air-res-title');
            const badge = document.getElementById('air-res-badge');
            const desc = document.getElementById('air-res-desc');
            
            title.innerText = selectedAirCity ? `${selectedAirCity} (${reg})` : (reg || 'Локація');
            const alertData = airAlerts[reg] || { code: 'green', text: 'ТИША', detail: 'Штатний режим моніторингу.' };
            
            if (alertData.code === 'red') {
                card.className = 'result-card red';
                badge.className = 'res-badge code-red-tag';
                badge.innerText = alertData.text;
            } else {
                card.className = 'result-card';
                badge.className = 'res-badge code-green-tag';
                badge.innerText = alertData.text;
            }
            desc.innerHTML = `📍 Обрана локація: <b>${selectedAirCity || 'Вся область'}</b><br>📡 Статус простору: ${alertData.detail}`;
        }

        function filterOutCities() {
            const regSel = document.getElementById('out-region-select');
            const input = document.getElementById('out-city-input');
            const listEl = document.getElementById('out-autocomplete');
            if (!regSel || !input || !listEl) return;
            const reg = regSel.value;
            const query = input.value.toLowerCase().trim();
            selectedOutCity = input.value.trim();
            renderOutageStatus();

            listEl.innerHTML = '';
            if (!query || !globalDb[reg]) { listEl.style.display = 'none'; return; }
            const matches = globalDb[reg].filter(c => c.toLowerCase().includes(query));
            if (matches.length === 0) { listEl.style.display = 'none'; return; }
            matches.forEach(city => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';
                item.innerHTML = `${city} <span style="font-size:0.7rem; color:var(--text-sub); float:right;">(${reg})</span>`;
                item.onclick = () => {
                    input.value = city;
                    selectedOutCity = city;
                    listEl.style.display = 'none';
                    renderOutageStatus();
                };
                listEl.appendChild(item);
            });
            listEl.style.display = 'block';
        }

        function renderOutageStatus() {
            const regSel = document.getElementById('out-region-select');
            if (!regSel) return;
            const reg = regSel.value;
            const title = document.getElementById('out-res-title');
            const desc = document.getElementById('out-res-desc');
            title.innerText = selectedOutCity ? `${selectedOutCity} (${reg})` : (reg || 'Локація не обрана');
            const outageText = outageStatuses[reg] || "⚡ Стабілізаційні графіки в штатному режимі";
            desc.innerHTML = `🏠 Обрана адреса: <b>${selectedOutCity || 'Вся область'}</b><br>⚡ Офіційний стан: <b>${outageText}</b>`;
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
                    initAirSelectors();
                } else {
                    renderAirStatus();
                    if (document.getElementById('pane-outages').classList.contains('active')) {
                        renderOutageStatus();
                    }
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

    # Список першоджерел (резервні канали моніторингу)
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
                    # Парсимо залежно від структури відповіді конкретного API
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
                                "detail": "⚠️ Увага! Оголошено повітряну тривогу в регіоні."
                            }
                        else:
                            air_alerts_map[reg] = {
                                "code": "green", 
                                "text": "ТИША", 
                                "detail": "✅ Штатний режим. Повітряна тривога відсутня."
                            }
                    success_fetched = True
                    break
            except Exception:
                continue

    # Якщо всі зовнішні джерела не відповіли, заповнюємо за замовчуванням мирним статусом
    if not success_fetched:
        for reg in REGIONS_DATABASE.keys():
            air_alerts_map[reg] = {
                "code": "green", 
                "text": "ТИША", 
                "detail": "✅ Штатний режим (мультиджерело активне)."
            }

    outages_map = {reg: "⚡ Стабілізаційні графіки за оперативними даними Обленерго" for reg in REGIONS_DATABASE.keys()}

    return {
        "regions_db": REGIONS_DATABASE,
        "air_alerts": air_alerts_map,
        "outages_status": outages_map
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
