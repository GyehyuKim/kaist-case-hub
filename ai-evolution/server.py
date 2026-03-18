#!/usr/bin/env python3
"""
AI Evolution 케이스 서버 + Ollama 연동
Usage: python server.py
Open : http://localhost:8081/
"""
import http.server
import json
import urllib.request
import urllib.error
import os
import threading
import webbrowser

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PORT      = 8081
OLLAMA    = "http://localhost:11434/api/generate"
PREFERRED = ["qwen3.5:2b", "qwen3.5:4b", "qwen3:1.7b", "qwen2.5:1.5b", "llama3.2:1b"]

SYSTEM = (
    "당신은 AI, 경영 전략, 기술 혁신 분야의 전문가입니다. "
    "사용자가 제공하는 영어 단어/표현을 반드시 아래 형식 그대로 출력하세요.\n\n"
    "- **일반적 의미:** (1문장)\n\n"
    "- **맥락적 의미:** (문맥 기반 AI/경영 해석, 2문장 이내)\n\n"
    "규칙: 두 항목 사이에 반드시 빈 줄 하나를 넣으세요. 전체 80단어 이내."
)


def build_prompt(text, context):
    ctx = '\n문맥: "' + context[:200] + '"' if context else ""
    return '설명할 표현: "' + text + '"' + ctx


def pick_model():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
        for m in PREFERRED:
            if any(n == m or n.startswith(m.split(":")[0]) for n in names):
                return m
    except Exception:
        pass
    return PREFERRED[-1]


def is_qwen3(model):
    return model.startswith("qwen3")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BASE_DIR, **kw)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/explain":
            self._explain()
        else:
            self.send_response(404)
            self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _explain(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
        except Exception:
            self.send_response(400); self.end_headers(); return

        text    = body.get("text", "").strip()
        context = body.get("context", "").strip()
        model   = body.get("model", pick_model())

        if not text:
            self.send_response(400); self.end_headers(); return

        prompt = build_prompt(text, context)
        payload_dict = {
            "model":   model,
            "system":  SYSTEM,
            "prompt":  prompt,
            "stream":  True,
            "options": {"temperature": 0.2, "num_predict": 450},
        }
        if is_qwen3(model):
            payload_dict["think"] = False

        payload = json.dumps(payload_dict).encode()

        req = urllib.request.Request(
            OLLAMA, data=payload,
            headers={"Content-Type": "application/json"}
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()

        def send(obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode())
            self.wfile.flush()

        send({"model": model})

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw in resp:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        chunk = json.loads(raw)
                    except Exception:
                        continue
                    tok = chunk.get("response", "")
                    if tok:
                        send({"token": tok})
                    if chunk.get("done"):
                        send({"done": True})
                        break
        except urllib.error.URLError as e:
            send({"error": "Ollama 연결 실패: " + str(e) + ". Ollama가 실행 중인지 확인하세요."})
        except Exception as e:
            try:
                send({"error": str(e)})
            except Exception:
                pass

    def log_message(self, fmt, *args):
        if self.path and self.path.startswith("/api"):
            try:
                print("  [%s] %s -- %s" % (self.command, self.path, fmt % args))
            except Exception:
                pass


if __name__ == "__main__":
    model = pick_model()
    print("=" * 50)
    print("  AI Evolution Case Hub Server")
    print("  Model: %s" % model)
    print("  URL  : http://localhost:%d/" % PORT)
    print("  Stop : Ctrl+C")
    print("=" * 50)

    threading.Thread(
        target=lambda: (
            __import__("time").sleep(0.6),
            webbrowser.open("http://localhost:%d/" % PORT),
        ),
        daemon=True,
    ).start()

    with http.server.ThreadingHTTPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n서버 종료.")
