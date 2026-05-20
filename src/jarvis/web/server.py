"""J.A.R.V.I.S. web dashboard — Flask + Socket.IO real-time UI."""

import os
import threading
import time
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, Response, jsonify, redirect, render_template,
    render_template_string, request, session, url_for,
)
from flask_socketio import SocketIO, disconnect, emit

from jarvis.core.brain import Brain
from jarvis.core.speaker import Speaker
from jarvis.memory.conversation import ConversationMemory
from jarvis.skills import reminders as reminder_module
from jarvis.skills import timer as timer_module

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>J.A.R.V.I.S. — Authorisation Required</title>
<style>
  :root{--c:#00d4ff;--bg:#030810;--bg2:#070f1a;--c3:#003366;--err:#ff3333;--dim:#2a4a5a}
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:#b0e4f0;font-family:'Courier New',monospace;
       height:100vh;display:flex;align-items:center;justify-content:center}
  .box{background:var(--bg2);border:1px solid var(--c3);border-radius:8px;
       padding:40px 48px;width:360px;text-align:center}
  .logo{font-size:22px;font-weight:bold;letter-spacing:6px;color:var(--c);
        text-shadow:0 0 12px rgba(0,212,255,.6);margin-bottom:4px}
  .sub{font-size:9px;letter-spacing:3px;color:var(--dim);margin-bottom:32px}
  label{display:block;font-size:10px;letter-spacing:3px;color:var(--dim);
        text-align:left;margin-bottom:6px}
  input[type=password]{width:100%;background:#0a1520;border:1px solid var(--c3);
    border-radius:4px;color:var(--c);font-family:inherit;font-size:14px;
    padding:10px 12px;outline:none;caret-color:var(--c);margin-bottom:20px;transition:border-color .2s}
  input[type=password]:focus{border-color:var(--c)}
  button{width:100%;padding:10px;background:transparent;border:1px solid var(--c);
    border-radius:4px;color:var(--c);font-family:inherit;font-size:12px;
    letter-spacing:3px;cursor:pointer;text-transform:uppercase;transition:all .2s}
  button:hover{background:var(--c);color:var(--bg)}
  .error{color:var(--err);font-size:11px;letter-spacing:1px;margin-bottom:14px}
</style>
</head>
<body>
  <div class="box">
    <div class="logo">J.A.R.V.I.S.</div>
    <div class="sub">AUTHORISATION REQUIRED</div>
    {% if error %}<div class="error">⚠ {{ error }}</div>{% endif %}
    <form method="post" action="/login">
      <label>ACCESS CODE</label>
      <input type="password" name="password" autofocus autocomplete="current-password">
      <button type="submit">Authenticate</button>
    </form>
  </div>
</body>
</html>"""


class WebServer:
    """Hosts the JARVIS browser dashboard on localhost."""

    def __init__(
        self,
        brain: Brain,
        memory: ConversationMemory,
        speaker: Speaker | None = None,
        port: int = 7575,
        password: str = "",
    ):
        self._brain    = brain
        self._memory   = memory
        self._speaker  = speaker
        self._port     = port
        self._password = password  # empty = no auth

        self._app = Flask(__name__, template_folder="templates")
        self._app.config["SECRET_KEY"] = os.urandom(24)
        self._sio = SocketIO(
            self._app,
            cors_allowed_origins="*",
            async_mode="threading",
        )

        self._register_routes()
        self._register_events()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _auth_required(self) -> bool:
        return bool(self._password)

    def _is_authenticated(self) -> bool:
        return not self._auth_required() or session.get("authenticated") is True

    def _require_auth(self, f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not self._is_authenticated():
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, host: str = "127.0.0.1", open_browser: bool = True) -> None:
        threading.Thread(target=self._metrics_loop,   daemon=True).start()
        threading.Thread(target=self._reminder_relay, daemon=True).start()

        if open_browser:
            import webbrowser
            threading.Timer(
                1.2, lambda: webbrowser.open(f"http://{host}:{self._port}")
            ).start()

        print(f"  J.A.R.V.I.S. dashboard → http://{host}:{self._port}")
        if self._auth_required():
            print("  Password protection: enabled")
        self._sio.run(
            self._app,
            host=host,
            port=self._port,
            debug=False,
            log_output=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def _register_routes(self) -> None:
        app = self._app

        @app.route("/login", methods=["GET", "POST"])
        def login():
            if not self._auth_required():
                return redirect(url_for("index"))
            if self._is_authenticated():
                return redirect(url_for("index"))
            error = None
            if request.method == "POST":
                if request.form.get("password") == self._password:
                    session["authenticated"] = True
                    session.permanent = False
                    return redirect(url_for("index"))
                error = "Invalid access code. Try again."
            return render_template_string(_LOGIN_HTML, error=error)

        @app.route("/logout")
        def logout():
            session.clear()
            return redirect(url_for("login"))

        @app.route("/")
        @self._require_auth
        def index():
            return render_template("index.html", auth_enabled=self._auth_required())

        @app.route("/api/history")
        @self._require_auth
        def history():
            turns = self._memory.get_recent(30)
            return jsonify(turns)

        @app.route("/api/facts")
        @self._require_auth
        def facts():
            raw = self._memory.recall_facts()
            facts_list = []
            if "no stored" not in raw.lower():
                body = raw.split(": ", 1)[-1].rstrip(".")
                facts_list = [f.strip() for f in body.split(".") if f.strip()]
            return jsonify({"facts": facts_list})

        @app.route("/api/reminders")
        @self._require_auth
        def reminders():
            text = reminder_module.list_reminders()
            return jsonify({"text": text})

        @app.route("/api/timers")
        @self._require_auth
        def timers():
            active = timer_module.get_active_timers()
            return jsonify({
                "timers": [
                    {
                        "id":                str(t["id"]),
                        "label":             f"Timer {t['id']}",
                        "remaining_seconds": round(t["remaining"], 1),
                    }
                    for t in active
                ]
            })

        @app.route("/api/export")
        @self._require_auth
        def export():
            turns = self._memory.get_recent(200)
            now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            lines: list[str] = [
                "# J.A.R.V.I.S. Conversation Export", "",
                f"**Exported:** {now}  ", f"**Turns:** {len(turns)}", "", "---", "",
            ]
            for turn in turns:
                role    = turn.get("role", "unknown")
                content = turn.get("content", "")
                tag     = "**You**" if role == "user" else "**J.A.R.V.I.S.**"
                lines += [tag, "", content, "", "---", ""]
            md       = "\n".join(lines)
            filename = f"jarvis-export-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
            return Response(
                md,
                mimetype="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    # ------------------------------------------------------------------
    # Socket.IO events
    # ------------------------------------------------------------------

    def _register_events(self) -> None:
        sio = self._sio

        def _check_socket_auth() -> bool:
            if self._auth_required() and not session.get("authenticated"):
                disconnect()
                return False
            return True

        @sio.on("connect")
        def on_connect():
            if not _check_socket_auth():
                return
            turns = self._memory.get_recent(30)
            emit("history", turns)

        @sio.on("message")
        def on_message(data: dict):
            if not _check_socket_auth():
                return
            user_text = (data.get("text") or "").strip()
            if not user_text:
                return

            self._memory.add_message("user", user_text)
            emit("user_message", {"text": user_text})

            tokens: list[str] = []

            def _on_token(tok: str) -> None:
                tokens.append(tok)
                sio.emit("token", {"text": tok})

            response = self._brain.process(user_text, stream_callback=_on_token)
            self._memory.add_message("assistant", response)
            sio.emit("response_complete", {"text": response})

            if self._speaker:
                self._speaker.speak(response, blocking=False)

        @sio.on("clear_context")
        def on_clear_context():
            if not _check_socket_auth():
                return
            self._memory.clear_history()
            emit("context_cleared")

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _metrics_loop(self) -> None:
        while True:
            try:
                self._sio.emit("metrics", _get_metrics())
            except Exception:
                pass
            time.sleep(2)

    def _reminder_relay(self) -> None:
        while True:
            try:
                msg = reminder_module.fired_queue.get(timeout=1)
                self._sio.emit("reminder_fired", {"text": msg})
                if self._speaker:
                    self._speaker.speak(msg, blocking=False)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Metrics helper
# ---------------------------------------------------------------------------

def _get_metrics() -> dict:
    metrics: dict = {}
    try:
        import psutil
        metrics["cpu"]         = psutil.cpu_percent(interval=None)
        ram                    = psutil.virtual_memory()
        metrics["ram"]         = ram.percent
        metrics["ram_free_gb"] = f"{ram.available / (1024**3):.1f}"
        try:
            disk               = psutil.disk_usage("/")
            metrics["disk"]    = disk.percent
        except Exception:
            pass
        try:
            bat = psutil.sensors_battery()
            if bat:
                metrics["battery"] = {
                    "percent":  round(bat.percent),
                    "charging": bat.power_plugged,
                }
        except Exception:
            pass
    except ImportError:
        pass
    return metrics
