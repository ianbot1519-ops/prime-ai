import os
import requests
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

HTML = r"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRIME V10</title>
<style>
body{margin:0;background:#05080d;color:#eaf3ff;font-family:Arial,sans-serif}
.wrap{max-width:760px;margin:auto;padding:20px}
h1{text-align:center;letter-spacing:6px;margin:8px 0}
.sub{text-align:center;color:#91a7ba;margin-bottom:18px}
button,input,textarea{width:100%;box-sizing:border-box;border-radius:12px;padding:13px;margin:5px 0;font-size:16px}
button{border:1px solid #31506b;background:#0d1721;color:white}
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
<div class="sub">Personal Response & Intelligence Management Engine · V10</div>

<button onclick="startWake()">PRIME 호출 대기</button>
<button onclick="askVoice()">말하기</button>

<textarea id="question" placeholder="질문을 입력하세요"></textarea>
<button onclick="askText()">질문하기</button>

<button onclick="getWeather()">날씨</button>

<input id="destination" placeholder="목적지">
<button onclick="directions()">길찾기</button>

<button onclick="startCamera()">카메라 켜기</button>
<video id="camera" autoplay playsinline></video>

<button onclick="vision('identify')">물체 분석</button>
<button onclick="vision('translate')">번역</button>
<button onclick="vision('price')">가격 검색</button>

<input id="song" placeholder="노래 제목 또는 가수">
<button onclick="playSong()">노래 검색 / 재생</button>

<div id="status"></div>
<div id="answer"></div>

<button onclick="speakAnswer()">답변 듣기</button>

</div>

<script>
let recognition = null;
let stream = null;
let lastAnswer = "";

function status(t) {
    document.getElementById("status").textContent = t;
}

function answer(t) {
    lastAnswer = t;
    document.getElementById("answer").textContent = t;
}

function speak(t) {
    if (!("speechSynthesis" in window)) return;

    speechSynthesis.cancel();

    const u = new SpeechSynthesisUtterance(t);

    u.lang = "ko-KR";
    u.rate = 0.95;
    u.pitch = 0.75;

    const voices = speechSynthesis.getVoices();

    const ko = voices.filter(function(v) {
        return v.lang &&
               v.lang.toLowerCase().startsWith("ko");
    });

    const male = ko.find(function(v) {
        return /male|man|남성|남자/i.test(v.name);
    });

    if (male) {
        u.voice = male;
    } else if (ko.length) {
        u.voice = ko[0];
    }

    speechSynthesis.speak(u);
}

function speakAnswer() {
    if (lastAnswer) {
        speak(lastAnswer);
    }
}

function makeRecognition() {
    const R =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;

    if (!R) {
        status("이 브라우저는 음성 인식을 지원하지 않습니다.");
        return null;
    }

    const r = new R();

    r.lang = "ko-KR";
    r.interimResults = false;
    r.continuous = false;

    return r;
}

function startWake() {
    recognition = makeRecognition();

    if (!recognition) return;

    status("PRIME 호출을 기다리는 중...");

    recognition.onresult = function(e) {

        const t =
            e.results[0][0].transcript
            .trim()
            .toLowerCase();

        if (
            t.includes("prime") ||
            t.includes("프라임")
        ) {
            status("네. 말씀하세요.");
            speak("네. 말씀하세요.");

            setTimeout(
                askVoice,
                1200
            );

        } else {
            status("PRIME이라고 말씀해주세요.");
        }
    };

    recognition.onerror = function() {
        status("호출 대기가 종료되었습니다.");
    };

    recognition.start();
}

function askVoice() {
    recognition = makeRecognition();

    if (!recognition) return;

    status("듣고 있습니다...");

    recognition.onresult = function(e) {

        const q =
            e.results[0][0].transcript;

        document.getElementById(
            "question"
        ).value = q;

        ask(q);
    };

    recognition.onerror = function() {
        status("음성을 듣지 못했습니다.");
    };

    recognition.start();
}

async function askText() {

    const q =
        document.getElementById(
            "question"
        ).value.trim();

    if (q) {
        await ask(q);
    }
}

async function ask(q) {

    status("PRIME 처리 중...");

    try {

        const r =
            await fetch(
                "/ask",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        question: q
                    })
                }
            );

        const d = await r.json();

        const a =
            d.answer ||
            d.error ||
            "오류가 발생했습니다.";

        answer(a);
        status("완료");
        speak(a);

    } catch (e) {

        status("서버 연결 오류");
    }
}

function getLocation() {

    return new Promise(
        function(resolve, reject) {

            if (!navigator.geolocation) {

                reject(
                    "위치 기능을 사용할 수 없습니다."
                );

                return;
            }

            navigator.geolocation.getCurrentPosition(
                function(p) {
                    resolve(p.coords);
                },
                function() {
                    reject(
                        "위치 권한이 필요합니다."
                    );
                }
            );
        }
    );
}

async function getWeather() {

    try {

        status(
            "현재 위치의 날씨를 확인 중..."
        );

        const c =
            await getLocation();

        const r =
            await fetch(
                "/weather?lat=" +
                c.latitude +
                "&lon=" +
                c.longitude
            );

        const d =
            await r.json();

        if (d.error) {
            status(d.error);
            return;
        }

        const t =
            "현재 기온 " +
            d.temperature +
            "도, " +
            d.description +
            "입니다. 오늘 최고 " +
            d.max +
            "도, 최저 " +
            d.min +
            "도입니다.";

        answer(t);
        status("완료");
        speak(t);

    } catch (e) {

        status(String(e));
    }
}

async function directions() {

    const dest =
        document.getElementById(
            "destination"
        ).value.trim();

    if (!dest) {

        status(
            "목적지를 입력해주세요."
        );

        return;
    }

    try {

        const c =
            await getLocation();

        const origin =
            c.latitude +
            "," +
            c.longitude;

        const url =
            "https://www.google.com/maps/dir/?api=1" +
            "&origin=" +
            encodeURIComponent(origin) +
            "&destination=" +
            encodeURIComponent(dest);

        window.open(
            url,
            "_blank"
        );

        status(
            "길찾기를 열었습니다."
        );

    } catch (e) {

        status(String(e));
    }
}

async function startCamera() {

    try {

        stream =
            await navigator.mediaDevices.getUserMedia(
                {
                    video: {
                        facingMode:
                            "environment"
                    },
                    audio: false
                }
            );

        const v =
            document.getElementById(
                "camera"
            );

        v.srcObject = stream;
        v.style.display = "block";

        status(
            "카메라가 켜졌습니다."
        );

    } catch (e) {

        status(
            "카메라 권한을 허용해주세요."
        );
    }
}

function cameraData() {

    if (!stream) return null;

    const v =
        document.getElementById(
            "camera"
        );

    const c =
        document.createElement(
            "canvas"
        );

    c.width =
        v.videoWidth || 640;

    c.height =
        v.videoHeight || 480;

    c.getContext(
        "2d"
    ).drawImage(
        v,
        0,
        0,
        c.width,
        c.height
    );

    return c.toDataURL(
        "image/jpeg",
        0.8
    );
}

async function vision(mode) {

    const image =
        cameraData();

    if (!image) {

        status(
            "먼저 카메라를 켜주세요."
        );

        return;
    }

    status(
        "카메라 화면을 분석 중..."
    );

    try {

        const r =
            await fetch(
                "/vision",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        image: image,
                        mode: mode
                    })
                }
            );

        const d =
            await r.json();

        const a =
            d.answer ||
            d.error ||
            "분석 실패";

        answer(a);
        status("완료");
        speak(a);

    } catch (e) {

        status(
            "카메라 분석 오류"
        );
    }
}

function playSong() {

    const song =
        document.getElementById(
            "song"
        ).value.trim();

    if (!song) {

        status(
            "노래 제목이나 가수를 입력해주세요."
        );

        return;
    }

    const url =
        "https://www.youtube.com/results?search_query=" +
        encodeURIComponent(song);

    window.open(
        url,
        "_blank"
    );

    const t =
        song +
        "를 YouTube에서 검색합니다.";

    answer(t);
    status(
        "YouTube 검색을 열었습니다."
    );
    speak(t);
}
</script>
</body>
</html>
"""


def response_text(prompt, web=False):

    kwargs = {
        "model": "gpt-5.6-luna",
        "instructions": (
            "당신은 PRIME이라는 개인 AI 비서다. "
            "한국어로 답하고 이해하기 쉽게 정확하게 설명한다."
        ),
        "input": prompt
    }

    if web:
        kwargs["tools"] = [
            {
                "type": "web_search"
            }
        ]

    response = client.responses.create(
        **kwargs
    )

    return response.output_text


@app.route("/")
def home():

    return render_template_string(
        HTML
    )


@app.route(
    "/ask",
    methods=["POST"]
)
def ask():

    try:

        data = (
            request.get_json(
                silent=True
            ) or {}
        )

        question = str(
            data.get(
                "question",
                ""
            )
        ).strip()

        if not question:

            return jsonify(
                {
                    "error":
                    "질문이 없습니다."
                }
            ), 400

        web_words = [
            "가격",
            "얼마",
            "현재",
            "오늘",
            "최신",
            "뉴스",
            "시장가",
            "노래"
        ]

        use_web = any(
            word in question
            for word in web_words
        )

        result = response_text(
            question,
            use_web
        )

        return jsonify(
            {
                "answer": result
            }
        )

    except Exception as e:

        return jsonify(
            {
                "error":
                "AI 오류: " +
                str(e)
            }
        ), 500


@app.route("/weather")
def weather():

    try:

        lat = float(
            request.args["lat"]
        )

        lon = float(
            request.args["lon"]
        )

        params = {
            "latitude": lat,
            "longitude": lon,
            "current":
                "temperature_2m,weather_code",
            "daily":
                "temperature_2m_max,temperature_2m_min",
            "timezone":
                "Asia/Seoul"
        }

        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=15
        )

        r.raise_for_status()

        data = r.json()

        current = data["current"]
        daily = data["daily"]

        descriptions = {
            0: "맑음",
            1: "대체로 맑음",
            2: "부분적으로 흐림",
            3: "흐림",
            45: "안개",
            48: "짙은 안개",
            51: "이슬비",
            53: "이슬비",
            55: "이슬비",
            61: "비",
            63: "비",
            65: "강한 비",
            71: "눈",
            73: "눈",
            75: "강한 눈",
            80: "소나기",
            81: "소나기",
            82: "강한 소나기",
            95: "뇌우"
        }

        return jsonify(
            {
                "temperature":
                    current[
                        "temperature_2m"
                    ],

                "description":
                    descriptions.get(
                        current[
                            "weather_code"
                        ],
                        "날씨 정보"
                    ),

                "max":
                    daily[
                        "temperature_2m_max"
                    ][0],

                "min":
                    daily[
                        "temperature_2m_min"
                    ][0]
            }
        )

    except Exception as e:

        return jsonify(
            {
                "error":
                "날씨 오류: " +
                str(e)
            }
        ), 500


@app.route(
    "/vision",
    methods=["POST"]
)
def vision():

    try:

        data = (
            request.get_json(
                silent=True
            ) or {}
        )

        image = data.get(
            "image",
            ""
        )

        mode = data.get(
            "mode",
            "identify"
        )

        if not image.startswith(
            "data:image/"
        ):

            return jsonify(
                {
                    "error":
                    "이미지 데이터가 없습니다."
                }
            ), 400

        prompts = {

            "identify":
                "사진 속 물체를 식별해줘. "
                "브랜드, 종류, 모델명과 특징을 설명하고 "
                "확실하지 않은 내용은 추정이라고 말해줘.",

            "translate":
                "사진 속 글자를 읽고 "
                "자연스러운 한국어로 번역해줘. "
                "읽기 어려운 부분은 명확히 알려줘.",

            "price":
                "사진 속 제품을 식별해줘. "
                "브랜드와 모델을 추정하고 "
                "현재 한국 판매 가격대를 웹 검색으로 확인해줘. "
                "확실하지 않은 식별은 추정이라고 말해줘."
        }

        tools = []

        if mode == "price":

            tools = [
                {
                    "type": "web_search"
                }
            ]

        response = client.responses.create(
            model="gpt-5.6-luna",

            instructions=(
                "당신은 PRIME의 카메라 분석 담당이다. "
                "한국어로 답한다."
            ),

            tools=tools,

            input=[
                {
                    "role": "user",

                    "content": [
                        {
                            "type":
                            "input_text",

                            "text":
                            prompts.get(
                                mode,
                                prompts["identify"]
                            )
                        },

                        {
                            "type":
                            "input_image",

                            "image_url":
                            image,

                            "detail":
                            "auto"
                        }
                    ]
                }
            ]
        )

        return jsonify(
            {
                "answer":
                response.output_text
            }
        )

    except Exception as e:

        return jsonify(
            {
                "error":
                "카메라 분석 오류: " +
                str(e)
            }
        ), 500


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000
            )
        )
    )
