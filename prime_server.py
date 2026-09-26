import os
import base64
import requests
from urllib.parse import quote

from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI


app = Flask(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


HTML = """
<!DOCTYPE html>
<html lang="ko">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>PRIME</title>

<style>

body {
    background: #050505;
    color: #00aaff;
    font-family: Arial, sans-serif;
    text-align: center;
    padding: 20px;
}

h1 {
    font-size: 40px;
    letter-spacing: 8px;
}

input {
    width: 85%;
    max-width: 500px;
    padding: 15px;
    font-size: 18px;
    background: #111;
    color: white;
    border: 1px solid #0088cc;
    border-radius: 8px;
}

button {
    margin: 7px 4px;
    padding: 13px 20px;
    font-size: 17px;
    background: #0088cc;
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
}

button:hover {
    background: #00aaff;
}

#answer {
    margin: 25px auto;
    max-width: 650px;
    font-size: 20px;
    line-height: 1.6;
}

#status {
    margin-top: 15px;
    color: #66ccff;
}

#wakeStatus {
    margin-top: 15px;
    color: #00ffcc;
}

#cameraArea {
    display: none;
    margin: 20px auto;
    max-width: 650px;
}

#camera {
    width: 100%;
    max-width: 600px;
    border: 2px solid #0088cc;
    border-radius: 10px;
}

#locationStatus {
    margin-top: 10px;
    color: #88ddff;
}

</style>

</head>

<body>

<h1>PRIME</h1>

<p>PRIME V8 ONLINE</p>


<input
    id="question"
    placeholder="PRIME에게 질문하세요"
>


<br>


<button onclick="startWakeWord()">
    PRIME 호출 대기
</button>

<button onclick="startListening()">
    말하기
</button>

<button onclick="askPrime()">
    질문하기
</button>


<br>


<button onclick="getWeather()">
    날씨
</button>

<button onclick="openDirections()">
    길찾기
</button>


<br>


<button onclick="startCamera()">
    카메라 켜기
</button>

<button onclick="analyzeObject()">
    물체 분석
</button>

<button onclick="translateCamera()">
    번역
</button>

<button onclick="priceSearch()">
    가격 검색
</button>


<br>


<button onclick="speakAnswer()">
    답변 듣기
</button>


<div id="wakeStatus">
    PRIME 호출 대기 꺼짐
</div>


<div id="locationStatus">
    위치 확인 전
</div>


<div id="status"></div>


<div id="answer"></div>


<div id="cameraArea">

    <video
        id="camera"
        autoplay
        playsinline>
    </video>

</div>


<canvas
    id="snapshot"
    style="display:none;">
</canvas>


<script>

let recognition = null;

let lastAnswer = "";

let selectedVoice = null;

let wakeWordMode = false;

let cameraStream = null;

let lastLocation = null;


// ==========================================
// 음성
// ==========================================

function loadVoices() {

    const voices =
        window.speechSynthesis.getVoices();

    if (!voices || voices.length === 0) {
        return;
    }


    const koreanVoices =
        voices.filter(function(voice) {

            return voice.lang
                .toLowerCase()
                .startsWith("ko");

        });


    if (koreanVoices.length === 0) {

        selectedVoice = null;

        return;

    }


    selectedVoice =
        koreanVoices.find(function(voice) {

            const name =
                voice.name.toLowerCase();

            return (
                name.includes("male") ||
                name.includes("man") ||
                name.includes("남성") ||
                name.includes("남자")
            );

        });


    if (!selectedVoice) {

        selectedVoice =
            koreanVoices[0];

    }

}


window.speechSynthesis.onvoiceschanged =
    loadVoices;


// ==========================================
// 음성 출력
// ==========================================

function speakText(text) {

    if (!("speechSynthesis" in window)) {
        return;
    }


    window.speechSynthesis.cancel();

    loadVoices();


    const speech =
        new SpeechSynthesisUtterance(text);


    speech.lang = "ko-KR";

    speech.rate = 0.95;

    speech.pitch = 0.75;

    speech.volume = 1.0;


    if (selectedVoice) {

        speech.voice =
            selectedVoice;

    }


    speech.onstart = function() {

        document.getElementById("status")
            .innerText =
            "PRIME이 말하고 있습니다...";

    };


    speech.onend = function() {

        document.getElementById("status")
            .innerText =
            "PRIME 온라인";

    };


    window.speechSynthesis.speak(speech);

}


function speakAnswer() {

    if (!lastAnswer) {

        document.getElementById("status")
            .innerText =
            "먼저 PRIME에게 질문해주세요.";

        return;

    }

    speakText(lastAnswer);

}


// ==========================================
// PRIME 호출어
// ==========================================

function startWakeWord() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;


    if (!SpeechRecognition) {

        document.getElementById("status")
            .innerText =
            "이 브라우저에서는 음성 인식을 지원하지 않습니다.";

        return;

    }


    wakeWordMode = true;


    document.getElementById("wakeStatus")
        .innerText =
        "PRIME 호출 대기 중...";


    document.getElementById("status")
        .innerText =
        "PRIME이라고 말해보세요.";


    startWakeRecognition();

}


function startWakeRecognition() {

    if (!wakeWordMode) {
        return;
    }


    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;


    recognition =
        new SpeechRecognition();


    recognition.lang =
        "ko-KR";


    recognition.continuous =
        false;


    recognition.interimResults =
        false;


    try {

        recognition.start();

    } catch (error) {

        console.log(error);

    }


    recognition.onresult =
        function(event) {

            const text =
                event.results[0][0]
                    .transcript
                    .trim();


            if (
                text.includes("PRIME") ||
                text.includes("프라임") ||
                text.includes("프라임아")
            ) {

                wakeWordMode = false;


                document.getElementById(
                    "wakeStatus"
                ).innerText =
                    "PRIME 활성화";


                speakText(
                    "네. 말씀하세요."
                );


                setTimeout(
                    startQuestionListening,
                    1200
                );

            } else {

                setTimeout(
                    startWakeRecognition,
                    300
                );

            }

        };


    recognition.onerror =
        function(event) {

            console.log(
                "Wake error:",
                event.error
            );


            if (wakeWordMode) {

                setTimeout(
                    startWakeRecognition,
                    500
                );

            }

        };


    recognition.onend =
        function() {

            if (wakeWordMode) {

                setTimeout(
                    startWakeRecognition,
                    300
                );

            }

        };

}


// ==========================================
// 호출 후 질문
// ==========================================

function startQuestionListening() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;


    if (!SpeechRecognition) {
        return;
    }


    recognition =
        new SpeechRecognition();


    recognition.lang =
        "ko-KR";


    recognition.continuous =
        false;


    recognition.interimResults =
        false;


    document.getElementById("status")
        .innerText =
        "듣고 있습니다...";


    try {

        recognition.start();

    } catch (error) {

        console.log(error);

    }


    recognition.onresult =
        function(event) {

            const text =
                event.results[0][0]
                    .transcript
                    .trim();


            document.getElementById(
                "question"
            ).value =
                text;


            askPrime();

        };


    recognition.onerror =
        function(event) {

            console.log(
                "Question error:",
                event.error
            );

            startWakeWord();

        };

}


// ==========================================
// 일반 음성 질문
// ==========================================

function startListening() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;


    if (!SpeechRecognition) {
        return;
    }


    recognition =
        new SpeechRecognition();


    recognition.lang =
        "ko-KR";


    recognition.continuous =
        false;


    recognition.interimResults =
        false;


    document.getElementById("status")
        .innerText =
        "PRIME이 듣고 있습니다...";


    try {

        recognition.start();

    } catch (error) {

        console.log(error);

    }


    recognition.onresult =
        function(event) {

            const text =
                event.results[0][0]
                    .transcript;


            document.getElementById(
                "question"
            ).value =
                text;


            askPrime();

        };

}


// ==========================================
// PRIME 질문
// ==========================================

async function askPrime() {

    const question =
        document.getElementById(
            "question"
        ).value.trim();


    if (!question) {
        return;
    }


    document.getElementById(
        "answer"
    ).innerText =
        "PRIME: 생각 중...";


    document.getElementById(
        "status"
    ).innerText =
        "PRIME이 처리하고 있습니다...";


    try {

        const response =
            await fetch(
                "/ask",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            question:
                                question
                        })
                }
            );


        const data =
            await response.json();


        lastAnswer =
            data.answer;


        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            lastAnswer;


        speakAnswer();


    } catch (error) {

        console.error(error);


        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: 서버 연결 오류";

    }

}


// ==========================================
// 위치 가져오기
// ==========================================

function getLocation() {

    return new Promise(
        function(resolve, reject) {

            if (!navigator.geolocation) {

                reject(
                    "이 브라우저는 위치 기능을 지원하지 않습니다."
                );

                return;

            }


            navigator.geolocation.getCurrentPosition(

                function(position) {

                    lastLocation = {

                        latitude:
                            position.coords.latitude,

                        longitude:
                            position.coords.longitude

                    };


                    document.getElementById(
                        "locationStatus"
                    ).innerText =
                        "현재 위치 확인 완료";


                    resolve(lastLocation);

                },


                function(error) {

                    reject(
                        "위치 권한이 필요합니다."
                    );

                },


                {
                    enableHighAccuracy: true,

                    timeout: 10000,

                    maximumAge: 60000

                }

            );

        }
    );

}


// ==========================================
// 날씨
// ==========================================

async function getWeather() {

    document.getElementById(
        "status"
    ).innerText =
        "현재 위치와 날씨를 확인하고 있습니다...";


    try {

        const location =
            await getLocation();


        const response =
            await fetch(
                "/weather",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(
                            location
                        )
                }
            );


        const data =
            await response.json();


        lastAnswer =
            data.answer;


        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            lastAnswer;


        speakAnswer();


    } catch (error) {

        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            error;

    }

}


// ==========================================
// 길찾기
// ==========================================

async function openDirections() {

    const destination =
        document.getElementById(
            "question"
        ).value.trim();


    if (!destination) {

        document.getElementById(
            "status"
        ).innerText =
            "목적지를 먼저 입력해주세요.";

        return;

    }


    try {

        const location =
            await getLocation();


        const url =
            "https://www.google.com/maps/dir/?api=1" +
            "&origin=" +
            encodeURIComponent(
                location.latitude +
                "," +
                location.longitude
            ) +
            "&destination=" +
            encodeURIComponent(
                destination
            );


        window.open(
            url,
            "_blank"
        );


        lastAnswer =
            destination +
            "까지의 길찾기를 열었습니다.";


        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            lastAnswer;


        speakAnswer();


    } catch (error) {

        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            error;

    }

}


// ==========================================
// 카메라 시작
// ==========================================

async function startCamera() {

    try {

        cameraStream =
            await navigator.mediaDevices
                .getUserMedia({

                    video: {
                        facingMode: {
                            ideal: "environment"
                        }
                    },

                    audio: false

                });


        const video =
            document.getElementById(
                "camera"
            );


        video.srcObject =
            cameraStream;


        document.getElementById(
            "cameraArea"
        ).style.display =
            "block";


        document.getElementById(
            "status"
        ).innerText =
            "카메라가 켜졌습니다.";

    } catch (error) {

        console.error(error);


        document.getElementById(
            "status"
        ).innerText =
            "카메라 권한을 허용해주세요.";

    }

}


// ==========================================
// 카메라 사진 캡처
// ==========================================

function captureImage() {

    const video =
        document.getElementById(
            "camera"
        );


    if (!video.srcObject) {

        throw new Error(
            "먼저 카메라를 켜주세요."
        );

    }


    const canvas =
        document.getElementById(
            "snapshot"
        );


    canvas.width =
        video.videoWidth;


    canvas.height =
        video.videoHeight;


    const context =
        canvas.getContext("2d");


    context.drawImage(
        video,
        0,
        0,
        canvas.width,
        canvas.height
    );


    return canvas.toDataURL(
        "image/jpeg",
        0.85
    );

}


// ==========================================
// 물체 분석
// ==========================================

async function analyzeObject() {

    try {

        const image =
            captureImage();


        document.getElementById(
            "status"
        ).innerText =
            "PRIME이 앞의 물체를 분석하고 있습니다...";


        const response =
            await fetch(
                "/vision",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            image:
                                image,

                            mode:
                                "analyze"

                        })

                }
            );


        const data =
            await response.json();


        lastAnswer =
            data.answer;


        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            lastAnswer;


        speakAnswer();


    } catch (error) {

        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            error.message;

    }

}


// ==========================================
// 번역
// ==========================================

async function translateCamera() {

    try {

        const image =
            captureImage();


        document.getElementById(
            "status"
        ).innerText =
            "PRIME이 글자를 읽고 번역하고 있습니다...";


        const response =
            await fetch(
                "/vision",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            image:
                                image,

                            mode:
                                "translate"

                        })

                }
            );


        const data =
            await response.json();


        lastAnswer =
            data.answer;


        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            lastAnswer;


        speakAnswer();


    } catch (error) {

        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            error.message;

    }

}


// ==========================================
// 가격 검색
// ==========================================

async function priceSearch() {

    try {

        const image =
            captureImage();


        document.getElementById(
            "status"
        ).innerText =
            "제품을 식별하고 현재 가격을 검색하고 있습니다...";


        const response =
            await fetch(
                "/vision",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            image:
                                image,

                            mode:
                                "price"

                        })

                }
            );


        const data =
            await response.json();


        lastAnswer =
            data.answer;


        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            lastAnswer;


        speakAnswer();


    } catch (error) {

        document.getElementById(
            "answer"
        ).innerText =
            "PRIME: " +
            error.message;

    }

}


// ==========================================
// 페이지 로딩
// ==========================================

window.addEventListener(
    "load",
    function() {

        loadVoices();

    }
);

</script>

</body>

</html>
"""


# ==========================================
# 메인
# ==========================================

@app.route("/")
def home():

    return render_template_string(
        HTML
    )


# ==========================================
# 일반 PRIME AI
# ==========================================

@app.route(
    "/ask",
    methods=["POST"]
)
def ask():

    data =
        request.get_json(
            silent=True
        ) or {}


    question =
        data.get(
            "question",
            ""
        ).strip()


    if not question:

        return jsonify({
            "answer":
                "질문을 입력해주세요."
        })


    try:

        response =
            client.responses.create(

                model="gpt-6-luna",

                instructions="""
당신의 이름은 PRIME입니다.

당신은 사용자의 개인 AI 비서입니다.

차분하고 정중하며 자연스럽게
한국어로 대답합니다.

음성으로 읽었을 때 자연스럽도록
불필요한 특수문자와 이모티콘을
사용하지 않습니다.

최신 정보가 필요한 질문은
웹 검색을 활용합니다.

날씨, 가격, 뉴스, 현재 정보 등은
추측하지 말고 확인된 정보를 사용합니다.
""",

                tools=[
                    {
                        "type":
                            "web_search"
                    }
                ],

                input=question

            )


        return jsonify({
            "answer":
                response.output_text
        })


    except Exception as e:

        print(
            "ASK ERROR:",
            e
        )


        return jsonify({
            "answer":
                "PRIME 처리 중 오류가 발생했습니다."
        })


# ==========================================
# 날씨
# ==========================================

@app.route(
    "/weather",
    methods=["POST"]
)
def weather():

    data =
        request.get_json(
            silent=True
        ) or {}


    latitude =
        data.get("latitude")


    longitude =
        data.get("longitude")


    if latitude is None or longitude is None:

        return jsonify({
            "answer":
                "현재 위치를 확인할 수 없습니다."
        })


    try:

        url =
            "https://api.open-meteo.com/v1/forecast"


        params = {

            "latitude":
                latitude,

            "longitude":
                longitude,

            "current":
                "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",

            "timezone":
                "Asia/Seoul"

        }


        response =
            requests.get(
                url,
                params=params,
                timeout=10
            )


        response.raise_for_status()


        weather_data =
            response.json()


        current =
            weather_data[
                "current"
            ]


        weather_code =
            current.get(
                "weather_code",
                0
            )


        descriptions = {

            0: "맑음",

            1: "대체로 맑음",

            2: "부분적으로 흐림",

            3: "흐림",

            45: "안개",

            48: "안개",

            51: "약한 이슬비",

            53: "이슬비",

            55: "강한 이슬비",

            61: "약한 비",

            63: "비",

            65: "강한 비",

            71: "약한 눈",

            73: "눈",

            75: "강한 눈",

            80: "소나기",

            81: "소나기",

            82: "강한 소나기",

            95: "뇌우",

            96: "뇌우",

            99: "뇌우"

        }


        description =
            descriptions.get(
                weather_code,
                "현재 날씨"
            )


        answer = (
            "현재 기온은 "
            + str(
                current.get(
                    "temperature_2m"
                )
            )
            + "도입니다. "

            + description
            + "이고, "

            + "체감온도는 "
            + str(
                current.get(
                    "apparent_temperature"
                )
            )
            + "도입니다. "

            + "습도는 "
            + str(
                current.get(
                    "relative_humidity_2m"
                )
            )
            + "퍼센트이며, "

            + "바람은 시속 "
            + str(
                current.get(
                    "wind_speed_10m"
                )
            )
            + "킬로미터입니다."
        )


        return jsonify({
            "answer":
                answer
        })


    except Exception as e:

        print(
            "WEATHER ERROR:",
            e
        )


        return jsonify({
            "answer":
                "날씨 정보를 가져오지 못했습니다."
        })


# ==========================================
# 카메라 AI
# ==========================================

@app.route(
    "/vision",
    methods=["POST"]
)
def vision():

    data =
        request.get_json(
            silent=True
        ) or {}


    image_data =
        data.get(
            "image",
            ""
        )


    mode =
        data.get(
            "mode",
            "analyze"
        )


    if not image_data:

        return jsonify({
            "answer":
                "카메라 이미지를 받지 못했습니다."
        })


    try:

        if "," in image_data:

            image_data =
                image_data.split(
                    ",",
                    1
                )[1]


        prompt = ""


        if mode == "analyze":

            prompt = """
사진을 보고 앞에 있는 물체를 분석하세요.

한국어로 대답하세요.

가능하면 다음을 알려주세요.

1. 무엇인지
2. 브랜드
3. 제품 종류
4. 보이는 특징
5. 정확한 모델을 판단할 수 있는지

확실하지 않은 내용은 추측해서 단정하지 마세요.
"""


        elif mode == "translate":

            prompt = """
사진 속에 보이는 글자를 읽으세요.

외국어가 있다면 한국어로 번역하세요.

가능하면 원문과 한국어 번역을 함께 알려주세요.

글자가 잘 보이지 않으면 그렇게 알려주세요.
"""


        elif mode == "price":

            prompt = """
사진 속 물체를 분석해서 제품을 식별하세요.

가능하면 브랜드와 정확한 제품명,
모델명을 확인하세요.

그 다음 웹 검색을 사용해서
현재 판매 가격과 가능한 경우
중고 시세를 확인하세요.

가격은 대한민국 원화 기준으로 설명하세요.

검색 결과가 확실하지 않으면
정확한 가격이라고 단정하지 마세요.

제품 식별이 불확실하면
후보 제품을 구분해서 설명하세요.
"""


        image_url =
            "data:image/jpeg;base64," +
            image_data


        tools = []


        if mode == "price":

            tools = [
                {
                    "type":
                        "web_search"
                }
            ]


        response =
            client.responses.create(

                model="gpt-6-luna",

                instructions="""
당신은 PRIME입니다.

사용자가 카메라로 보여주는
사물을 분석하는 개인 AI 비서입니다.

항상 한국어로 대답하세요.

확실하지 않은 정보는
확실하다고 말하지 마세요.

가격을 말할 때는
검색된 최신 정보와
가격의 기준을 명확히 설명하세요.
""",

                tools=tools,

                input=[

                    {

                        "role":
                            "user",

                        "content": [

                            {

                                "type":
                                    "input_text",

                                "text":
                                    prompt

                            },

                            {

                                "type":
                                    "input_image",

                                "image_url":
                                    image_url

                            }

                        ]

                    }

                ]

            )


        return jsonify({
            "answer":
                response.output_text
        })


    except Exception as e:

        print(
            "VISION ERROR:",
            e
        )


        return jsonify({
            "answer":
                "카메라 분석 중 오류가 발생했습니다."
        })


# ==========================================
# 서버 실행
# ==========================================

if __name__ == "__main__":

    print(
        "=============================="
    )

    print(
        " PRIME V8 SERVER"
    )

    print(
        "=============================="
    )

    print(
        "PRIME V8 서버가 시작되었습니다."
    )


    app.run(

        host="0.0.0.0",

        port=5000

    )
