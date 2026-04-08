# Jarvis

A local AI assistant powered by Ollama, modelled after the Iron Man AI. Responds to typed commands in the terminal with optional voice input/output.

## Features

- **Text interface** — type commands directly in the terminal
- **Voice input** — type `!` and press Enter to speak a command (transcribed via Whisper)
- **Voice output** — responses spoken aloud via macOS `say`
- **Streaming** — LLM responses stream token-by-token as they are generated
- **Skill routing** — LLM emits action tags; Jarvis dispatches them to the right skill
- **Conversation memory** — recent turns are included in each prompt for context

## Skills

| Tag | Action |
|-----|--------|
| `[OPEN: <app>]` | Open a macOS application |
| `[URL: <url>]` | Open a URL in the default browser |
| `[SEARCH: <query>]` | Web search (summarised by LLM) |
| `[VOLUME: <0-100>]` | Set system volume |
| `[CMD: <command>]` | Run a safe shell command |
| `[NOTE: <text>]` | Save a note to `~/.jarvis/notes.txt` |
| `[NOTES]` | Read your five most recent notes |
| `[TIME]` | Current time |
| `[DATE]` | Today's date |
| `[CALC: <expr>]` | Evaluate a math expression |

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally with a model pulled (default: `llama3`)
- macOS (for `open`, `osascript`, and `say` commands)
- Microphone access (for voice input)

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Pull the default model
ollama pull llama3

# Start Ollama (if not already running)
ollama serve
```

## Running

```bash
python -m jarvis.main
# or
python src/jarvis/main.py
```

## Configuration

Edit `config/settings.yaml` to change:

- `ollama.model` — which Ollama model to use
- `ollama.context_turns` — how many conversation turns to keep in context
- `jarvis.voice` — macOS `say` voice name
- `whisper.command_model` — Whisper model size for voice transcription (`tiny`, `base`, `small`, etc.)

## Usage

```
You: open spotify
Jarvis: Opening Spotify.

You: what's the weather in London
Jarvis: [searches and summarises]

You: !
Listening… speak now.
You (voice): set volume to 40
Jarvis: Volume set to 40 percent.

You: exit
```

## Project Structure

```
src/jarvis/
├── main.py              # Entry point, REPL loop
├── core/
│   ├── brain.py         # LLM client, streaming, tool dispatch
│   ├── listener.py      # Whisper-based voice transcription
│   └── speaker.py       # macOS text-to-speech
├── skills/
│   ├── system_control.py  # open_app, open_url, set_volume, run_command
│   ├── utils.py           # time, date, notes, calculator
│   └── web_search.py      # DuckDuckGo search
├── memory/
│   └── conversation.py  # SQLite-backed conversation history
config/
└── settings.yaml        # Runtime configuration
```

## Tests

```bash
pytest
```
