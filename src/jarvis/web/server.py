"""J.A.R.V.I.S. web dashboard — Flask + Socket.IO real-time UI."""

import threading
import time

from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO, emit

from jarvis.core.brain import Brain
from jarvis.core.speaker import Speaker
from jarvis.memory.conversation import ConversationMemory
from jarvis.skills import reminders as reminder_module


class WebServer:
    """Hosts the JARVIS browser dashboard on localhost."""

    def __init__(
        self,
        brain: Brain,
        memory: ConversationMemory,
        speaker: Speaker | None = None,
        port: int = 7575,
    ):
        self._brain   = brain
        self._memory  = memory
        self._speaker = speaker
        self._port    = port

        self._app = Flask(__name__, template_folder="templates")
        self._app.config["SECRET_KEY"] = "jarvis-dashboard"
        self._sio = SocketIO(
            self._app,
            cors_allowed_origins="*",
            async_mode="threading",
        )

        self._register_routes()
        self._register_events()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, host: str = "127.0.0.1", open_browser: bool = True) -> None:
        """Start the web server (blocking). Opens browser automatically."""
        threading.Thread(target=self._metrics_loop,   daemon=True).start()
        threading.Thread(target=self._reminder_relay, daemon=True).start()

        if open_browser:
            import webbrowser
            threading.Timer(
                1.2, lambda: webbrowser.open(f"http://{host}:{self._port}")
            ).start()

        print(f"  J.A.R.V.I.S. dashboard → http://{host}:{self._port}")
        self._sio.run(
            self._app,
            host=host,
            port=self._port,
            debug=False,
            log_output=False,
            use_reloader=False,
        )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def _register_routes(self) -> None:
        app = self._app

        @app.route("/")
        def index():
            return render_template("index.html")

        @app.route("/api/history")
        def history():
            turns = self._memory.get_recent(30)
            return jsonify(turns)

        @app.route("/api/facts")
        def facts():
            raw = self._memory.recall_facts()
            facts_list = []
            if "no stored" not in raw.lower():
                # Strip prefix, split on ". "
                body = raw.split(": ", 1)[-1].rstrip(".")
                facts_list = [f.strip() for f in body.split(".") if f.strip()]
            return jsonify({"facts": facts_list})

        @app.route("/api/reminders")
        def reminders():
            text = reminder_module.list_reminders()
            return jsonify({"text": text})

    # ------------------------------------------------------------------
    # Socket.IO events
    # ------------------------------------------------------------------

    def _register_events(self) -> None:
        sio = self._sio

        @sio.on("connect")
        def on_connect():
            # Send conversation history on connect
            turns = self._memory.get_recent(30)
            emit("history", turns)

        @sio.on("message")
        def on_message(data: dict):
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

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _metrics_loop(self) -> None:
        """Push system metrics to all clients every 2 seconds."""
        while True:
            try:
                self._sio.emit("metrics", _get_metrics())
            except Exception:
                pass
            time.sleep(2)

    def _reminder_relay(self) -> None:
        """Forward fired reminders to all connected clients."""
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
