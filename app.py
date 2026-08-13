import os
import re
import json
import streamlit as st
from groq import Groq
from dotenv import load_dotenv

from prompts import get_system_prompt

# Load .env file
load_dotenv()

# --- Page Configuration ---
st.set_page_config(
    page_title="Curer - Pre-Consultation Intake",
    page_icon="🩺",
    layout="centered",
    initial_sidebar_state="expanded",
)

# --- Constants ---
SPECIALTIES = [
    "General Practitioner (GP)",
    "Cardiology",
    "Dermatology",
    "Orthopedics",
    "Pediatrics",
    "Gynecology",
]

# --- Conversation Guardrails ---
MAX_USER_TURNS = 10  # Max messages a user can send before forced completion
MAX_INPUT_LENGTH = 1000  # Max characters per user message
MAX_TOTAL_CONVERSATION_TOKENS = 8000  # Approximate token budget
MIN_INPUT_LENGTH = 2  # Minimum meaningful input

# Patterns indicating prompt injection or abuse attempts
ABUSE_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions?|prompts?)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"system\s*:\s*",
    r"forget\s+(everything|all|your)\s+(you|instructions?|rules?)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"act\s+as\s+(if|a|an)",
    r"new\s+instructions?\s*:",
    r"override\s+(your|the)\s+(instructions?|rules?|prompt)",
    r"disregard\s+(your|all|previous)",
    r"jailbreak",
]

ABUSE_REGEX = re.compile("|".join(ABUSE_PATTERNS), re.IGNORECASE)


# --- API Key Retrieval ---
def get_api_key() -> str:
    """Retrieve Groq API key from st.secrets or environment variable."""
    try:
        return st.secrets["GROQ_API_KEY"]
    except (KeyError, FileNotFoundError):
        return os.environ.get("GROQ_API_KEY", "")


# --- Initialize Session State ---
def init_session_state():
    """Initialize all session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "intake_complete" not in st.session_state:
        st.session_state.intake_complete = False
    if "intake_data" not in st.session_state:
        st.session_state.intake_data = None
    if "selected_specialty" not in st.session_state:
        st.session_state.selected_specialty = SPECIALTIES[0]
    if "conversation_started" not in st.session_state:
        st.session_state.conversation_started = False
    if "email_sent_to" not in st.session_state:
        st.session_state.email_sent_to = None
    if "pdf_bytes" not in st.session_state:
        st.session_state.pdf_bytes = None
    if "user_turn_count" not in st.session_state:
        st.session_state.user_turn_count = 0
    if "abuse_warnings" not in st.session_state:
        st.session_state.abuse_warnings = 0


def reset_conversation():
    """Reset the conversation state."""
    st.session_state.messages = []
    st.session_state.intake_complete = False
    st.session_state.intake_data = None
    st.session_state.conversation_started = False
    st.session_state.email_sent_to = None
    st.session_state.pdf_bytes = None
    st.session_state.user_turn_count = 0
    st.session_state.abuse_warnings = 0


# --- Guardrail Functions ---
def validate_user_input(text: str) -> tuple[bool, str]:
    """
    Validate user input for length, content, and abuse patterns.

    Returns (is_valid, error_message).
    """
    # Check minimum length
    if len(text.strip()) < MIN_INPUT_LENGTH:
        return False, "Please provide a more detailed response."

    # Check maximum length
    if len(text) > MAX_INPUT_LENGTH:
        return False, f"Message too long. Please keep your response under {MAX_INPUT_LENGTH} characters."

    # Check for prompt injection / abuse patterns
    if ABUSE_REGEX.search(text):
        st.session_state.abuse_warnings += 1
        if st.session_state.abuse_warnings >= 3:
            return False, "Session terminated due to repeated misuse. Please reset and use the app as intended."
        return False, "Please keep your responses relevant to your health concern."

    # Check max turns
    if st.session_state.user_turn_count >= MAX_USER_TURNS:
        return False, "Maximum conversation length reached. The AI will now generate your briefing."

    return True, ""


def check_conversation_budget() -> bool:
    """Check if conversation is within token budget (approximate)."""
    total_chars = sum(len(m["content"]) for m in st.session_state.messages)
    # Rough estimate: 1 token ~ 4 chars
    estimated_tokens = total_chars // 4
    return estimated_tokens < MAX_TOTAL_CONVERSATION_TOKENS


def sanitize_input(text: str) -> str:
    """Basic input sanitization — strip control characters, normalize whitespace."""
    # Remove null bytes and control characters (keep newlines/tabs)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalize excessive whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {3,}", "  ", cleaned)
    return cleaned.strip()


# --- Core Functions ---
def parse_intake_json(text: str) -> dict | None:
    """Extract and parse the JSON intake summary from AI response."""
    start_marker = "<<<INTAKE_COMPLETE>>>"
    end_marker = "<<<END_INTAKE>>>"

    if start_marker in text and end_marker in text:
        start_idx = text.index(start_marker) + len(start_marker)
        end_idx = text.index(end_marker)
        json_str = text[start_idx:end_idx].strip()

        # Guard against oversized JSON payloads (max 5KB)
        if len(json_str) > 5000:
            return None

        try:
            data = json.loads(json_str)
            # Validate expected keys exist
            required_keys = {"patient_summary", "chief_complaint", "symptoms"}
            if not required_keys.issubset(data.keys()):
                return None
            # Validate types
            if not isinstance(data.get("symptoms"), list):
                return None
            return data
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
    return None


def get_display_text(text: str) -> str:
    """Remove JSON markers from displayed text and sanitize for safe rendering."""
    start_marker = "<<<INTAKE_COMPLETE>>>"
    if start_marker in text:
        text = text[:text.index(start_marker)].strip()
    # Strip any raw HTML tags from AI output to prevent XSS via LLM injection
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<iframe[^>]*>.*?</iframe>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"on\w+\s*=\s*[\"'][^\"']*[\"']", "", text, flags=re.IGNORECASE)
    return text


def stream_chat_response(client: Groq, specialty: str):
    """Stream a chat response from Groq and handle intake completion."""
    system_prompt = get_system_prompt(specialty)

    messages_for_api = [{"role": "system", "content": system_prompt}]
    messages_for_api.extend(
        [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    )

    try:
        stream = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages_for_api,
            temperature=0.7,
            max_tokens=1024,
            stream=True,
        )

        full_response = ""
        response_placeholder = st.empty()

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                full_response += chunk.choices[0].delta.content
                # Display without JSON markers
                display_text = get_display_text(full_response)
                if display_text:
                    response_placeholder.markdown(display_text)

        # Check if intake is complete
        intake_data = parse_intake_json(full_response)
        if intake_data:
            st.session_state.intake_complete = True
            st.session_state.intake_data = intake_data

        # Store the full response
        st.session_state.messages.append(
            {"role": "assistant", "content": full_response}
        )

        return full_response

    except Exception as e:
        error_msg = str(e)
        # Don't expose internal details to user — log-safe generic message
        if "api_key" in error_msg.lower() or "auth" in error_msg.lower():
            st.error("⚠️ API authentication error. Please check your Groq API key.")
        elif "rate" in error_msg.lower() or "limit" in error_msg.lower():
            st.error("⚠️ Rate limit reached. Please wait a moment and try again.")
        elif "timeout" in error_msg.lower() or "connect" in error_msg.lower():
            st.error("⚠️ Connection timeout. Please check your internet and try again.")
        else:
            st.error("⚠️ An error occurred while communicating with the AI. Please try again.")
        return None


# --- Sidebar ---
def render_sidebar():
    """Render the sidebar with app info and branding."""
    with st.sidebar:
        st.markdown(
            """
            <div style="text-align: center; padding: 1rem 0;">
                <h2 style="color: #0D9488; margin-bottom: 0.5rem;">🩺 Curer</h2>
                <p style="color: #6B7280; font-size: 0.9rem;">AI-Powered Pre-Consultation Intake</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown("### How it works")
        st.markdown(
            """
            1. **Select** your doctor's specialty
            2. **Answer** 3-4 tailored questions from the AI
            3. **Receive** a Doctor's Briefing Card
            4. **Briefing auto-sent** to your doctor via email
            5. **Download** the PDF for your records
            """
        )
        st.divider()

        st.markdown("### About")
        st.markdown(
            """
            Curer streamlines your doctor visit by collecting relevant
            health information before your consultation. Your responses
            are summarized into a concise briefing for your doctor.
            """
        )
        st.divider()

        # Show conversation stats
        if st.session_state.get("conversation_started", False):
            turns = st.session_state.get("user_turn_count", 0)
            st.caption(f"Messages sent: {turns}/{MAX_USER_TURNS}")

        st.markdown(
            """
            <div style="text-align: center; color: #9CA3AF; font-size: 0.8rem;">
                <p>Powered by Groq &bull; LLaMA 3.1</p>
                <p>⚠️ Not a substitute for medical advice</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# --- Main App ---
def main():
    init_session_state()
    render_sidebar()

    # --- Header ---
    st.markdown(
        """
        <div style="text-align: center; padding: 1rem 0 0.5rem 0;">
            <h1 style="color: #0D9488; margin-bottom: 0.2rem;">🩺 Curer</h1>
            <p style="color: #6B7280; font-size: 1.1rem;">Pre-Consultation AI Intake</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Check for abuse lockout ---
    if st.session_state.abuse_warnings >= 3:
        st.error("Session locked due to repeated misuse. Please click Reset to start over.")
        if st.button("🔄 Reset Session"):
            reset_conversation()
            st.rerun()
        st.stop()

    # --- API Key Check ---
    api_key = get_api_key()
    if not api_key:
        st.warning(
            "⚠️ Groq API key not found. Please set `GROQ_API_KEY` in "
            "`.streamlit/secrets.toml` or as an environment variable."
        )
        st.stop()

    client = Groq(api_key=api_key)

    # --- Specialty Selection ---
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_specialty = st.selectbox(
            "Select your consultation specialty:",
            options=SPECIALTIES,
            index=SPECIALTIES.index(st.session_state.selected_specialty),
            disabled=st.session_state.conversation_started,
            help="Choose the type of doctor you're seeing. Locked once the conversation starts.",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Reset", use_container_width=True):
            reset_conversation()
            st.rerun()

    # Update specialty in session if changed before conversation starts
    if not st.session_state.conversation_started:
        st.session_state.selected_specialty = selected_specialty

    st.divider()

    # --- Chat Display ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            display_text = get_display_text(message["content"])
            if display_text:
                st.markdown(display_text)

    # --- Intake Complete: Show Briefing Card ---
    if st.session_state.intake_complete and st.session_state.intake_data:
        from styles import render_briefing_card
        from pdf_generator import generate_pdf, get_download_button
        from email_sender import send_briefing_email, get_doctor_email

        st.divider()
        render_briefing_card(st.session_state.intake_data, st.session_state.selected_specialty)

        # Generate PDF once and cache in session
        if st.session_state.pdf_bytes is None:
            st.session_state.pdf_bytes = generate_pdf(
                st.session_state.intake_data, st.session_state.selected_specialty
            )

        pdf_bytes = st.session_state.pdf_bytes

        # --- Auto-send email to doctor ---
        doctor_email = get_doctor_email()

        if doctor_email and pdf_bytes and not st.session_state.email_sent_to:
            with st.spinner("📧 Sending briefing to your doctor..."):
                try:
                    send_briefing_email(
                        recipient=doctor_email,
                        intake_data=st.session_state.intake_data,
                        specialty=st.session_state.selected_specialty,
                        pdf_bytes=pdf_bytes,
                    )
                    st.session_state.email_sent_to = doctor_email
                    st.success(f"✅ Briefing automatically sent to your doctor")
                except ValueError as e:
                    st.error(f"⚠️ Email configuration issue. Please contact support.")
                except RuntimeError:
                    st.error(f"⚠️ Failed to send email. Please try again later.")
                except Exception:
                    st.error(f"⚠️ An unexpected error occurred while sending the email.")

        elif st.session_state.email_sent_to:
            st.success("✅ Briefing sent to your doctor")

        elif not doctor_email:
            st.info("ℹ️ Doctor's email not configured. Set `DOCTOR_EMAIL` in .env to enable auto-send.")

        # PDF Download button
        if pdf_bytes:
            get_download_button(pdf_bytes)

    # --- Chat Input ---
    if not st.session_state.intake_complete:
        # Check if max turns reached — force completion
        if st.session_state.user_turn_count >= MAX_USER_TURNS and not st.session_state.intake_complete:
            st.warning("Maximum conversation length reached. Generating your briefing now...")
            # Add a hint to the AI to wrap up
            st.session_state.messages.append(
                {"role": "user", "content": "Please generate my briefing summary now."}
            )
            with st.chat_message("assistant"):
                stream_chat_response(client, st.session_state.selected_specialty)
            st.rerun()

        if prompt := st.chat_input(
            "Type your response here...",
            max_chars=MAX_INPUT_LENGTH,
        ):
            # Sanitize input
            prompt = sanitize_input(prompt)

            # Validate input
            is_valid, error_msg = validate_user_input(prompt)
            if not is_valid:
                st.warning(f"⚠️ {error_msg}")
                st.stop()

            # Check conversation budget
            if not check_conversation_budget():
                st.warning("Conversation is getting long. The AI will summarize your intake now.")
                st.session_state.messages.append(
                    {"role": "user", "content": "Please generate my briefing summary now."}
                )
                with st.chat_message("assistant"):
                    stream_chat_response(client, st.session_state.selected_specialty)
                st.rerun()

            # Process valid input
            st.session_state.conversation_started = True
            st.session_state.user_turn_count += 1
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                stream_chat_response(client, st.session_state.selected_specialty)

            st.rerun()

    # --- Auto-start conversation ---
    if not st.session_state.conversation_started and not st.session_state.messages:
        st.session_state.conversation_started = True
        with st.chat_message("assistant"):
            stream_chat_response(client, st.session_state.selected_specialty)
        st.rerun()


if __name__ == "__main__":
    main()
