"""
Анализатор подозрительных сообщений «Щит от мошенников».

Работает полностью офлайн на правилах (регулярные выражения + разбор ссылок).
Каждый признак даёт «вклад» в риск, вклады объединяются по формуле
1 − Π(1 − p), поэтому несколько слабых признаков складываются,
но итог никогда не превышает 100.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

FLAGS = re.IGNORECASE | re.UNICODE
W = r"[^.!?\n]"  # «внутри одного предложения»


@dataclass
class Pattern:
    regex: re.Pattern
    weight: int


@dataclass
class Rule:
    id: str
    title: str
    icon: str
    explanation: str
    advice: str
    patterns: list[Pattern]
    cap: int = 60


def P(rx: str, weight: int) -> Pattern:
    return Pattern(re.compile(rx, FLAGS), weight)


# ---------------------------------------------------------------------------
# Текстовые правила
# ---------------------------------------------------------------------------
RULES: list[Rule] = [
    Rule(
        id="money",
        title="Просьба срочно перевести деньги",
        icon="💸",
        explanation="Отправитель просит перевести, скинуть или одолжить деньги. "
        "Это главная цель почти любой мошеннической схемы.",
        advice="Не переводите деньги, пока не перезвоните человеку по его старому, "
        "знакомому вам номеру или не увидитесь лично.",
        patterns=[
            P(rf"\b(?:срочно|быстрее|немедленно|прямо сейчас|скорее)\b{W}{{0,60}}\b(?:перев\w*|скин\w*|перекин\w*|кинь|отправ\w*|деньг\w*|оплат\w*|пополн\w*|займ\w*|одолж\w*)", 45),
            P(rf"\b(?:перев\w*|скин\w*|перекин\w*|кинь|кинуть|отправ\w*|пополн\w*)\b{W}{{0,40}}(?:\bденьг\w*|\d[\d\s]*(?:₽|р\b|руб\w*|тыс\w*|к\b)|\bна (?:карт\w*|номер\w*|сч[её]т\w*|кошел[её]к\w*|телефон\w*))", 35),
            P(r"\b(?:займи|займите|одолжи|одолжите|выручи|выручите|нужн\w* деньги|не хватает денег)\b", 30),
            P(r"\b(?:номер карты|на эту карту|по номеру телефона)\b", 20),
        ],
        cap=50,
    ),
    Rule(
        id="safe_account",
        title="«Безопасный счёт»",
        icon="🏦",
        explanation="Банки и полиция никогда не просят переводить деньги на «безопасный», "
        "«резервный» или «защищённый» счёт. Это классическая схема.",
        advice="Положите трубку. Такого понятия, как «безопасный счёт», не существует — "
        "деньги в вашем банке уже защищены.",
        patterns=[
            P(r"\b(?:безопасн|резервн|защищ[её]нн|специальн|страхов)\w*\s+(?:сч[её]т|ячейк)\w*", 60),
        ],
        cap=60,
    ),
    Rule(
        id="sms_code",
        title="Запрос кода из SMS или данных карты",
        icon="🔐",
        explanation="Код из SMS — это ваша подпись под операцией. С ним мошенники "
        "входят в банк или Госуслуги и подтверждают переводы.",
        advice="Никогда и никому не называйте коды из SMS, пароли, CVV/CVC и PIN — "
        "даже «сотруднику банка».",
        patterns=[
            P(rf"\b(?:продиктуй|назов|назови|сообщ|скаж|пришли|пришлите|отправь|отправьте|введи|введите|скинь|скиньте|напиш|подтверд)\w*\b{W}{{0,30}}\b(?:код\w*|парол\w*|cvv\d?|cvc\d?|цифр\w*)", 50),
            P(rf"\bкод\w*\b{W}{{0,25}}\b(?:смс|sms|из сообщени\w*|подтвержд\w*)", 40),
            P(r"\b(?:смс|sms)[\s-]?код\w*", 40),
            P(r"\b(?:cvv2?|cvc2?|пин[\s-]?код\w*|pin[\s-]?code)\b", 45),
            P(r"\b(?:три|3)\s+цифр\w*", 35),
            P(r"\bкод\w* (?:с|на) обратной сторон\w*", 45),
        ],
        cap=60,
    ),
    Rule(
        id="personal_data",
        title="Запрос личных данных",
        icon="🪪",
        explanation="Номер карты, срок её действия, паспорт, СНИЛС или логин с паролем "
        "позволяют украсть деньги или оформить на вас кредит.",
        advice="Не отправляйте фото и данные документов и карт в переписке.",
        patterns=[
            P(r"\b(?:номер\w*|данн\w*|реквизит\w*|фото)\s+(?:вашей\s+|своей\s+)?(?:карт\w*|паспорт\w*)", 35),
            P(r"\bсрок\w* действия\b", 30),
            P(r"\b(?:паспортн\w* данн\w*|снилс\w*|серию и номер)\b", 30),
            P(r"\b(?:логин\w* и парол\w*|парол\w* от)\b", 40),
        ],
        cap=45,
    ),
    Rule(
        id="prize",
        title="Обещание выигрыша или выплаты",
        icon="🎁",
        explanation="Неожиданные призы, компенсации и «положенные выплаты» — приманка. "
        "Обычно дальше просят оплатить «комиссию» или ввести данные карты.",
        advice="Если вы не участвовали в розыгрыше — вы ничего не выиграли. "
        "Проверяйте выплаты только на официальных сайтах ведомств.",
        patterns=[
            P(r"\bвы\s+(?:выиграл\w*|стал\w* победител\w*|получил\w* (?:приз|подар|выигрыш)\w*)", 40),
            P(r"\b(?:выигрыш\w*|выиграл\w*|победител\w*|лотере\w*|розыгрыш\w*|джекпот\w*)", 30),
            P(r"\bприз(?:а|ом|ы|ов)?\b", 25),
            P(r"\b(?:компенсаци\w*|положен\w* выплат\w*|социальн\w* выплат\w*|возврат\w* (?:налог|средств|денег)\w*)", 30),
            P(rf"\b(?:оплат|заплат|внес|переве)\w*\b{W}{{0,40}}\b(?:комисси\w*|пошлин\w*|страховк\w*|налог\w* на выигрыш)", 45),
            P(r"\b(?:бесплатн\w*|подар\w*|бонус\w*)\b", 10),
        ],
        cap=50,
    ),
    Rule(
        id="pressure",
        title="Давление, срочность и угрозы",
        icon="⚠️",
        explanation="Мошенники торопят и пугают, чтобы вы не успели подумать и посоветоваться. "
        "Настоящие организации не требуют решений «за 5 минут».",
        advice="Возьмите паузу. Любая настоящая проблема подождёт, пока вы сами "
        "позвоните в организацию по официальному номеру.",
        patterns=[
            P(r"(?:\bсрочно\b|\bнемедленно\b|\bнезамедлительно\b|\bпрямо сейчас\b|\bв течени[ея] \d+\s*(?:минут|час|сут)\w*|\bв течени[ея] (?:часа|суток|дня)\b|\bсегодня до\b|\bпоследн\w* (?:предупреждени|шанс|день)\w*|\bосталось \d+\s*(?:минут|час)\w*|\bтолько сегодня\b|\bвремени (?:мало|нет)\b)", 15),
            P(r"\b(?:заблокир\w*|блокировк\w*|аннулир\w*|арест\w*|замороз\w*|заморож\w*)", 25),
            P(r"\b(?:несанкционированн\w*|подозрительн\w* (?:операци|перевод|вход|активност)\w*|мошенническ\w* операци\w*|оформ\w*\s+(?:на вас\s+)?кредит\w*|взлом\w*|утечк\w*)", 30),
            P(r"\b(?:полици\w*|мвд|фсб|следовател\w*|прокуратур\w*|центробанк\w*|цб рф|банк\w* росси\w*|служб\w* безопасности|росфинмониторинг\w*|сотрудник\w* банка|служб\w* поддержки банка)", 25),
            P(r"\b(?:уголовн\w*|штраф\w*|суд(?:а|е|ом|ебн\w*)?\b|ответственност\w*|приставы|коллектор\w*)", 25),
            P(r"(?:\bникому не (?:говор|сообщ|рассказ)\w*|\bне (?:говорите|сообщайте|рассказывайте)\w* (?:родным|близким|никому|банку|сотрудник\w*)|\bне кладите трубку\b|\bне отключайтесь\b|\bтайн\w* следстви\w*|\bконфиденциальн\w*)", 40),
        ],
        cap=55,
    ),
    Rule(
        id="impersonation",
        title="Выдают себя за близкого человека",
        icon="🎭",
        explanation="«Мама, это я, у меня новый номер» — популярная схема. Аккаунт "
        "знакомого тоже могут взломать и писать от его имени.",
        advice="Позвоните родственнику по старому номеру или задайте вопрос, "
        "ответ на который знает только он.",
        patterns=[
            P(r"\b(?:мам\w*|пап\w*|сын\w*|доч\w*|бабул\w*|бабушк\w*|дедушк\w*)\W{0,3}\s*это я\b", 40),
            P(r"\b(?:у меня|это мой|пиши на)\s+нов\w* номер\b|\bсменил\w* номер\b", 30),
            P(r"\bпопал\w* в (?:беду|аварию|дтп|больниц\w*|полици\w*|неприятност\w*)", 40),
            P(r"\bне могу (?:сейчас )?(?:говорить|позвонить|разговаривать)\b", 20),
        ],
        cap=50,
    ),
    Rule(
        id="remote_app",
        title="Просьба установить приложение",
        icon="📲",
        explanation="Программы удалённого доступа (AnyDesk, RustDesk и др.) и APK-файлы "
        "дают мошенникам полный контроль над телефоном и банковскими приложениями.",
        advice="Не устанавливайте приложения по ссылкам из сообщений — только из "
        "официальных магазинов и только по своей инициативе.",
        patterns=[
            P(rf"\b(?:установ|скача|загруз)\w*\b{W}{{0,40}}\b(?:приложени\w*|программ\w*|apk|обновлени\w*)", 35),
            P(r"\b(?:anydesk|teamviewer|rustdesk|rudesktop|аnydesk|эни ?деск)\b|\.apk\b", 50),
            P(r"\bдемонстраци\w* экрана\b", 40),
        ],
        cap=55,
    ),
    Rule(
        id="investment",
        title="Лёгкий заработок или инвестиции",
        icon="📈",
        explanation="Гарантированный доход «без риска» не бывает. Такие предложения ведут "
        "в финансовые пирамиды и поддельные биржи.",
        advice="Проверьте компанию в справочнике участников финрынка на сайте Банка России.",
        patterns=[
            P(r"\b(?:гарантированн\w* (?:доход|прибыл|заработ)\w*|без риска|без вложений)\b", 35),
            P(r"\b(?:пассивн\w* доход\w*|заработ\w* от \d+|доход\w* от \d+|удво\w*|приумнож\w*)", 25),
            P(r"\b(?:инвестиц\w*|криптовалют\w*|биткоин\w*|крипт\w* бирж\w*|трейдинг\w*)", 15),
            P(r"\b(?:работа на дому|подработк\w*|ставить лайки|оплата за отзыв\w*)", 15),
        ],
        cap=45,
    ),
    Rule(
        id="channel_switch",
        title="Просят перейти в мессенджер",
        icon="💬",
        explanation="Перевод разговора в Telegram или WhatsApp помогает мошенникам "
        "уйти от модерации и спам-фильтров.",
        advice="Общайтесь с организациями только через официальные приложения и сайты.",
        patterns=[
            P(rf"\b(?:напиш|перейд|свяж|пиш|добав)\w*\b{W}{{0,30}}\b(?:telegram|телеграм\w*|whatsapp|ватсап\w*|вотсап\w*|viber|вайбер\w*)", 15),
        ],
        cap=15,
    ),
    Rule(
        id="generic_greeting",
        title="Обезличенное обращение",
        icon="👤",
        explanation="«Уважаемый клиент» вместо имени — признак массовой рассылки.",
        advice="Сообщения от вашего банка обычно приходят в его приложении или с короткого официального номера.",
        patterns=[
            P(r"\b(?:уважаем\w* (?:клиент|пользовател|абонент|держател)\w*|дорог\w* (?:клиент|друг)\w*)", 10),
        ],
        cap=10,
    ),
]

# ---------------------------------------------------------------------------
# Ссылки
# ---------------------------------------------------------------------------
TLDS = (
    "ru|рф|su|com|net|org|info|biz|xyz|top|online|site|club|icu|buzz|live|shop|click|"
    "link|tk|ml|ga|cf|gq|pw|cc|ws|fun|space|website|store|io|me|app|pro|ua|by|kz|cn|"
    "tech|vip|win|bet|loan|money|work|host|press|life|world|today|us|co|xn--p1ai"
)
URL_RE = re.compile(
    rf"(?:(?:https?://|www\.)[^\s<>\"'«»]+|(?<![@\w.])(?:[a-zа-яё0-9-]+\.)+(?:{TLDS})\b(?:/[^\s<>\"'«»]*)?)",
    FLAGS,
)

SHORTENERS = {
    "bit.ly", "clck.ru", "tinyurl.com", "goo.su", "cutt.ly", "is.gd", "t.co", "vk.cc",
    "u.to", "rebrand.ly", "shorturl.at", "qps.ru", "ow.ly", "tiny.cc", "bit.do",
    "s.id", "rb.gy", "v.gd", "inlnk.ru", "to.click",
}
RISKY_TLDS = {
    "xyz", "top", "online", "site", "club", "icu", "buzz", "live", "shop", "click", "link",
    "tk", "ml", "ga", "cf", "gq", "pw", "cc", "ws", "fun", "space", "website", "store",
    "vip", "win", "bet", "loan", "money", "work", "host", "press", "info", "biz",
}
# бренд -> официальные домены (поддомены тоже считаются официальными)
BRANDS: dict[str, set[str]] = {
    "sber": {"sberbank.ru", "sber.ru", "sberbank.com"},
    "sberbank": {"sberbank.ru", "sberbank.com"},
    "tinkoff": {"tinkoff.ru", "tbank.ru"},
    "tbank": {"tbank.ru", "tinkoff.ru"},
    "vtb": {"vtb.ru"},
    "alfa": {"alfabank.ru"},
    "alfabank": {"alfabank.ru"},
    "gazprombank": {"gazprombank.ru"},
    "raiffeisen": {"raiffeisen.ru"},
    "pochtabank": {"pochtabank.ru"},
    "gosuslugi": {"gosuslugi.ru"},
    "nalog": {"nalog.gov.ru", "nalog.ru"},
    "ozon": {"ozon.ru", "ozon.com"},
    "wildberries": {"wildberries.ru", "wb.ru"},
    "avito": {"avito.ru"},
    "pochta": {"pochta.ru"},
    "cdek": {"cdek.ru"},
    "yandex": {"yandex.ru", "ya.ru", "yandex.com"},
    "mvideo": {"mvideo.ru"},
    "dns-shop": {"dns-shop.ru"},
    "megafon": {"megafon.ru"},
    "beeline": {"beeline.ru"},
    "mts": {"mts.ru"},
    "tele2": {"tele2.ru", "t2.ru"},
    "rostelecom": {"rt.ru", "rostelecom.ru"},
    "telegram": {"telegram.org", "t.me"},
    "whatsapp": {"whatsapp.com", "wa.me"},
    "vk": {"vk.com", "vk.ru", "vk.cc"},
    "госуслуги": {"госуслуги.рф"},
    "сбер": {"сбер.рф"},
}
SHORT_BRANDS = {"vk", "mts", "vtb", "sber", "alfa", "ozon", "cdek", "tbank"}  # только целым словом
BAIT_WORDS = (
    "login", "verify", "secure", "bonus", "prize", "priz", "compens", "kompens", "vyplat",
    "viplat", "win", "gift", "free", "akci", "podar", "auth", "confirm", "update",
    "lk-", "-lk", "cabinet", "kabinet", "support", "pay", "oplat", "dostav", "delivery",
)


def _host_of(url: str) -> tuple[str, str, str]:
    raw = url if re.match(r"https?://", url, FLAGS) else "http://" + url
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower().rstrip(".")
    return host, parts.scheme.lower(), raw


def _is_official(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def _mixed_script(label: str) -> bool:
    has_lat = bool(re.search(r"[a-z]", label))
    has_cyr = bool(re.search(r"[а-яё]", label))
    return has_lat and has_cyr


def analyze_url(url: str) -> dict:
    """Возвращает {url, host, risk, reasons[]} для одной ссылки."""
    url = url.rstrip(".,;:!?)»\"'")
    host, scheme, raw = _host_of(url)
    reasons: list[str] = []
    risk = 0

    if not host:
        return {"url": url, "host": host, "risk": 0, "reasons": []}

    labels = host.split(".")
    tld = labels[-1]
    tokens = re.split(r"[.\-]", host)

    try:
        ipaddress.ip_address(host)
        risk += 35
        reasons.append("Вместо названия сайта — IP-адрес")
    except ValueError:
        pass

    if host in SHORTENERS:
        risk += 25
        reasons.append("Сокращённая ссылка — настоящий адрес скрыт")

    impersonated = None
    is_official_any = any(_is_official(host, d) for d in BRANDS.values())
    for brand, official in ([] if is_official_any else BRANDS.items()):
        b = brand.rstrip("-")
        hit = (b in tokens) if b in SHORT_BRANDS else (b in host)
        if hit and not _is_official(host, official):
            impersonated = (b, sorted(official)[0])
            break
    if impersonated:
        risk += 45
        reasons.append(
            f"Похоже на «{impersonated[0]}», но это не официальный сайт "
            f"(официальный: {impersonated[1]})"
        )

    if any(_mixed_script(l) for l in labels):
        risk += 40
        reasons.append("В адресе смешаны латинские и русские буквы — приём для подделки")

    if any(l.startswith("xn--") for l in labels[:-1]):
        risk += 15
        reasons.append("Адрес закодирован (punycode) — может маскировать похожие символы")

    if tld in RISKY_TLDS:
        risk += 15
        reasons.append(f"Доменная зона .{tld} часто используется для одноразовых сайтов")

    if "@" in raw.split("//", 1)[-1].split("/", 1)[0]:
        risk += 30
        reasons.append("Символ «@» в адресе — браузер откроет совсем другой сайт")

    if host.count("-") >= 2 or len(labels) >= 5 or len(host) > 40:
        risk += 10
        reasons.append("Слишком длинный или запутанный адрес")

    low = raw.lower()
    bait = [w for w in BAIT_WORDS if w in low]
    if bait and not impersonated:
        risk += 10
        reasons.append("В адресе слова-приманки: " + ", ".join(sorted(set(bait))[:3]))
    elif bait:
        risk += 5

    if scheme == "http" and url.lower().startswith("http://"):
        risk += 5
        reasons.append("Нет защищённого соединения (http вместо https)")

    return {"url": url, "host": host, "risk": min(risk, 70), "reasons": reasons}


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------
LEVELS = [
    (75, "critical", "Критический риск", "Почти наверняка мошенничество. Ничего не делайте по этому сообщению."),
    (50, "high", "Высокий риск", "Много признаков мошенничества. Скорее всего, это обман."),
    (20, "medium", "Средний риск", "Есть настораживающие признаки. Проверьте информацию через официальные каналы."),
    (0, "low", "Низкий риск", "Явных признаков мошенничества не найдено. Но всё равно оставайтесь внимательны."),
]

GENERAL_ADVICE = {
    "critical": [
        "Не отвечайте, не переходите по ссылкам и не перезванивайте на номера из сообщения.",
        "Если уже сообщили код или перевели деньги — немедленно позвоните в банк по номеру на обороте карты и заблокируйте её.",
        "Заблокируйте отправителя и отметьте сообщение как спам.",
        "Если деньги списаны — подайте заявление в полицию (102) и сообщите в банк в течение суток.",
    ],
    "high": [
        "Не отвечайте и не переходите по ссылкам.",
        "Проверьте информацию, позвонив в организацию по номеру с её официального сайта.",
        "Заблокируйте отправителя и отметьте сообщение как спам.",
    ],
    "medium": [
        "Не спешите: проверьте отправителя через официальный сайт или приложение.",
        "Не переходите по ссылкам — наберите адрес сайта вручную.",
        "Посоветуйтесь с близкими, прежде чем что-либо делать.",
    ],
    "low": [
        "Если сообщение от незнакомца — всё равно не сообщайте личные данные.",
        "При малейших сомнениях проверьте информацию через официальные источники.",
    ],
}

MAX_LEN = 10_000


def _normalize(text: str) -> str:
    # ё -> е и «лукавые» латинские буквы не трогаем, длина строки сохраняется,
    # поэтому позиции совпадений совпадают с исходным текстом
    return text.replace("ё", "е").replace("Ё", "Е")


def analyze(text: str) -> dict:
    text = (text or "")[:MAX_LEN]
    norm = _normalize(text)
    signs: list[dict] = []
    highlights: list[dict] = []

    for rule in RULES:
        matched_weights: list[int] = []
        fragments: list[str] = []
        for pat in rule.patterns:
            found = False
            for m in pat.regex.finditer(norm):
                found = True
                frag = text[m.start():m.end()].strip()
                if frag and frag.lower() not in (f.lower() for f in fragments):
                    fragments.append(frag)
                highlights.append({"start": m.start(), "end": m.end(), "sign": rule.id})
            if found:
                matched_weights.append(pat.weight)
        if matched_weights:
            matched_weights.sort(reverse=True)
            score = matched_weights[0] + 5 * (len(matched_weights) - 1)
            signs.append({
                "id": rule.id,
                "title": rule.title,
                "icon": rule.icon,
                "explanation": rule.explanation,
                "advice": rule.advice,
                "score": min(score, rule.cap),
                "fragments": fragments[:5],
            })

    # ссылки
    links = []
    for m in URL_RE.finditer(text):
        info = analyze_url(m.group(0))
        if not info["host"]:
            continue
        links.append(info)
        highlights.append({"start": m.start(), "end": m.start() + len(info["url"]), "sign": "link"})
    if links:
        worst = max(l["risk"] for l in links)
        if worst > 0:
            reasons = []
            for l in links:
                reasons.extend(f"{l['host']}: {r}" for r in l["reasons"])
            signs.append({
                "id": "link",
                "title": "Подозрительная ссылка",
                "icon": "🔗",
                "explanation": "Ссылка может вести на поддельный сайт, который крадёт пароли "
                "и данные карт, или скачивать вредоносную программу.",
                "advice": "Не открывайте ссылку. Зайдите на сайт организации, набрав адрес вручную, "
                "или через официальное приложение.",
                "score": worst,
                "fragments": [l["url"] for l in links if l["risk"] > 0][:5],
                "details": reasons[:8],
            })
        else:
            signs.append({
                "id": "link",
                "title": "В сообщении есть ссылка",
                "icon": "🔗",
                "explanation": "Явных признаков подделки в адресе нет, но любые ссылки "
                "из неожиданных сообщений стоит открывать с осторожностью.",
                "advice": "Убедитесь, что адрес совпадает с официальным сайтом, прежде чем вводить данные.",
                "score": 5,
                "fragments": [l["url"] for l in links][:5],
            })

    # итоговый балл
    remain = 1.0
    for s in signs:
        remain *= 1 - s["score"] / 100
    score = (1 - remain) * 100
    strong = [s for s in signs if s["score"] >= 25]
    if len(strong) >= 3:
        score += 10
    ids = {s["id"] for s in signs}
    if {"sms_code", "pressure"} <= ids or {"money", "pressure"} <= ids or {"money", "impersonation"} <= ids:
        score += 5
    score = int(round(max(0, min(100, score))))

    for threshold, level, label, verdict in LEVELS:
        if score >= threshold:
            break

    signs.sort(key=lambda s: s["score"], reverse=True)
    recommendations: list[str] = []
    for s in signs:
        if s["score"] >= 10 and s["advice"] not in recommendations:
            recommendations.append(s["advice"])
    for a in GENERAL_ADVICE[level]:
        if a not in recommendations:
            recommendations.append(a)

    return {
        "score": score,
        "level": level,
        "label": label,
        "verdict": verdict,
        "signs": signs,
        "links": links,
        "recommendations": recommendations,
        "highlights": _merge(highlights),
        "length": len(text),
    }


def _merge(spans: list[dict]) -> list[dict]:
    spans = sorted(spans, key=lambda s: (s["start"], -s["end"]))
    out: list[dict] = []
    for s in spans:
        if out and s["start"] < out[-1]["end"]:
            out[-1]["end"] = max(out[-1]["end"], s["end"])
        else:
            out.append(dict(s))
    return out
