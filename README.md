# AI Trainer

A Home Assistant custom integration that turns the
[FaserF/ha-whatsapp](https://github.com/FaserF/ha-whatsapp) bot into a personal
Hebrew health coach.

Send the bot a WhatsApp message and it creates a user, asks for the goal,
weight and height in Hebrew, then sends a daily plan for food, water and
exercise. Everything is managed from a sidebar panel inside Home Assistant:
users, plans, chat history, AI provider, API keys and the schedule.

```
WhatsApp  ──event──▶  ai_trainer  ──▶  AI provider (OpenAI / Anthropic / Google / DeepSeek / Ollama)
   ▲                        │
   └──── whatsapp.send_message ────┘
```

## Features

- **Automatic user creation** — the first inbound message starts onboarding
  (goal → weight → height) in Hebrew.
- **Daily coaching** — a morning plan with meals, water target and a workout,
  plus configurable water and workout reminders.
- **Conversation** — free chat, meal check-ins, weight updates, water logging,
  workout completion, status, pause/resume and a two-step reset.
- **Any AI, or none** — OpenAI, Anthropic, Google Gemini, DeepSeek, any
  OpenAI-compatible endpoint and local Ollama. Without a key the bot still
  works using a deterministic Hebrew plan.
- **Hebrew first** — every prompt, fallback plan and message is Hebrew, RTL UI
  included.
- **Admin panel** — dashboard, users table, per-user profile/plan/chat, manual
  messages, provider and WhatsApp tests, live activity log.
- **Safe by default** — admin-only panel and REST API, write-only API keys,
  optional phone allow-list, group messages ignored unless enabled, user cap.

> **Publishing note:** update `documentation` / `issue_tracker` in
> `custom_components/ai_trainer/manifest.json` to your repository URL before
> publishing, and keep the `version` field in sync with `hacs.json`.

## Requirements

| Item | Version |
| --- | --- |
| Home Assistant | 2024.7 or newer |
| [ha-whatsapp](https://github.com/FaserF/ha-whatsapp) | installed and connected |
| Python | 3.12+ (bundled with Home Assistant) |

ha-whatsapp must be configured with a working WhatsApp session, because it
provides the `whatsapp_message_received` event and the
`whatsapp.send_message` service used by this integration.

## Installation

### Manual

1. Copy the folder `custom_components/ai_trainer` into your Home Assistant
   configuration directory so you get `/config/custom_components/ai_trainer`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for
   **AI Trainer**.
4. Pick an AI provider. The API key is optional here; you can add it later in
   the panel. Set the daily plan time and save.
5. Open **AI Trainer** in the sidebar.

### HACS (custom repository)

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add this repository URL with category **Integration**.
3. Install **AI Trainer**, restart Home Assistant, then add the integration as
   above.

## Configuration

The initial dialog asks for:

- **AI provider** — OpenAI, Anthropic, Google Gemini, DeepSeek, Ollama or
  OpenAI-compatible.
- **API key** — optional at setup, write-only afterwards.
- **Model** — empty means the provider default.
- **WhatsApp account** — only needed when several accounts are configured.
- **Daily plan time** — local time, `HH:MM`.

Everything else lives in the panel (**Settings** tab) or in
**Settings → Devices & services → AI Trainer → Configure**:

- **AI** — provider, model, base URL, temperature, max tokens, key management.
- **WhatsApp** — send service, account, allow groups, phone allow-list.
- **Schedule** — daily plan, water reminder times, workout reminder time.
- **Limits** — maximum users, minimum seconds between AI calls.
- **Coach persona** — coach name and extra system-prompt instructions.

### Examples

**OpenAI**

```
provider: openai
model:    gpt-4o-mini
api_key:  sk-...
```

**Ollama (local, no key)**

```
provider: ollama
model:    llama3.1:8b
base_url: http://homeassistant.local:11434
```

If Home Assistant runs in Docker or on a different host, point `base_url` at
the machine running Ollama, e.g. `http://192.168.1.50:11434`, and make sure
Ollama listens on `0.0.0.0` (`OLLAMA_HOST=0.0.0.0`).

**Any OpenAI-compatible server** (LM Studio, vLLM, OpenRouter, …)

```
provider: openai_compatible
model:    the-model-name
base_url: http://192.168.1.50:1234/v1
api_key:  optional
```

## Usage

Send any text to the WhatsApp number connected to ha-whatsapp.

| Message | Result |
| --- | --- |
| anything new | Creates the user and starts onboarding |
| `1`–`4` | Goal: lose weight / build muscle / maintain / healthy lifestyle |
| free-text goal | Accepted and stored for the AI |
| `78.5` | Weight in kg (pounds are converted) |
| `175` or `1.75` | Height in cm |
| `תפריט` / `plan` | Today's plan |
| `שתיתי 2` | Log 2 cups of water (250 ml each) |
| `שקלתי 77.4` | Update weight |
| `סיימתי אימון` | Mark today's workout as done |
| `סטטוס` | Progress summary |
| `עצור` / `הפעל` | Pause / resume reminders |
| `איפוס` then `כן` | Reset the profile and restart onboarding |
| `עזרה` | Command list |

### Panel

The sidebar panel has three areas:

1. **Dashboard** — users, messages today, provider and WhatsApp status,
   schedule overview, recent activity.
2. **Users** — search, add a user manually, open a user to see profile, goals
   and BMI, today's plan, and the conversation history. From here you can
   generate/send a plan, send a manual message, simulate an inbound message,
   pause/resume, reset onboarding or delete the user.
3. **Settings** — all provider, WhatsApp and schedule settings, plus
   connectivity tests for the AI provider and WhatsApp.

## Services

| Service | Fields | Purpose |
| --- | --- | --- |
| `ai_trainer.send_daily_plan` | `phone` (optional), `force` | Build and send today's plan to one user or all active users |
| `ai_trainer.send_message` | `phone`, `message` | Send a manual WhatsApp message |
| `ai_trainer.ask` | `phone`, `prompt` | Run a prompt through the bot as if the user wrote it |
| `ai_trainer.reset_user` | `phone` | Clear the profile and restart onboarding |

## Entities

- `sensor.ai_trainer_users`
- `sensor.ai_trainer_active_users`
- `sensor.ai_trainer_messages_today`
- `binary_sensor.ai_trainer_whatsapp` — WhatsApp send service available

## Data and privacy

- Users, chat history and plans are stored in
  `/config/.storage/ai_trainer.<entry_id>` inside your Home Assistant config.
- API keys are stored in the config entry, are never returned by the REST API
  or the panel, and are redacted from diagnostics.
- Messages are sent to the configured AI provider only for users who write to
  the bot. With Ollama, no data leaves your network.
- Health values and plans are general estimates, not medical advice.

## Troubleshooting

**No sidebar panel** — check **Settings → System → Logs** for `ai_trainer`
errors, then restart Home Assistant. The panel is registered only for admin
users.

**"WhatsApp service is not available"** — ha-whatsapp is not loaded or the
service name differs. Check the service in Developer Tools → Actions and put
the exact name in the panel's WhatsApp settings.

**Bot does not answer** — verify the WhatsApp integration receives messages
(its own log) and that the sender is not blocked by the allow-list. Group
messages are ignored unless **Allow group chats** is enabled.

**AI errors** — use **Test AI** in the panel. A 401 means a bad key, 429 means
rate limiting. The bot falls back to the built-in Hebrew plan so users still
get a plan.

**Ollama timeouts** — the first request loads the model and can take a while;
90 seconds are allowed per request. Check `base_url` from the Home Assistant
host with `curl http://host:11434/api/tags`.

## Development

The pure logic in `custom_components/ai_trainer/core` has no Home Assistant
dependency and is covered by unit tests:

```bash
python -m unittest discover -s tests -v
# or
python -m pytest tests -q
```

Layout:

```
custom_components/ai_trainer/
├── __init__.py        setup / unload
├── agent.py           conversation, onboarding, plans
├── ai/                provider implementations
├── core/              pure Python parsing, metrics, plans, prompts
├── frontend/          sidebar panel (vanilla JS web component)
├── http.py            admin REST API
├── runtime.py         wiring, stats, panel payloads
├── scheduler.py       daily / water / workout reminders
├── store.py           persistent users
└── whatsapp.py        ha-whatsapp bridge
```

## License

MIT — use it, change it, share it.
