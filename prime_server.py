import os

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

<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>PRIME</title>

<style>

body {
    background: #050505;
    color: #00aaff;
    font-family: Arial, sans-serif;
    text-align: center;
    padding: 30px;
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
    margin: 10px 5px;
    padding: 14px 25px;
    font-size: 18px;
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
    margin: 30px auto;
    max-width: 600px;
    font-size: 20px;
    line-height: 1.6;
}

#status {
    margin-top: 15px;
    color: #66ccff;
}

</style>

</head>

<body>

<h1>PRIME</h1>

<p>PRIME V6 ONLINE</p>

<input
    id="question"
    placeholder="PRIME에게 질문하세요"
>

<br>

<button onclick="startListening()">
    🎙 말하기
</button>

<button onclick="askPrime()">
    질문하기
</button>

<button onclick="speakAnswer()">
    🔊 답변 듣기
</button>

<div id="status"></div>

<div id="answer"></div>


<script>

let recognition = null;
let lastAnswer = "";
let selectedVoice = null;


// ==========================================
// 한국어 음성 찾기
// ==========================================

function loadVoices() {

    const voices = window.speechSynthesis.getVoices();

    if (!voices || voices.length === 0) {
        return;
    }

    const koreanVoices = voices.filter(function(voice) {

        return voice.lang.toLowerCase().startsWith("ko");

    });

    if (koreanVoices.length === 0) {
        selectedVoice = null;
        return;
    }

    // 이름에 남성 표시가 있는 음성을 우선 사용
    selectedVoice = koreanVoices.find(function(voice) {

        const name = voice.name.toLowerCase();

        return (
            name.includes("male") ||
            name.includes("man") ||
            name.includes("남성") ||
            name.includes("남자")
        );

    });

    // 남성 표시가 없으면 첫 번째 한국어 음성 사용
    if (!selectedVoice) {
        selectedVoice = koreanVoices[0];
    }
}


window.speechSynthesis.onvoiceschanged = function() {

    loadVoices();

};


// ==========================================
// 음성 인식
// ==========================================

function startListening() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;

    if (!SpeechRecognition) {

        document.getElementById("status").innerText =
            "이 브라우저에서는 음성 인식을 지원하지 않습니다.";

        return;
    }

    recognition = new SpeechRecognition();

    recognition.lang = "ko-KR";

    recognition.continuous = false;

    recognition.interimResults = false;

    document.getElementById("status").innerText =
        "PRIME이 듣고 있습니다...";

    try {

        recognition.start();

    } catch (error) {

        console.log(error);

    }

    recognition.onresult = function(event) {

        const text =
            event.results[0][0].transcript;

        document.getElementById("question").value =
            text;

        document.getElementById("status").innerText =
            "질문을 확인했습니다.";

        askPrime();
    };

    recognition.onerror = function(event) {

        document.getElementById("status").innerText =
            "마이크 오류: " + event.error;

    };
}


// ==========================================
// PRIME에게 질문
// ==========================================

async function askPrime() {

    const question =
        document.getElementById("question").value.trim();

    if (!question) {
        return;
    }

    document.getElementById("answer").innerText =
        "PRIME: 생각 중...";

    document.getElementById("status").innerText =
        "PRIME이 답변을 준비하고 있습니다...";

    try {

        const response = await fetch(
            "/ask",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    question: question
                })
            }
        );

        const data = await response.json();

        lastAnswer = data.answer;

        document.getElementById("answer").innerText =
            "PRIME: " + lastAnswer;

        document.getElementById("status").innerText =
            "PRIME 온라인";

        // 답변이 나오면 자동으로 음성 출력
        speakAnswer();

    } catch (error) {

        console.error(error);

        document.getElementById("answer").innerText =
            "PRIME: 서버 연결 오류";

        document.getElementById("status").innerText =
            "오류가 발생했습니다.";

    }
}


// ==========================================
// 브라우저 음성 출력
// ==========================================

function speakAnswer() {

    if (!lastAnswer) {

        document.getElementById("status").innerText =
            "먼저 PRIME에게 질문해주세요.";

        return;
    }

    if (!("speechSynthesis" in window)) {

        document.getElementById("status").innerText =
            "이 브라우저에서는 음성 출력을 지원하지 않습니다.";

        return;
    }

    window.speechSynthesis.cancel();

    loadVoices();

    const speech =
        new SpeechSynthesisUtterance(lastAnswer);

    speech.lang = "ko-KR";

    // 말하는 속도
    speech.rate = 0.95;

    // 조금 낮은 음색
    speech.pitch = 0.75;

    speech.volume = 1.0;

    if (selectedVoice) {
        speech.voice = selectedVoice;
    }

    speech.onstart = function() {

        document.getElementById("status").innerText =
            "PRIME이 말하고 있습니다...";

    };

    speech.onend = function() {

        document.getElementById("status").innerText =
            "PRIME 온라인";

    };

    speech.onerror = function(error) {

        console.log("Speech error:", error);

        document.getElementById("status").innerText =
            "음성 출력 오류";

    };

    window.speechSynthesis.speak(speech);
}


// ==========================================
// 페이지 로딩
// ==========================================

window.addEventListener("load", function() {

    loadVoices();

});

</script>

</body>

</html>
"""


# ==========================================
# 메인 페이지
# ==========================================

@app.route("/")
def home():

    return render_template_string(HTML)


# ==========================================
# PRIME AI 답변
# ==========================================

@app.route("/ask", methods=["POST"])
def ask():

    data = request.get_json(silent=True) or {}

    question = data.get("question", "").strip()

    if not question:

        return jsonify({
            "answer": "질문을 입력해주세요."
        })


    try:

        response = client.responses.create(

            model="gpt-6-luna",

            instructions="""
당신의 이름은 PRIME입니다.

당신은 사용자의 개인 AI 비서입니다.

말투는 차분하고 정중하며 자연스럽습니다.

한국어로 대답합니다.

고급 개인 AI 비서처럼 말하세요.

음성으로 읽었을 때 자연스럽게 들리도록
불필요한 특수문자와 이모티콘을 사용하지 마세요.

문장을 지나치게 길게 만들지 마세요.

필요하면 짧은 문장으로 나누어 설명하세요.

사용자가 이해하기 쉽게 설명하세요.
""",

            input=question
        )

        answer = response.output_text

        return jsonify({
            "answer": answer
        })


    except Exception as e:

        print("ERROR:", e)

        return jsonify({
            "answer": "오류가 발생했습니다."
        })


# ==========================================
# 서버 실행
# ==========================================

if __name__ == "__main__":

    print("==============================")
    print(" PRIME V6 SERVER")
    print("==============================")
    print("PRIME 서버가 시작되었습니다.")

    app.run(
        host="0.0.0.0",
        port=5000
    )
