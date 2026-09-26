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
    margin-top: 15px;
    padding: 14px 30px;
    font-size: 18px;
    background: #0088cc;
    color: white;
    border: none;
    border-radius: 8px;
}

#answer {
    margin: 30px auto;
    max-width: 600px;
    font-size: 20px;
    line-height: 1.6;
}
</style>
</head>

<body>

<h1>PRIME</h1>

<p>PRIME V4 ONLINE</p>

<input id="question" placeholder="PRIME에게 질문하세요">

<br>

<button onclick="askPrime()">질문하기</button>

<div id="answer"></div>

<script>

async function askPrime() {

    const question =
        document.getElementById("question").value;

    if (!question) return;

    document.getElementById("answer").innerText =
        "PRIME: 생각 중...";

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

    document.getElementById("answer").innerText =
        "PRIME: " + data.answer;
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

        return jsonify({
            "answer": "오류가 발생했습니다."
        })


if __name__ == "__main__":

    print("==============================")
    print("       PRIME V4 SERVER")
    print("==============================")
    print("PRIME 서버가 시작되었습니다.")
    print("컴퓨터에서 http://127.0.0.1:5000")
    print("")

    app.run(
        host="0.0.0.0",
        port=5000
    )