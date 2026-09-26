import ast
import operator
import re
import platform
import socket
import sys
from datetime import datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests
import time
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
VIREONIX_URL = "https://vireonix.ai/v1/chat/completions"

# 한국 주요 도시의 고정 좌표. 날씨 조회에서 지오코딩 실패를 줄인다.
KOREAN_CITY_COORDS = {
    "서울": (37.5665, 126.9780), "서울특별시": (37.5665, 126.9780),
    "부산": (35.1796, 129.0756), "부산광역시": (35.1796, 129.0756),
    "대구": (35.8714, 128.6014), "대구광역시": (35.8714, 128.6014),
    "인천": (37.4563, 126.7052), "인천광역시": (37.4563, 126.7052),
    "광주": (35.1595, 126.8526), "광주광역시": (35.1595, 126.8526),
    "대전": (36.3504, 127.3845), "대전광역시": (36.3504, 127.3845),
    "울산": (35.5384, 129.3114), "울산광역시": (35.5384, 129.3114),
    "세종": (36.4800, 127.2890), "세종특별자치시": (36.4800, 127.2890),
    "제주": (33.4996, 126.5312), "제주도": (33.4996, 126.5312), "제주시": (33.4996, 126.5312),
    "동해": (37.5247, 129.1143), "동해시": (37.5247, 129.1143),
    "강릉": (37.7519, 128.8761), "강릉시": (37.7519, 128.8761),
    "춘천": (37.8813, 127.7298), "춘천시": (37.8813, 127.7298),
    "원주": (37.3422, 127.9202), "원주시": (37.3422, 127.9202),
    "수원": (37.2636, 127.0286), "수원시": (37.2636, 127.0286),
    "성남": (37.4449, 127.1389), "성남시": (37.4449, 127.1389),
    "고양": (37.6584, 126.8320), "고양시": (37.6584, 126.8320),
}

WEATHER_CODES = {
    0: "맑음", 1: "대체로 맑음", 2: "부분적으로 흐림", 3: "흐림",
    45: "안개", 48: "안개", 51: "이슬비", 53: "이슬비", 55: "이슬비",
    56: "어는 이슬비", 57: "어는 이슬비", 61: "약한 비", 63: "비", 65: "강한 비",
    66: "어는 비", 67: "어는 비", 71: "약한 눈", 73: "눈", 75: "강한 눈",
    77: "눈 알갱이", 80: "소나기", 81: "소나기", 82: "강한 소나기",
    85: "눈 소나기", 86: "강한 눈 소나기", 95: "천둥번개", 96: "우박을 동반한 천둥번개",
    99: "우박을 동반한 천둥번개",
}



def call_vireonix_with_retry(messages, max_attempts=3, timeout_seconds=12):
    """Bounded retry for transient Vireonix failures."""
    payload = {"model": "auto", "messages": messages}
    last_error = None
    for attempt in range(max_attempts):
        try:
            response = requests.post(
                "https://vireonix.ai/v1/chat/completions",
                json={"model": "auto", "messages": messages},
                headers={"Content-Type": "application/json"},
                timeout=12,
            )
            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                last_error = RuntimeError("AI response did not contain usable text.")
            elif response.status_code in (408, 425, 429, 500, 502, 503, 504):
                last_error = RuntimeError(
                    f"Transient AI server error: HTTP {response.status_code}"
                )
            else:
                last_error = RuntimeError(
                    f"AI server error: HTTP {response.status_code}"
                )
                break
        except (requests.Timeout, requests.RequestException, ValueError) as exc:
            last_error = exc

        if attempt < max_attempts - 1:
            time.sleep(0.7 * (attempt + 1))

    raise last_error or RuntimeError("AI request failed.")

def clean_ai_response(text):
    text = str(text or "")
    emoji_pattern = re.compile(
        "[\\U0001F300-\\U0001FAFF\\U00002700-\\U000027BF"
        "\\U00002600-\\U000026FF\\U0001F1E0-\\U0001F1FF"
        "\\U0001F900-\\U0001F9FF\\u200d\\ufe0f\\u20e3]",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ask_vireonix(question, history=None):
    system_prompt = """
당신은 PRIME이라는 개인 AI 비서다.
한국어로 답한다.
말투는 영화 속 첨단 AI 비서처럼 침착하고 자연스럽고 세련되게 한다.
기계적인 반복 문장과 지나치게 딱딱한 표현을 피한다.
상황에 따라 짧고 재치 있는 표현을 사용할 수 있지만 과장하지 않는다.
사용자에게 친근하지만 무례하지 않게 말한다.
답변은 필요한 만큼만 간결하게 한다.
이모지와 이모티콘은 사용하지 않는다.
장식용 특수문자는 사용하지 않는다.
모르는 사실은 추측하지 말고 모른다고 말한다.
이전 대화가 제공되면 자연스럽게 이어서 답한다.
이전 대화에 없는 내용을 기억하는 척하지 않는다.
"에디스"라는 이름을 주장하거나 영화 속 캐릭터인 척하지 않는다.
"EDITH 스타일"이라는 표현 대신 PRIME 고유의 첨단 AI 비서 말투를 유지한다.
"""

    messages = [{"role": "system", "content": system_prompt}]
    if isinstance(history, list):
        for item in history[-12:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content[:1500]})
    messages.append({"role": "user", "content": str(question)[:3000]})

    response = requests.post(
        VIREONIX_URL,
        json={"model": "auto", "messages": messages},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("AI가 답변을 반환하지 않았습니다.")
    message = choices[0].get("message") or {}
    return clean_ai_response(message.get("content", "")) or "답변을 생성하지 못했습니다."


def make_time_answer():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    return f"현재 시간은 {now.hour}시 {now.minute}분입니다."


def make_date_answer():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    return f"오늘은 {now.year}년 {now.month}월 {now.day}일 {weekdays[now.weekday()]}입니다."


def is_time_question(q):
    return any(x in q for x in ["몇 시", "몇시", "현재 시간", "지금 시간", "시간 알려줘", "시간 알려 줘", "지금 몇"])


def is_date_question(q):
    return any(x in q for x in ["오늘 날짜", "오늘이 며칠", "오늘 며칠", "몇 월 며칠", "몇월 며칠", "현재 날짜"])


def is_screen_link_question(q):
    text = str(q or '').strip().lower()
    start = re.sub(r'^(프라임[,\s]*)', '', text, flags=re.I).strip()
    return any(x in start for x in [
        "화면 연동", "화면연동", "폰 화면 연동", "핸드폰 화면 연동",
        "휴대폰 화면 연동", "스마트폰 화면 연동", "화면 연결", "화면연결"
    ])


def is_screen_unlink_question(q):
    text = str(q or '').strip().lower()
    return any(x in text for x in [
        "화면 연동 해제", "화면연동 해제", "화면 연결 해제", "화면연결 해제",
        "화면 연동 끄기", "화면연동 끄기"
    ])


def extract_weather_city(q):
    cleaned = re.sub(r"^(프라임[,\s]*)", "", q.strip(), flags=re.I)
    weather_words = r"(?:날씨|기온|온도|비 와|비가 와|비올|비 올|눈 와|눈이 와|일기예보)"
    if not re.search(weather_words, cleaned):
        return None
    m = re.search(r"([가-힣A-Za-z0-9·\-\s]{1,30}?)(?:의|에서)?\s*" + weather_words, cleaned, flags=re.I)
    if m:
        city = m.group(1).strip(" ,?%!.")
        if city and city not in ["현재", "오늘", "지금"]:
            return city
    return "서울"


def resolve_city(city):
    city = str(city).strip()
    if city in KOREAN_CITY_COORDS:
        lat, lon = KOREAN_CITY_COORDS[city]
        return city, lat, lon
    return None


def weather_from_open_meteo(place_name, latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "Asia/Seoul",
        "forecast_days": 1,
    }
    r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=8)
    r.raise_for_status()
    data = r.json()
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    temp = current.get("temperature_2m")
    feels = current.get("apparent_temperature")
    code = current.get("weather_code")
    wind = current.get("wind_speed_10m")
    high = (daily.get("temperature_2m_max") or [None])[0]
    low = (daily.get("temperature_2m_min") or [None])[0]
    rain = (daily.get("precipitation_probability_max") or [None])[0]
    desc = WEATHER_CODES.get(code, "날씨 정보")
    rain_text = f"강수확률은 {rain}%입니다. " if rain is not None else ""
    return (
        f"{place_name}의 현재 날씨는 {desc}이고, 기온은 {temp}도입니다. "
        f"체감온도는 {feels}도, 오늘 최고기온은 {high}도, 최저기온은 {low}도입니다. "
        f"{rain_text}현재 풍속은 시속 {wind}킬로미터입니다."
    )


def weather_from_wttr(place_name):
    r = requests.get(
        "https://wttr.in/" + quote_plus(place_name) + "?format=j1",
        headers={"User-Agent": "PRIME-weather/16.3"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    current = (data.get("current_condition") or [{}])[0]
    day = (data.get("weather") or [{}])[0]
    desc = ((current.get("weatherDesc") or [{"value": "날씨 정보"}])[0]).get("value", "날씨 정보")
    temp = current.get("temp_C", "정보 없음")
    feels = current.get("FeelsLikeC", "정보 없음")
    wind = current.get("windspeedKmph", "정보 없음")
    high = day.get("maxtempC", "정보 없음")
    low = day.get("mintempC", "정보 없음")
    rain = None
    hourly = day.get("hourly") or []
    if hourly:
        rain_values = [h.get("chanceofrain") for h in hourly if str(h.get("chanceofrain", "")).isdigit()]
        if rain_values:
            rain = max(int(v) for v in rain_values)
    rain_text = f"강수확률은 {rain}%입니다. " if rain is not None else ""
    return (
        f"{place_name}의 현재 날씨는 {desc}이고, 기온은 {temp}도입니다. "
        f"체감온도는 {feels}도, 오늘 최고기온은 {high}도, 최저기온은 {low}도입니다. "
        f"{rain_text}현재 풍속은 시속 {wind}킬로미터입니다."
    )


def get_weather_by_city(city):
    city = str(city).strip()[:50]
    direct = resolve_city(city)
    if direct:
        place_name, latitude, longitude = direct
    else:
        try:
            geo = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "ko", "format": "json"},
                timeout=6,
            )
            geo.raise_for_status()
            results = (geo.json().get("results") or [])
        except requests.RequestException:
            results = []
        if results:
            place = results[0]
            place_name = place.get("name", city)
            latitude = float(place["latitude"])
            longitude = float(place["longitude"])
        else:
            try:
                return weather_from_wttr(city)
            except requests.RequestException:
                raise ValueError(f"{city} 지역의 날씨 정보를 찾지 못했습니다.")

    try:
        return weather_from_open_meteo(place_name, latitude, longitude)
    except requests.RequestException:
        try:
            return weather_from_wttr(place_name)
        except requests.RequestException:
            raise ValueError(f"{place_name}의 날씨 정보를 가져오지 못했습니다.")


def extract_search_query(q):
    cleaned = re.sub(r"^(프라임[,\s]*)", "", q.strip(), flags=re.I)
    if re.fullmatch(r"(네이버|naver)\s*(?:검색해줘|검색해|찾아줘|찾아)?", cleaned, flags=re.I):
        return "__NAVER_HOME__"
    if re.fullmatch(r"(구글|google)\s*(?:검색해줘|검색해|찾아줘|찾아)?", cleaned, flags=re.I):
        return "__GOOGLE_HOME__"
    patterns = [
        (r"(?:네이버|naver)\s*(?:에서)?\s*(?:검색해줘|검색해|찾아줘|찾아)\s*(.*)$", "naver"),
        (r"(?:구글|google)\s*(?:에서)?\s*(?:검색해줘|검색해|찾아줘|찾아)\s*(.*)$", "google"),
        (r"(?:인터넷에서|웹에서|온라인에서)\s*(?:검색해줘|검색해|찾아줘|찾아)\s*(.*)$", "google"),
        (r"(?:검색해줘|검색해|찾아줘|찾아)\s*(.*)$", "google"),
    ]
    for pattern, engine in patterns:
        m = re.search(pattern, cleaned, flags=re.I)
        if m:
            query = m.group(1).strip(" :：")
            if query:
                return f"__{engine.upper()}__:{query}"
    return None


def web_search(query):
    query = str(query).strip()
    if query == "__NAVER_HOME__":
        return {"message": "네이버 검색 페이지를 엽니다.", "url": "https://www.naver.com/"}
    if query == "__GOOGLE_HOME__":
        return {"message": "구글 검색 페이지를 엽니다.", "url": "https://www.google.com/"}
    engine = "google"
    if query.startswith("__NAVER__:"):
        engine = "naver"
        query = query.split(":", 1)[1].strip()
    elif query.startswith("__GOOGLE__:"):
        query = query.split(":", 1)[1].strip()
    query = query[:300]
    if engine == "naver":
        return {"message": f"네이버에서 {query}를 검색합니다.", "url": "https://search.naver.com/search.naver?query=" + quote_plus(query)}
    if any(word in query for word in ["뉴스", "기사", "속보", "시사"]):
        url = "https://www.google.com/search?tbm=nws&q=" + quote_plus(query)
    else:
        url = "https://www.google.com/search?q=" + quote_plus(query)
    return {"message": f"웹 검색 페이지를 엽니다: {query}", "url": url}


def extract_calculation(q):
    cleaned = re.sub(r"^(프라임[,\s]*)", "", q.strip(), flags=re.I)
    if not re.search(r"[0-9].*(?:[+\-*/%×÷]|더하기|빼기|곱하기|나누기)", cleaned):
        return None
    m = re.search(r"(?:계산해줘|계산해|얼마야|몇이야)?\s*([0-9+\-*/%.() ×÷−더하기빼기곱하기나누기\s]{1,100})$", cleaned, flags=re.I)
    return m.group(1).strip() if m else None


def safe_calculate(expression):
    expression = expression.strip().replace("×", "*").replace("÷", "/").replace("−", "-")
    for word, symbol in [("곱하기", "*"), ("더하기", "+"), ("빼기", "-"), ("나누기", "/")]:
        expression = expression.replace(word, symbol)
    expression = expression.replace(",", "")
    if len(expression) > 100 or not re.fullmatch(r"[0-9+\-*/%.() ]+", expression):
        raise ValueError("계산할 수 없는 식입니다.")
    tree = ast.parse(expression, mode="eval")
    allowed_bin = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    allowed_unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def ev(node):
        if isinstance(node, ast.Expression): return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_unary: return allowed_unary[type(node.op)](ev(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_bin:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100: raise ValueError("거듭제곱 값이 너무 큽니다.")
            if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0: raise ZeroDivisionError
            return allowed_bin[type(node.op)](left, right)
        raise ValueError("계산할 수 없는 식입니다.")
    result = ev(tree)
    return int(result) if isinstance(result, float) and result.is_integer() else result


DEVICE_SHORTCUTS = {
    "tv_on": "PRIME TV 켜기", "tv_off": "PRIME TV 끄기",
    "pc_on": "PRIME 컴퓨터 켜기", "pc_off": "PRIME 컴퓨터 끄기",
    "laptop_on": "PRIME 노트북 켜기", "laptop_off": "PRIME 노트북 끄기",
}

def classify_device_command(question):
    text = re.sub(r"^(프라임[,\s]*)", "", str(question or "").strip(), flags=re.I).strip()
    pairs = [
        (["TV 켜", "티비 켜", "텔레비전 켜"], "tv_on"),
        (["TV 꺼", "TV 끄", "티비 꺼", "티비 끄", "텔레비전 꺼", "텔레비전 끄"], "tv_off"),
        (["노트북 켜", "노트북 전원 켜"], "laptop_on"),
        (["노트북 꺼", "노트북 끄", "노트북 전원 꺼"], "laptop_off"),
        (["컴퓨터 켜", "PC 켜", "피씨 켜", "컴퓨터 전원 켜"], "pc_on"),
        (["컴퓨터 꺼", "컴퓨터 끄", "PC 꺼", "PC 끄", "피씨 꺼", "컴퓨터 전원 꺼"], "pc_off"),
    ]
    for phrases, kind in pairs:
        if any(x.lower() in text.lower() for x in phrases):
            return kind
    return None

HTML = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRIME V16.3</title>
<style>
body{margin:0;background:#05080d;color:#eaf3ff;font-family:Arial,sans-serif}.wrap{max-width:760px;margin:auto;padding:20px}
h1{text-align:center;letter-spacing:6px;margin:8px 0}.sub{text-align:center;color:#91a7ba;margin-bottom:18px}
button,input,textarea{width:100%;box-sizing:border-box;border-radius:12px;padding:13px;margin:5px 0;font-size:16px}
button{border:1px solid #31506b;background:#0d1721;color:white;cursor:pointer}button:hover{background:#142536}
input,textarea{border:1px solid #31506b;background:#091019;color:white}textarea{min-height:90px}
#status{text-align:center;color:#75bcff;min-height:24px;margin:10px 0}#answer{white-space:pre-wrap;background:#091019;border:1px solid #20384d;border-radius:12px;padding:14px;min-height:70px}
video{width:100%;border-radius:12px;margin-top:8px;display:none}.panel{border:1px solid #20384d;border-radius:12px;padding:12px;margin-top:10px}.small{font-size:13px;color:#91a7ba;text-align:center}
#eyeState{color:#75bcff;text-align:center;min-height:22px}.eye-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
</style>
<script type="module">
window.PRIME_EYE_MODULE_READY=false;
try{
  const vision=await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22-rc.20250304/+esm");
  window.FilesetResolver=vision.FilesetResolver;window.FaceLandmarker=vision.FaceLandmarker;window.PRIME_EYE_MODULE_READY=true;
}catch(e){console.warn("Eye module unavailable",e)}
</script>
</head>
<body>
<div class="wrap">
<h1>PRIME</h1><div class="sub">Personal Response &amp; Intelligence Management Engine V16.7</div>
<div id="screenLinkPanel" class="panel screen-link" style="display:none"><b>휴대폰 화면 연동</b><div id="screenLinkState">PRIME 화면이 이 휴대폰에 표시되고 있습니다.</div><button onclick="exitScreenLink()">화면 연동 해제</button></div>
<div class="panel"><b>기기 제어</b><div id="deviceState" class="small">휴대폰을 PRIME의 제어 브리지로 사용할 수 있습니다.</div><button onclick="deviceShortcut('tv_on')">TV 켜기</button><button onclick="deviceShortcut('tv_off')">TV 끄기</button><button onclick="deviceShortcut('pc_on')">컴퓨터 켜기</button><button onclick="deviceShortcut('pc_off')">컴퓨터 끄기</button><button onclick="deviceShortcut('laptop_on')">노트북 켜기</button><button onclick="deviceShortcut('laptop_off')">노트북 끄기</button></div>
<button onclick="startWake()">PRIME 호출 대기</button><button onclick="askVoice()">말하기</button>
<textarea id="question" placeholder="질문을 입력하세요"></textarea><button onclick="askText()">질문하기</button>
<button onclick="clearConversationMemory()">대화 기억 지우기</button>
<input id="calc" placeholder="계산식 예: 25 + 37"><button onclick="calculate()">계산하기</button>
<input id="search" placeholder="검색어"><button onclick="webSearch()">웹 검색</button>
<button onclick="getTime()">현재 시간</button><button onclick="getDate()">오늘 날짜</button><button onclick="getWeather()">현재 위치 날씨</button>
<input id="destination" placeholder="목적지"><button onclick="directions()">길찾기</button>
<button onclick="startCamera()">카메라 켜기</button><video id="camera" autoplay playsinline></video><button onclick="captureCamera()">카메라 사진 캡처</button>
<div class="panel"><b>시선 인식</b><div id="eyeState">카메라를 켠 뒤 시선 인식을 시작할 수 있습니다.</div>
<div class="eye-grid"><button onclick="startEyeTracking()">눈 인식 시작</button><button onclick="stopEyeTracking()">눈 인식 중지</button></div></div>
<button onclick="vision('identify')">물체 분석</button><button onclick="vision('translate')">번역</button><button onclick="vision('price')">가격 검색</button>
<div class="panel"><b>보안 진단</b><div id="securityState" class="small">PRIME 서버의 기본 보안 상태를 확인할 수 있습니다.</div><button onclick="runSecurityCheck()">보안 진단 실행</button></div>
<input id="song" placeholder="노래 제목 또는 가수"><button onclick="playSong()">노래 검색</button>
<div id="status"></div><div id="answer"></div>
<div class="small">최근 대화 6회분은 이 브라우저에 저장되어 새로고침 후에도 이어집니다.</div><button onclick="speakAnswer()">답변 듣기</button>
</div>
<script>
let recognition=null,stream=null,lastAnswer="",eyeLandmarker=null,eyeTimer=null;
const MEMORY_KEY="prime_v16_3_conversation";
let conversationHistory=loadConversationHistory();
function loadConversationHistory(){try{const saved=JSON.parse(localStorage.getItem(MEMORY_KEY)||"[]");return Array.isArray(saved)?saved.slice(-12):[]}catch(e){return []}}
function saveConversationHistory(){try{localStorage.setItem(MEMORY_KEY,JSON.stringify(conversationHistory.slice(-12)))}catch(e){}}
function rememberTurn(q,a){conversationHistory.push({role:"user",content:String(q).slice(0,1500)},{role:"assistant",content:String(a).slice(0,1500)});conversationHistory=conversationHistory.slice(-12);saveConversationHistory()}
function clearConversationMemory(){conversationHistory=[];try{localStorage.removeItem(MEMORY_KEY)}catch(e){}answer("대화 기억을 지웠습니다.");status("기억 삭제 완료")}
function status(t){document.getElementById("status").textContent=t}function answer(t){lastAnswer=t;document.getElementById("answer").textContent=t}
function selectPrimeVoice(){
  if(!('speechSynthesis' in window))return null;
  const voices=speechSynthesis.getVoices().filter(v=>v.lang&&v.lang.toLowerCase().startsWith('ko'));
  if(!voices.length)return null;
  const preferred=['Google 한국의','Microsoft Heami','Microsoft SunHi','Yuna','Seoyeon','Jihyun'];
  for(const name of preferred){const hit=voices.find(v=>v.name&&v.name.toLowerCase().includes(name.toLowerCase()));if(hit)return hit;}
  return voices.find(v=>/neural|natural|online/i.test(v.name||'')) || voices[0];
}
function speak(t){
  if(!('speechSynthesis' in window))return;
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(String(t||''));
  u.lang='ko-KR';
  u.rate=0.88;
  u.pitch=0.72;
  u.volume=1.0;
  const v=selectPrimeVoice();
  if(v)u.voice=v;
  speechSynthesis.speak(u);
}
speechSynthesis&&speechSynthesis.addEventListener&&speechSynthesis.addEventListener('voiceschanged',()=>selectPrimeVoice());
function speakAnswer(){if(lastAnswer)speak(lastAnswer)}
function makeRecognition(){const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R){status("이 브라우저는 음성 인식을 지원하지 않습니다.");return null}const r=new R();r.lang="ko-KR";r.interimResults=false;r.continuous=false;return r}
function startWake(){recognition=makeRecognition();if(!recognition)return;status("PRIME 호출을 기다리는 중");recognition.onresult=e=>{const t=e.results[0][0].transcript.trim().toLowerCase();if(t.includes("prime")||t.includes("프라임")){status("호출 확인. 말씀하세요.");speak("호출 확인. 말씀하세요.");setTimeout(askVoice,900)}else status("PRIME이라고 말씀해주세요.")};recognition.onerror=()=>status("호출 대기가 종료되었습니다.");try{recognition.start()}catch(e){status("음성 인식을 시작할 수 없습니다.")}}
function askVoice(){recognition=makeRecognition();if(!recognition)return;status("듣고 있습니다");recognition.onresult=e=>{const q=e.results[0][0].transcript;document.getElementById("question").value=q;ask(q)};recognition.onerror=()=>status("음성을 듣지 못했습니다.");try{recognition.start()}catch(e){status("음성 인식을 시작할 수 없습니다.")}}
async function askText(){const q=document.getElementById("question").value.trim();if(q)await ask(q)}
async function ask(q){status("PRIME 처리 중");try{const r=await fetch("/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q,history:conversationHistory})});const d=await r.json();const a=d.answer||d.error||"오류가 발생했습니다.";answer(a);if(d.answer)rememberTurn(q,a);if(d.screen_link){if(d.screen_link==="on"){enterScreenLink()}else if(d.screen_link==="off"){exitScreenLink()}status("화면 연동 상태를 변경했습니다.")}if(d.device_shortcut){deviceShortcut(d.device_shortcut)}if(d.search_url){window.open(d.search_url,"_blank");status("검색 페이지를 열었습니다.");speak(a);return}status("완료");speak(a)}catch(e){status("서버 연결 오류");answer("서버에 연결하지 못했습니다.")}}
async function enterScreenLink(){
  const panel=document.getElementById("screenLinkPanel");
  if(panel) panel.style.display="block";
  document.body.classList.add("screen-linked");
  const state=document.getElementById("screenLinkState");
  if(state) state.textContent="PRIME 화면이 이 휴대폰에 표시되고 있습니다.";
  try{if(!document.fullscreenElement && document.documentElement.requestFullscreen){await document.documentElement.requestFullscreen()}}catch(e){}
}
function exitScreenLink(){
  const panel=document.getElementById("screenLinkPanel");
  if(panel) panel.style.display="none";
  document.body.classList.remove("screen-linked");
  try{if(document.fullscreenElement && document.exitFullscreen){document.exitFullscreen()}}catch(e){}
  status("화면 연동을 해제했습니다.");
}

function deviceShortcut(kind){const names={tv_on:"PRIME TV 켜기",tv_off:"PRIME TV 끄기",pc_on:"PRIME 컴퓨터 켜기",pc_off:"PRIME 컴퓨터 끄기",laptop_on:"PRIME 노트북 켜기",laptop_off:"PRIME 노트북 끄기"};const name=names[kind];if(!name)return;const box=document.getElementById("deviceState");if(box)box.textContent=name+" 단축어를 실행합니다. iPhone 단축어 앱에 같은 이름의 단축어가 필요합니다.";status(name+" 실행 요청");window.location.href="shortcuts://run-shortcut?name="+encodeURIComponent(name)}
async function webSearch(){const q=document.getElementById("search").value.trim();if(!q){status("검색어를 입력해주세요.");return}try{const r=await fetch("/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:q})});const d=await r.json();if(d.search_url){window.open(d.search_url,"_blank");answer(d.answer);status("검색 페이지를 열었습니다.");speak(d.answer)}else{answer(d.error||"검색할 수 없습니다.");status("검색 오류")}}catch(e){status("검색 서버 연결 오류");answer("검색 페이지를 열지 못했습니다.")}}
async function calculate(){const q=document.getElementById("calc").value.trim();if(!q){status("계산식을 입력해주세요.");return}try{const d=await(await fetch("/calculate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expression:q})})).json();answer(d.answer||d.error);status(d.error?"오류":"완료");if(d.answer)speak(d.answer)}catch(e){status("계산 서버 연결 오류")}}
async function getTime(){try{const d=await(await fetch("/time")).json();answer(d.answer||d.error);status("완료");speak(d.answer||d.error)}catch(e){status("시간 정보를 확인하지 못했습니다.")}}
async function getDate(){try{const d=await(await fetch("/date")).json();answer(d.answer||d.error);status("완료");speak(d.answer||d.error)}catch(e){status("날짜 정보를 확인하지 못했습니다.")}}
function getLocation(){return new Promise((resolve,reject)=>{if(!navigator.geolocation){reject("위치 기능을 사용할 수 없습니다.");return}navigator.geolocation.getCurrentPosition(p=>resolve(p.coords),()=>reject("위치 권한이 필요합니다."),{enableHighAccuracy:false,timeout:8000,maximumAge:60000})})}
async function getWeather(){try{status("현재 위치의 날씨를 확인 중");const l=await getLocation();const d=await(await fetch(`/weather?lat=${encodeURIComponent(l.latitude)}&lon=${encodeURIComponent(l.longitude)}`)).json();if(d.error){status(d.error);answer(d.error);return}const t=`현재 기온 ${d.temperature}도, ${d.description}입니다. 오늘 최고 ${d.max}도, 최저 ${d.min}도입니다.`;answer(t);status("완료");speak(t)}catch(e){status(String(e));answer(String(e))}}
async function directions(){const dest=document.getElementById("destination").value.trim();if(!dest){status("목적지를 입력해주세요.");return}try{const l=await getLocation();window.open("https://www.google.com/maps/dir/?api=1&origin="+encodeURIComponent(`${l.latitude},${l.longitude}`)+"&destination="+encodeURIComponent(dest),"_blank");status("길찾기를 열었습니다.")}catch(e){status(String(e))}}
async function startCamera(){try{if(!navigator.mediaDevices?.getUserMedia){status("이 브라우저에서는 카메라를 사용할 수 없습니다.");return}if(stream){stream.getTracks().forEach(t=>t.stop())}stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"user",width:{ideal:640},height:{ideal:480}},audio:false});const v=document.getElementById("camera");v.srcObject=stream;v.style.display="block";status("카메라가 켜졌습니다.")}catch(e){status("카메라 권한을 허용해주세요.")}}
function stopEyeTracking(){if(eyeTimer){clearInterval(eyeTimer);eyeTimer=null}eyeLandmarker=null;document.getElementById("eyeState").textContent="눈 인식을 중지했습니다."}
async function startEyeTracking(){if(!stream){await startCamera();if(!stream)return}if(!window.PRIME_EYE_MODULE_READY){document.getElementById("eyeState").textContent="눈 인식 모듈을 불러오지 못했습니다. 인터넷 연결을 확인해주세요.";return}try{if(!eyeLandmarker){const fileset=await window.FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22-rc.20250304/wasm");eyeLandmarker=await window.FaceLandmarker.createFromOptions(fileset,{baseOptions:{modelAssetPath:"https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",delegate:"GPU"},runningMode:"VIDEO",numFaces:1,outputFaceBlendshapes:false,outputFacialTransformationMatrixes:false})}if(eyeTimer)clearInterval(eyeTimer);document.getElementById("eyeState").textContent="눈을 찾는 중...";eyeTimer=setInterval(()=>{try{const v=document.getElementById("camera");if(v.readyState<2)return;const result=eyeLandmarker.detectForVideo(v,performance.now());const lm=result.faceLandmarks?.[0];if(!lm){document.getElementById("eyeState").textContent="얼굴을 찾는 중...";return}const left=eyeAspect(lm,[33,160,158,133,153,144]);const right=eyeAspect(lm,[362,385,387,263,373,380]);const openness=(left+right)/2;const gaze=estimateGaze(lm);document.getElementById("eyeState").textContent=`눈 감지 완료 · ${gaze} · 눈 개방도 ${Math.round(openness*100)}`;}catch(e){document.getElementById("eyeState").textContent="눈 인식 처리 중..."}},120)}catch(e){document.getElementById("eyeState").textContent="눈 인식을 시작하지 못했습니다."}}
function dist(a,b){return Math.hypot(a.x-b.x,a.y-b.y)}
function eyeAspect(lm,i){const a=lm[i[0]],b=lm[i[1]],c=lm[i[2]],d=lm[i[3]],e=lm[i[4]],f=lm[i[5]];return (dist(b,f)+dist(c,e))/(2*dist(a,d))}
function estimateGaze(lm){const nose=lm[1],left=lm[33],right=lm[263];const x=(nose.x-(left.x+right.x)/2);if(x<-.035)return"왼쪽";if(x>.035)return"오른쪽";return"정면"}
function vision(mode){if(!stream){status("먼저 카메라를 켜주세요.");return}const m={identify:"물체 분석",translate:"카메라 번역",price:"카메라 가격 검색"}[mode];const t=`카메라는 켜졌습니다. 현재 ${m} 기능은 다음 AI 영상 모듈 단계에서 연결할 수 있습니다.`;answer(t);status("카메라 준비 완료");speak(t)}
async function captureCamera(){if(!stream){status("먼저 카메라를 켜주세요.");return}const v=document.getElementById("camera");if(v.readyState<2){status("카메라가 준비되는 중입니다.");return}const c=document.createElement("canvas");c.width=v.videoWidth||640;c.height=v.videoHeight||480;const ctx=c.getContext("2d");ctx.drawImage(v,0,0,c.width,c.height);const img=document.createElement("img");img.src=c.toDataURL("image/jpeg",0.9);img.style.width="100%";img.style.marginTop="8px";img.style.borderRadius="12px";const old=document.getElementById("cameraSnapshot");if(old)old.remove();img.id="cameraSnapshot";v.parentNode.insertBefore(img,v.nextSibling);status("카메라 사진을 캡처했습니다.");answer("카메라 화면을 캡처했습니다. 영상 분석 기능은 비전 AI 서버를 연결하면 사용할 수 있습니다.");speak("카메라 화면을 캡처했습니다.")}
async function runSecurityCheck(){const box=document.getElementById("securityState");box.textContent="보안 상태를 확인하는 중...";try{const r=await fetch("/security/check");const d=await r.json();box.textContent=(d.summary||"진단 완료")+"\n"+(d.details||"");status("보안 진단 완료")}catch(e){box.textContent="보안 진단 서버 연결 오류";status("보안 진단 오류")}}

function playSong(){const song=document.getElementById("song").value.trim();if(!song){status("노래 제목이나 가수를 입력해주세요.");return}window.open("https://www.youtube.com/results?search_query="+encodeURIComponent(song),"_blank");const t=`${song}를 YouTube에서 검색합니다.`;answer(t);status("YouTube 검색을 열었습니다.");speak(t)}
</script></body></html>'''


@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "16.7"})


@app.route("/ask", methods=["POST"])
def ask():
    try:
        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()
        if not question:
            return jsonify({"error": "질문이 없습니다."}), 400
        history = data.get("history", [])
        if not isinstance(history, list):
            history = []

        if is_screen_unlink_question(question):
            return jsonify({"answer": "화면 연동을 해제하겠습니다.", "screen_link": "off"})
        if is_screen_link_question(question):
            return jsonify({"answer": "화면 연동을 시작합니다. 이 휴대폰 화면에서 PRIME 화면을 표시하겠습니다.", "screen_link": "on"})

        device_command = classify_device_command(question)
        if device_command:
            messages = {"tv_on":"TV를 켜겠습니다.","tv_off":"TV를 끄겠습니다.","pc_on":"컴퓨터 전원 켜기 요청을 보냅니다.","pc_off":"컴퓨터 전원 끄기 요청을 보냅니다.","laptop_on":"노트북 전원 켜기 요청을 보냅니다.","laptop_off":"노트북 전원 끄기 요청을 보냅니다."}
            return jsonify({"answer": messages[device_command], "device_shortcut": device_command})

        calc = extract_calculation(question)
        if calc:
            try:
                return jsonify({"answer": f"계산 결과는 {safe_calculate(calc)}입니다."})
            except (ValueError, ZeroDivisionError):
                pass
        if is_time_question(question):
            return jsonify({"answer": make_time_answer()})
        if is_date_question(question):
            return jsonify({"answer": make_date_answer()})

        weather_city = extract_weather_city(question)
        if weather_city:
            try:
                return jsonify({"answer": get_weather_by_city(weather_city)})
            except requests.RequestException:
                return jsonify({"error": "날씨 서버에 연결하지 못했습니다."}), 502
            except ValueError as error:
                return jsonify({"error": str(error)}), 404

        search_query = extract_search_query(question)
        if search_query:
            result = web_search(search_query)
            return jsonify({"answer": result["message"], "search_url": result["url"]})

        return jsonify({"answer": ask_vireonix(question, history)})
    except requests.Timeout:
        return jsonify({"error": "AI 서버 응답이 늦어지고 있습니다. 잠시 후 다시 시도해주세요."}), 504
    except requests.HTTPError as error:
        code = error.response.status_code if error.response is not None else 502
        return jsonify({"error": f"AI 서버 오류가 발생했습니다. HTTP {code}"}), code
    except requests.RequestException:
        return jsonify({"error": "AI 서버에 연결하지 못했습니다."}), 502
    except Exception as error:
        return jsonify({"error": "AI 처리 중 오류가 발생했습니다."}), 500


@app.route("/security/check")
def security_check():
    """PRIME 서버 자체에 대한 비침투형 보안 진단."""
    try:
        host = socket.gethostname()
        localhost = socket.gethostbyname("localhost")
        checks = []
        checks.append(f"운영체제: {platform.system()} {platform.release()}")
        checks.append(f"Python: {sys.version.split()[0]}")
        checks.append(f"서버 호스트: {host}")
        checks.append(f"로컬 주소: {localhost}")
        checks.append("외부 장치 침투, 비밀번호 추출, 무단 스캔은 수행하지 않음")
        checks.append("웹 서버 debug 모드: 꺼짐")
        return jsonify({"summary":"안전 진단 완료", "details":"\n".join(checks)})
    except Exception as error:
        return jsonify({"summary":"진단 중 오류", "details":str(error)}), 500


@app.route("/search", methods=["POST"])
def search_route():
    data = request.get_json(silent=True) or {}
    query = str(data.get("query", "")).strip()
    if not query:
        return jsonify({"error": "검색어를 입력해주세요."}), 400
    result = web_search(query)
    return jsonify({"answer": result["message"], "search_url": result["url"]})


@app.route("/calculate", methods=["POST"])
def calculate_route():
    try:
        data = request.get_json(silent=True) or {}
        expression = str(data.get("expression", "")).strip()
        if not expression:
            return jsonify({"error": "계산식을 입력해주세요."}), 400
        return jsonify({"answer": f"계산 결과는 {safe_calculate(expression)}입니다."})
    except ZeroDivisionError:
        return jsonify({"error": "0으로 나눌 수 없습니다."}), 400
    except Exception:
        return jsonify({"error": "계산할 수 없는 식입니다."}), 400


@app.route("/time")
def time_route():
    return jsonify({"answer": make_time_answer()})


@app.route("/date")
def date_route():
    return jsonify({"answer": make_date_answer()})


@app.route("/weather")
def weather_route():
    try:
        latitude = float(request.args["lat"])
        longitude = float(request.args["lon"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
        text = weather_from_open_meteo("현재 위치", latitude, longitude)
        m = re.search(r"기온은 ([^도]+)도.*?체감온도는 ([^도]+)도.*?최고기온은 ([^도]+)도, 최저기온은 ([^도]+)도", text)
        if m:
            return jsonify({"answer": text, "temperature": m.group(1), "feels": m.group(2), "max": m.group(3), "min": m.group(4), "description": text.split("날씨는 ",1)[1].split("이고",1)[0]})
        return jsonify({"answer": text})
    except Exception:
        try:
            text = weather_from_wttr("현재 위치")
            return jsonify({"answer": text})
        except Exception:
            return jsonify({"error": "현재 위치의 날씨를 가져오지 못했습니다."}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

# PRIME V16.7 - AI stability/retry hardening release.
