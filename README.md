# 🩺 Curer — Pre-Consultation AI Intake Bot

An AI-powered pre-consultation intake assistant that collects patient symptoms and history before a doctor visit. The bot asks tailored questions based on the selected medical specialty, generates a structured Doctor's Briefing Card, and automatically emails it to the doctor.

## Features

- **6 Medical Specialties** — GP, Cardiology, Dermatology, Orthopedics, Pediatrics, Gynecology
- **Conversational AI** — Natural, empathetic intake questions powered by LLaMA 3.1
- **Streaming Responses** — Real-time AI responses for a smooth experience
- **Doctor's Briefing Card** — Styled summary with symptoms, severity, red flags, and focus areas
- **Auto Email to Doctor** — Briefing card is automatically emailed (HTML + PDF attachment) when intake completes
- **PDF Export** — Download a Curer-branded briefing card PDF
- **Security Guardrails** — Input validation, rate limiting, abuse detection, prompt injection protection

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Streamlit |
| LLM Provider | Groq (llama-3.1-8b-instant) |
| PDF Generation | fpdf2 |
| Email | Gmail SMTP (smtplib + App Password) |
| Language | Python 3.10+ |

## Project Structure

```
curer/
├── app.py                          # Main Streamlit app with guardrails
├── prompts.py                      # 6 specialty-specific system prompts
├── email_sender.py                 # SMTP email with security (validation, rate limiting)
├── pdf_generator.py                # Curer-branded PDF generation
├── styles.py                       # Briefing card renderer (Streamlit components)
├── requirements.txt                # Python dependencies
├── .streamlit/
│   ├── config.toml                 # Curer teal theme
│   └── secrets.toml.example        # Secrets template (copy to secrets.toml)
└── README.md                       # This file
```

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/BhoomiNayak/AI-intake-bot-curer.git
cd AI-intake-bot-curer
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

Create a `.env` file in the project root:

```env
GROQ_API_KEY=gsk_your_key_here
GMAIL_ADDRESS=your.bot@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
DOCTOR_EMAIL=doctor@clinic.com
```

Or copy the secrets template for Streamlit:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

### 4. Run the app

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Credential Setup

### Groq API Key

1. Go to [console.groq.com](https://console.groq.com)
2. Create an account and generate an API key
3. Add it as `GROQ_API_KEY`

### Gmail App Password (for auto-email)

1. Create a Gmail account (recommend a dedicated bot account)
2. Enable **2-Factor Authentication** on the account
3. Go to: Google Account → Security → App Passwords
4. Generate a new app password for "Mail"
5. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)
6. Add as `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`

### Doctor's Email

Set `DOCTOR_EMAIL` to the address where briefings should be auto-sent. The patient does not need to enter any email — it's fully automatic.

## Security Features

### Conversation Guardrails

| Protection | Details |
|-----------|---------|
| Max turns | 10 user messages before forced briefing generation |
| Input length | 2-1000 characters per message |
| Token budget | ~8000 tokens max conversation length |
| Prompt injection | Regex detection for injection patterns (3 strikes = lockout) |
| Input sanitization | Control characters stripped, whitespace normalized |
| AI output filtering | Script/iframe tags and event handlers stripped |

### Email Security

| Protection | Details |
|-----------|---------|
| Email validation | RFC 5322 format check + domain validation |
| Blocked domains | Disposable email services rejected |
| Rate limiting | Max 3 emails/session, 30s cooldown between sends |
| HTML sanitization | All user content HTML-escaped before email insertion |
| SMTP timeout | 30s connection timeout |
| Error handling | Generic messages to user, no internals exposed |

## How It Works

1. **Patient selects specialty** — Appropriate system prompt loaded
2. **AI asks 3-4 questions** — One at a time, tailored to the specialty
3. **Patient answers** — Validated, sanitized, checked against guardrails
4. **AI generates summary** — Structured JSON with symptoms, severity, red flags
5. **Briefing card renders** — Styled card displayed on screen
6. **Email auto-sent** — HTML email + PDF attachment to configured doctor
7. **PDF available** — Patient can download for their records

## Deployment (Streamlit Cloud)

1. Push to GitHub (`.env` and `secrets.toml` are git-ignored)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo, select `app.py`
4. Add secrets in **Settings → Secrets**:
   ```toml
   GROQ_API_KEY = "gsk_..."
   GMAIL_ADDRESS = "your.bot@gmail.com"
   GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"
   DOCTOR_EMAIL = "doctor@clinic.com"
   ```
5. Deploy

## Configuration

### Theme

Configured in `.streamlit/config.toml`:
- Primary: `#0D9488` (teal)
- Background: `#FFFFFF` (white)
- Secondary: `#F0FDFA` (light teal)
- Text: `#1F2937` (dark gray)

### Model

Uses `llama-3.1-8b-instant` via Groq. Change in `app.py` → `stream_chat_response()`.

### Guardrail Tuning

Adjust constants at the top of `app.py`:
```python
MAX_USER_TURNS = 10
MAX_INPUT_LENGTH = 1000
MAX_TOTAL_CONVERSATION_TOKENS = 8000
```

## Disclaimer

This is not a substitute for professional medical advice, diagnosis, or treatment. Curer is a pre-consultation tool designed to organize patient information before a doctor visit. Always consult a qualified healthcare provider.

## License

MIT
