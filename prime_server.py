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

<p>PRIME V5 ONLINE</p>

<input id="question" placeholder="PRIME에게 질문하세요">

<br>

<button onclick="startListening()">🎙 말하기</button>
<button onclick="askPrime()">질문하기</button>
<button onclick="speakAnswer()">🔊 답변 듣기</button>

<div id="status"></div>
<div id="answer"></div>

<script>

let recognition = null;
let lastAnswer = "";


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

        document.getElementById("question").value = text;

        document.getElementById("status").innerText =
            "질문을 확인했습니다.";

        askPrime();
    };

    recognition.onerror = function(event) {

        document.getElementById("status").innerText =
            "마이크 오류: " + event.error;
    };
}


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

        const response = await fetch("/ask", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                question: question
            })
        });

        const data = await response.json();

        lastAnswer = data.answer;

        document.getElementById("answer").innerText =
            "PRIME: " + lastAnswer;

        document.getElementById("status").innerText =
            "PRIME 온라인";

    } catch (error) {

        console.error(error);

        document.getElementById("answer").innerText =
            "PRIME: 서버 연결 오류";

        document.getElementById("status").innerText =
            "오류가 발생했습니다.";
    }
}


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

    const speech =
        new SpeechSynthesisUtterance(lastAnswer);

    speech.lang = "ko-KR";
    speech.rate = 1.0;
    speech.pitch = 1.0;
    speech.volume = 1.0;

    speech.onstart = function() {

        document.getElementById("status").innerText =
            "PRIME이 말하고 있습니다...";
    };

    speech.onend = function() {

        document.getElementById("status").innerText =
            "PRIME 온라인";
    };

    speech.onerror = function(error) {

        console.log(error);

        document.getElementById("status").innerText =
            "음성 출력 오류";
    };

    window.speechSynthesis.speak(speech);
}


</script>

</body>
</html>
"""


@app.route("/")
def home():

    return render_template_string(HTML)


@app.route("/ask", methods=["POST"])
def ask():

    data = request.json

    question = data.get("question", "")

    try:

        response = client.responses.create(

            model="gpt-6-luna",

            instructions="""
당신의 이름은 PRIME입니다.

당신은 사용자의 개인 AI 비서입니다.

말투는 차분하고 정중하며 자연스럽습니다.

한국어로 대답합니다.

사용자가 이해하기 쉽게 설명하세요.
""",

            input=question
        )

        return jsonify({
            "answer": response.output_text
        })

    except Exception as e:

        print("ERROR:", e)

        return jsonify({
            "answer": "오류가 발생했습니다."
        })


if __name__ == "__main__":

    print("==============================")
    print(" PRIME V5 SERVER")
    print("==============================")
    print("PRIME 서버가 시작되었습니다.")

    app.run(
        host="0.0.0.0",
        port=5000
    )
