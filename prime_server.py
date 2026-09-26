import os
import re
import ast
import operator
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
VIREONIX_URL = "https://vireonix.ai/v1/chat/completions"

def clean_ai_response(text):
    if not text:
        return ""
    text = str(text)
    emoji_pattern = re.compile(
        "[\U0001F300-\U0001FAFF\U00002700-\U000027BF"
        "\U00002600-\U000026FF\U0001F1E0-\U0001F1FF"
        "\U0001F900-\U0001F9FF\u200d\ufe0f\u20e3]",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def ask_vireonix(question):
    system_prompt = '''
당신은 PRIME이라는 개인 AI 비서다.
항상 한국어로 답한다.
차분하고 정중하게 말한다.
이모지와 이모티콘을 사용하지 않는다.
장식용 특수문자를 사용하지 않는다.
불필요한 감탄사를 사용하지 않는다.
사용자가 요청하지 않은 개인적인 생각이나 감정을 임의로 추가하지 않는다.
모르는 것은 모른다고 정확하게 말한다.
답변은 이해하기 쉽게 작성한다.
'''
    payload = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    }
    response = requests.post(VIREONIX_URL, json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()
    return clean_ai_response(data["choices"][0]["message"]["content"])

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


def extract_search_query(q):
    cleaned = re.sub(r"^(프라임[,\s]*)", "", q.strip(), flags=re.I)
    patterns = [
        r"(?:인터넷에서|웹에서|온라인에서)\s*(?:검색해줘|검색해 줘|검색해|찾아줘|찾아 줘|찾아)\s*(.*)$",
        r"(?:검색해줘|검색해 줘|검색해|찾아줘|찾아 줘|찾아)\s*(.*)$",
    ]
    for pattern in patterns:
        m = re.search(pattern, cleaned, flags=re.I)
        if m:
            query = m.group(1).strip(" :：")
            if query:
                return query
    return None

def web_search(query):
    """외부 검색 서버를 PRIME의 Flask 워커가 직접 기다리지 않도록 검색 주소만 만든다."""
    query = str(query).strip()
    if len(query) > 300:
        query = query[:300]

    if any(word in query for word in ["뉴스", "기사", "속보", "시사"]):
        url = "https://www.google.com/search?tbm=nws&q=" + quote_plus(query)
        return {
            "message": f"뉴스 검색을 준비했습니다: {query}",
            "url": url
        }

    url = "https://www.google.com/search?q=" + quote_plus(query)
    return {
        "message": f"웹 검색을 준비했습니다: {query}",
        "url": url
    }

def safe_calculate(expression):
    expression = expression.strip()
    expression = expression.replace("×", "*").replace("÷", "/").replace("−", "-")
    expression = re.sub(r"곱하기", "*", expression)
    expression = re.sub(r"더하기", "+", expression)
    expression = re.sub(r"빼기", "-", expression)
    expression = re.sub(r"나누기", "/", expression)
    expression = expression.replace(",", "")
    if len(expression) > 100 or not re.fullmatch(r"[0-9+\-*/%.() ]+", expression):
        raise ValueError("계산할 수 없는 식입니다.")
    tree = ast.parse(expression, mode="eval")
    allowed_bin = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    allowed_unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_bin:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("지수가 너무 큽니다.")
            return allowed_bin[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_unary:
            return allowed_unary[type(node.op)](ev(node.operand))
        raise ValueError("계산할 수 없는 식입니다.")

    result = ev(tree)
    if isinstance(result, float) and result.is_integer():
        return str(int(result))
    return str(round(result, 10))

def extract_calculation(q):
    cleaned = re.sub(r"^(프라임[,\s]*)", "", q.strip(), flags=re.I)
    patterns = [
        r"(?:계산해줘|계산해 줘|계산해|계산)\s*[:：]?\s*(.+)$",
        r"(?:얼마야|몇이야|값은)\s*[:：]?\s*(.+)$",
    ]
    for pattern in patterns:
        m = re.search(pattern, cleaned)
        if m:
            candidate = m.group(1).strip()
            if re.search(r"\d", candidate) and re.search(r"[+\-*/×÷%]|더하기|빼기|곱하기|나누기", candidate):
                return candidate
    if re.fullmatch(r"[0-9+\-*/%.() ×÷−]+", cleaned):
        return cleaned
    return None

HTML = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRIME V13</title>
<style>
body{margin:0;background:#05080d;color:#eaf3ff;font-family:Arial,sans-serif}
.wrap{max-width:760px;margin:auto;padding:20px}
h1{text-align:center;letter-spacing:6px;margin:8px 0}
.sub{text-align:center;color:#91a7ba;margin-bottom:18px}
button,input,textarea{width:100%;box-sizing:border-box;border-radius:12px;padding:13px;margin:5px 0;font-size:16px}
button{border:1px solid #31506b;background:#0d1721;color:white;cursor:pointer}
input,textarea{border:1px solid #31506b;background:#091019;color:white}
textarea{min-height:90px}
#status{text-align:center;color:#75bcff;min-height:24px;margin:10px 0}
#answer{white-space:pre-wrap;background:#091019;border:1px solid #20384d;border-radius:12px;padding:14px;min-height:70px}
video{width:100%;border-radius:12px;margin-top:8px;display:none}
</style>
</head>
<body>
<div class="wrap">
<h1>PRIME</h1>
<div class="sub">Personal Response &amp; Intelligence Management Engine V14.2</div>
<button onclick="startWake()">PRIME 호출 대기</button>
<button onclick="askVoice()">말하기</button>
<textarea id="question" placeholder="질문을 입력하세요"></textarea>
<button onclick="askText()">질문하기</button>
<input id="calc" placeholder="계산식 예: 25 + 37">
<button onclick="calculate()">계산하기</button> <input id="search" placeholder="검색어"> <button onclick="webSearch()">웹 검색</button>
<button onclick="getTime()">현재 시간</button>
<button onclick="getDate()">오늘 날짜</button>
<button onclick="getWeather()">날씨</button>
<input id="destination" placeholder="목적지">
<button onclick="directions()">길찾기</button>
<button onclick="startCamera()">카메라 켜기</button>
<video id="camera" autoplay playsinline></video>
<button onclick="vision('identify')">물체 분석</button>
<button onclick="vision('translate')">번역</button>
<button onclick="vision('price')">가격 검색</button>
<input id="song" placeholder="노래 제목 또는 가수">
<button onclick="playSong()">노래 검색 재생</button>
<div id="status"></div>
<div id="answer"></div>
<button onclick="speakAnswer()">답변 듣기</button>
</div>
<script>
let recognition=null,stream=null,lastAnswer="";
function status(text){document.getElementById("status").textContent=text}
function answer(text){lastAnswer=text;document.getElementById("answer").textContent=text}
function speak(text){if(!("speechSynthesis" in window))return;speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang="ko-KR";u.rate=.95;u.pitch=.75;const v=speechSynthesis.getVoices().filter(x=>x.lang&&x.lang.toLowerCase().startsWith("ko"));if(v.length)u.voice=v[0];speechSynthesis.speak(u)}
function speakAnswer(){if(lastAnswer)speak(lastAnswer)}
function makeRecognition(){const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R){status("이 브라우저는 음성 인식을 지원하지 않습니다.");return null}const r=new R();r.lang="ko-KR";r.interimResults=false;r.continuous=false;return r}
function startWake(){recognition=makeRecognition();if(!recognition)return;status("PRIME 호출을 기다리는 중");recognition.onresult=e=>{const t=e.results[0][0].transcript.trim().toLowerCase();if(t.includes("prime")||t.includes("프라임")){status("네. 말씀하세요.");speak("네. 말씀하세요.");setTimeout(askVoice,1200)}else status("PRIME이라고 말씀해주세요.")};recognition.onerror=()=>status("호출 대기가 종료되었습니다.");try{recognition.start()}catch(e){status("음성 인식을 시작할 수 없습니다.")}}
function askVoice(){recognition=makeRecognition();if(!recognition)return;status("듣고 있습니다");recognition.onresult=e=>{const q=e.results[0][0].transcript;document.getElementById("question").value=q;ask(q)};recognition.onerror=()=>status("음성을 듣지 못했습니다.");try{recognition.start()}catch(e){status("음성 인식을 시작할 수 없습니다.")}}
async function askText(){const q=document.getElementById("question").value.trim();if(q)await ask(q)}
async function ask(question){status("PRIME 처리 중");try{const r=await fetch("/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question})});const d=await r.json();const a=d.answer||d.error||"오류가 발생했습니다.";answer(a);if(d.search_url){window.open(d.search_url,"_blank");status("검색 페이지를 열었습니다.");speak(a);return}status("완료");speak(a)}catch(e){status("서버 연결 오류");answer("서버에 연결하지 못했습니다.")}}
async function webSearch(){const q=document.getElementById("search").value.trim();if(!q){status("검색어를 입력해주세요.");return}status("검색 페이지 준비 중");try{const r=await fetch("/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:q})});const d=await r.json();if(d.search_url){window.open(d.search_url,"_blank");answer(d.answer||"웹 검색을 준비했습니다.");status("검색 페이지를 열었습니다.");speak(d.answer||"웹 검색을 준비했습니다.");return}answer(d.error||"검색할 수 없습니다.");status("검색 오류")}catch(e){status("검색 서버 연결 오류");answer("검색 페이지를 열지 못했습니다.")}}\nasync function calculate(){const q=document.getElementById("calc").value.trim();if(!q){status("계산식을 입력해주세요.");return}status("계산 중");try{const r=await fetch("/calculate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({expression:q})});const d=await r.json();const a=d.answer||d.error||"계산할 수 없습니다.";answer(a);status(d.error?"오류":"완료");if(!d.error)speak(a)}catch(e){status("계산 서버 연결 오류")}}
async function getTime(){status("현재 시간을 확인하는 중");try{const d=await (await fetch("/time")).json();answer(d.answer||d.error);status("완료");speak(d.answer||d.error)}catch(e){status("시간 정보를 확인하지 못했습니다.")}}
async function getDate(){status("오늘 날짜를 확인하는 중");try{const d=await (await fetch("/date")).json();answer(d.answer||d.error);status("완료");speak(d.answer||d.error)}catch(e){status("날짜 정보를 확인하지 못했습니다.")}}
function getLocation(){return new Promise((resolve,reject)=>{if(!navigator.geolocation){reject("위치 기능을 사용할 수 없습니다.");return}navigator.geolocation.getCurrentPosition(p=>resolve(p.coords),()=>reject("위치 권한이 필요합니다."))})}
async function getWeather(){try{status("현재 위치의 날씨를 확인 중");const l=await getLocation();const d=await (await fetch(`/weather?lat=${encodeURIComponent(l.latitude)}&lon=${encodeURIComponent(l.longitude)}`)).json();if(d.error){status(d.error);return}const t=`현재 기온 ${d.temperature}도, ${d.description}입니다. 오늘 최고 ${d.max}도, 최저 ${d.min}도입니다.`;answer(t);status("완료");speak(t)}catch(e){status(String(e))}}
async function directions(){const dest=document.getElementById("destination").value.trim();if(!dest){status("목적지를 입력해주세요.");return}try{const l=await getLocation();const origin=`${l.latitude},${l.longitude}`;const url="https://www.google.com/maps/dir/?api=1&origin="+encodeURIComponent(origin)+"&destination="+encodeURIComponent(dest);window.open(url,"_blank");status("길찾기를 열었습니다.")}catch(e){status(String(e))}}
async function startCamera(){try{if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){status("이 브라우저에서는 카메라를 사용할 수 없습니다.");return}stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"},audio:false});const v=document.getElementById("camera");v.srcObject=stream;v.style.display="block";status("카메라가 켜졌습니다.")}catch(e){status("카메라 권한을 허용해주세요.")}}
function vision(mode){if(!stream){status("먼저 카메라를 켜주세요.");return}const m={identify:"물체 분석",translate:"카메라 번역",price:"카메라 가격 검색"}[mode];const t=`카메라는 켜졌습니다. 현재 ${m} 기능은 아직 AI 서버에 연결되지 않았습니다.`;answer(t);status("카메라 기능 준비 중");speak(t)}
function playSong(){const song=document.getElementById("song").value.trim();if(!song){status("노래 제목이나 가수를 입력해주세요.");return}window.open("https://www.youtube.com/results?search_query="+encodeURIComponent(song),"_blank");const t=`${song}를 YouTube에서 검색합니다.`;answer(t);status("YouTube 검색을 열었습니다.");speak(t)}
</script>
</body>
</html>'''

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/ask", methods=["POST"])
def ask():
    try:
        data=request.get_json(silent=True) or {}
        question=str(data.get("question","")).strip()
        if not question:return jsonify({"error":"질문이 없습니다."}),400
        calc=extract_calculation(question)
        if calc:
            try:return jsonify({"answer":f"계산 결과는 {safe_calculate(calc)}입니다."})
            except (ValueError, ZeroDivisionError):pass
        if is_time_question(question):return jsonify({"answer":make_time_answer()})
        if is_date_question(question):return jsonify({"answer":make_date_answer()})
        search_query = extract_search_query(question)
        if search_query:
            result = web_search(search_query)
            return jsonify({
                "answer": result["message"],
                "search_url": result["url"]
            })
        return jsonify({"answer": ask_vireonix(question)})
    except requests.HTTPError as error:
        if error.response is not None:
            try:detail=error.response.json()
            except ValueError:detail=error.response.text
            return jsonify({"error":"Vireonix 오류: "+str(detail)}),error.response.status_code
        return jsonify({"error":"Vireonix 서버 오류"}),500
    except requests.RequestException as error:
        return jsonify({"error":"Vireonix 연결 오류: "+str(error)}),502
    except Exception as error:
        return jsonify({"error":"AI 오류: "+str(error)}),500

@app.route("/search", methods=["POST"])
def search_route():
    try:
        data = request.get_json(silent=True) or {}
        query = str(data.get("query", "")).strip()
        if not query:
            return jsonify({"error": "검색어를 입력해주세요."}), 400
        result = web_search(query)
        return jsonify({
            "answer": result["message"],
            "search_url": result["url"]
        })
    except requests.RequestException as error:
        return jsonify({"error": "웹 검색 서버 연결 오류: " + str(error)}), 502
    except Exception as error:
        return jsonify({"error": "웹 검색 오류: " + str(error)}), 500

@app.route("/calculate", methods=["POST"])
def calculate_route():
    try:
        data=request.get_json(silent=True) or {}
        expression=str(data.get("expression","")).strip()
        if not expression:return jsonify({"error":"계산식을 입력해주세요."}),400
        result=safe_calculate(expression)
        return jsonify({"answer":f"계산 결과는 {result}입니다."})
    except ZeroDivisionError:
        return jsonify({"error":"0으로 나눌 수 없습니다."}),400
    except Exception:
        return jsonify({"error":"계산할 수 없는 식입니다."}),400

@app.route("/time")
def time():
    return jsonify({"answer":make_time_answer()})

@app.route("/date")
def date():
    return jsonify({"answer":make_date_answer()})

@app.route("/weather")
def weather():
    try:
        latitude=float(request.args["lat"]);longitude=float(request.args["lon"])
        params={"latitude":latitude,"longitude":longitude,"current":"temperature_2m,weather_code","daily":"temperature_2m_max,temperature_2m_min","timezone":"Asia/Seoul"}
        r=requests.get("https://api.open-meteo.com/v1/forecast",params=params,timeout=15);r.raise_for_status();d=r.json()
        c=d["current"];daily=d["daily"]
        descriptions={0:"맑음",1:"대체로 맑음",2:"부분적으로 흐림",3:"흐림",45:"안개",48:"짙은 안개",51:"이슬비",53:"이슬비",55:"이슬비",61:"비",63:"비",65:"강한 비",71:"눈",73:"눈",75:"강한 눈",80:"소나기",81:"소나기",82:"강한 소나기",95:"뇌우",96:"우박을 동반한 뇌우",99:"우박을 동반한 뇌우"}
        return jsonify({"temperature":c["temperature_2m"],"description":descriptions.get(c["weather_code"],"날씨 정보"),"max":daily["temperature_2m_max"][0],"min":daily["temperature_2m_min"][0]})
    except requests.RequestException as error:return jsonify({"error":"날씨 서버 연결 오류: "+str(error)}),502
    except Exception as error:return jsonify({"error":"날씨 오류: "+str(error)}),500

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
