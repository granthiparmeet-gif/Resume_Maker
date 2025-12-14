import json
import os
import re
import textwrap
import math
from datetime import date

import openai
import streamlit as st
from dotenv import load_dotenv
from fpdf import FPDF

load_dotenv(dotenv_path=".env")
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    st.warning(
        "OPENAI_API_KEY is not set. Add it to your environment or the .env file before proceeding."
    )

PROJECT_TITLE_PREFIX = "PROJECT_TITLE::"
BOLD_DETECTION_PATTERN = re.compile(r"\*\*\s*(.+?)\s*\*\*")
PROJECT_TITLE_BOLD_PATTERN = re.compile(r"^\*\s*\*\s*(.+?)\s*\*\*\s*$")

# -----------------------------
# Load Resume Template From File
# -----------------------------
PREFERRED_TEMPLATE_NAMES = [
    "Parmeet_Singh_Resume_Template.pdf",
    "Resume_Parmeet_Singh.pdf",
    "parmeet_singh_resume.pdf",
]
PRIMARY_EMAIL = "parmeet.singh@parmeetsingh.com"
TEMPLATE_PATH = next(
    (path for path in PREFERRED_TEMPLATE_NAMES if os.path.exists(path)),
    PREFERRED_TEMPLATE_NAMES[0],
)


def extract_text_from_pdf(source):
    """Return all text extracted from a PDF path or file-like object, normalized."""
    import PyPDF2

    close_after = False
    if isinstance(source, (str, os.PathLike)):
        source = open(source, "rb")
        close_after = True
    else:
        source.seek(0)

    try:
        try:
            import pdfplumber  # type: ignore

            with pdfplumber.open(source) as pdf:
                text = "\n".join(
                    (page.extract_text(layout=True) or "").rstrip()
                    for page in pdf.pages
                ).strip()
            if text:
                return text
        except Exception:
            pass

        reader = PyPDF2.PdfReader(source)
        raw = "\n".join(
            (page.extract_text() or "").rstrip() for page in reader.pages
        ).rstrip()
        tokens = raw.replace("\n", " ").split()
        combined = " ".join(tokens)
        return textwrap.fill(combined, width=75, break_long_words=False)
    finally:
        if close_after:
            source.close()


if os.path.exists(TEMPLATE_PATH):
    TEMPLATE_TEXT = extract_text_from_pdf(TEMPLATE_PATH)
else:
    TEMPLATE_TEXT = ""


def sanitize_job_role_candidate(role_text: str) -> str:
    """Drop seniority words so the job title stays functional."""
    if not role_text:
        return "Software Engineer"
    cleaned = re.sub(
        r"\b(Senior|Sr\.?|Lead|Principal|Director|Head|Manager|Mgr|VP|Vice\s+President|Staff|Junior|Jr\.?)\b",
        "",
        role_text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not cleaned:
        return "Software Engineer"
    return cleaned


ROLE_INDICATORS = {
    "engineer",
    "developer",
    "architect",
    "scientist",
    "analyst",
    "specialist",
    "consultant",
    "tester",
    "qa",
    "technician",
    "manager",
    "lead",
    "director",
    "officer",
    "designer",
    "programmer",
    "coordinator",
    "administrator",
    "researcher",
    "developer",
}


def infer_job_role_from_description(description: str) -> str | None:
    """Return a plausible job role phrase from the description."""
    if not description:
        return None

    lines = [line.strip() for line in description.splitlines() if line.strip()]
    label_pattern = re.compile(r"(?:Job Title|Role|Position)\s*[:\-]\s*(.+)", re.IGNORECASE)
    for line in lines:
        match = label_pattern.match(line)
        if match:
            return match.group(1).strip()

    desc_pattern = re.compile(
        r"^\s*(?:As\s+)?(?:a|an|the)\s+(.+?)(?:,| who\b| that\b| will\b| for\b| in\b| on\b| where\b|$)",
        re.IGNORECASE,
    )
    for line in lines:
        match = desc_pattern.match(line)
        if match:
            return match.group(1).strip()

    word_pattern = re.compile(r"[A-Za-z&/+-]+")
    for line in lines:
        words = word_pattern.findall(line)
        for window_size in range(min(5, len(words)), 1, -1):
            for start in range(0, len(words) - window_size + 1):
                window = words[start : start + window_size]
                lower_words = [word.lower() for word in window]
                if any(indicator in word for word in lower_words for indicator in ROLE_INDICATORS):
                    if set(lower_words) & {"role", "job", "responsibilities", "responsibility"}:
                        continue
                    return " ".join(window)
    return None


def extract_kiran_role_from_description(description: str) -> str | None:
    """Extract the role reference seeded near Kiran Engineering Works when possible."""
    if not description:
        return None
    pattern = re.compile(r"Kiran Engineering Works\s*[–—-]\s*([^\n\r]+)", re.IGNORECASE)
    match = pattern.search(description)
    if match:
        fragment = match.group(1).strip()
        fragment = re.sub(
            r"^(?:As\s+)?(?:a|an|the)\s+", "", fragment, flags=re.IGNORECASE
        )
        split_pattern = re.compile(
            r",|\bwho\b|\bwill\b|\bwhere\b|\bthat\b|\bin\b|\bfor\b|\bat\b", re.IGNORECASE
        )
        role_text = re.split(split_pattern, fragment, maxsplit=1)[0].strip()
        role_text = role_text.strip(":-–— ")
        words = role_text.split()
        if words:
            return " ".join(words[:5])
    return infer_job_role_from_description(description)


# -----------------------------
# PDF Generator
# -----------------------------
def generate_pdf(
    text,
    job_role,
    selected_format="LinkedIn + Projects",
    doc_label="resume",
    fit_page=True,
):
    tokens = [t for t in re.split(r"[_\s]+", job_role) if t]
    short_role = "_".join(tokens[:4]) if tokens else "Role"
    if len(short_role) > 40:
        short_role = short_role[:40].rstrip("_")
    filename = f"Parmeet_Singh_{short_role}_{doc_label}.pdf"
    raw_lines = text.split("\n")
    lines = [ln for ln in raw_lines if ln is not None]
    total_lines = max(len(lines), 1)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    left_margin = 7
    right_margin = 7
    top_margin = 15
    bottom_margin = 7
    pdf.set_margins(left_margin, top_margin, right_margin)

    available_height = pdf.h - top_margin - bottom_margin
    usable_width = pdf.w - left_margin - right_margin

    base_font_size = 11
    def normalize_line(text_line: str) -> str:
        # Normalize dashes and bullets so they survive Latin-1 encoding.
        cleaned = text_line.replace("–", "-").replace("—", "-").replace("‑", "-").replace("•", "-")
        cleaned = re.sub(r"\s\?\s", " - ", cleaned)
        cleaned = re.sub(r"\s\?(\W|$)", r" -\1", cleaned)
        cleaned = re.sub(r"(\W|^)\?\s", r"\1- ", cleaned)
        cleaned = cleaned.replace("?", "-")
        return (cleaned.encode("latin-1", "replace").decode("latin-1")) or " "

    safe_lines = [normalize_line(line) for line in lines]

    def normalize_project_heading_line(line: str) -> str:
        stripped = line.strip()
        match = PROJECT_TITLE_BOLD_PATTERN.match(stripped)
        if match:
            return f"{PROJECT_TITLE_PREFIX}{match.group(1).strip()}"
        return line

    def limit_line_width(line: str) -> str:
        """Limit lines to ~75 characters using textwrap.fill while keeping a single line."""
        if not line.strip():
            return line
        wrapped = textwrap.fill(line, width=75, break_long_words=False)
        return " ".join(wrapped.splitlines())

    safe_lines = [
        limit_line_width(normalize_project_heading_line(ln)) for ln in safe_lines
    ]

    # Determine body font size to fit longest line within width, but keep standard size
    # for the Experience-Focused layout so the text never shrinks.
    font_size = base_font_size
    pdf.set_font("Arial", size=font_size)

    # Line height scaled to fill the page without overflow.
    line_height = available_height / total_lines
    min_line_height = font_size * 1.15
    max_line_height = font_size * 1.5 if not fit_page else float("inf")
    line_height = min(line_height, max_line_height)
    if line_height < min_line_height:
        line_height = min_line_height

    BULLET_MARGIN_RATIO = 0.15
    bullet_width_limit = usable_width * (1 - BULLET_MARGIN_RATIO)

    blank_line_height = (
        line_height * 0.5
        if selected_format == "Experience-Focused (No LinkedIn/Projects)"
        else line_height
    )

    name_size = max(font_size + 6, 16)
    heading_size = max(font_size + 2, font_size * 1.2)
    project_heading_size = max(font_size, heading_size * 0.75)

    def is_heading(text_line: str) -> bool:
        stripped = text_line.strip()
        if not stripped:
            return False
        known = {
            "Professional Summary",
            "Experience",
            "Work Experience",
            "Education",
            "Projects",
            "Skills",
            "Core Skills",
            "Additional Information",
        }
        if stripped in known:
            return True
        if stripped.isupper() and len(stripped) <= 40:
            return True
        words = stripped.split()
        if len(words) <= 5 and all(w[:1].isupper() for w in words):
            return True
        return False

    def is_company_role(text_line: str) -> bool:
        stripped = text_line.strip()
        if not stripped:
            return False
        # Heuristic: contains a dash or bullet separating company and role, but not a section heading.
        if " - " in stripped or " — " in stripped or " – " in stripped:
            return True
        return False

    def reflow_block(lines_block):
        """Reflow a block of body lines to the same count, distributing words evenly."""
        if not lines_block:
            return []
        words = []
        for ln in lines_block:
            words.extend(ln.split())
        target = len(lines_block)
        out = []
        idx = 0
        for i in range(target):
            remaining_lines = target - i
            remaining_words = len(words) - idx
            take = max(1, math.ceil(remaining_words / remaining_lines))
            segment = " ".join(words[idx : idx + take])
            out.append(segment)
            idx += take
        return out

    def wrap_text_to_width(text_line: str) -> list[str]:
        """Wrap a paragraph so each line fits within the usable width."""
        cleaned = text_line.strip()
        if not cleaned:
            return [""]
        pdf.set_font("Arial", "", font_size)
        words = cleaned.split()
        lines = []
        current_line = words[0]
        for word in words[1:]:
            candidate = f"{current_line} {word}"
            if pdf.get_string_width(candidate) <= usable_width:
                current_line = candidate
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines

    def wrap_bullet_line(text_line: str) -> list[str]:
        stripped = text_line.lstrip()
        bullet_char = "-"
        remainder = stripped
        if stripped and stripped[0] in "-•*–":
            bullet_char = stripped[0]
            remainder = stripped[1:].lstrip()
        segments = wrap_text_to_width(remainder)
        if not segments:
            return [f"{bullet_char} "]
        lines = []
        for idx, segment in enumerate(segments):
            prefix = f"{bullet_char} " if idx == 0 else "  "
            lines.append(f"{prefix}{segment}")
        return lines

    def format_single_line_bullet(text_line: str) -> str:
        """Shrink a bullet entry so it fits on exactly one line within the usable width."""
        stripped = text_line.lstrip()
        bullet_char = "-"
        remainder = stripped
        if stripped and stripped[0] in "-•*–":
            bullet_char = stripped[0]
            remainder = stripped[1:].lstrip()
        if not remainder:
            return f"{bullet_char} "
        prefix = f"{bullet_char} "
        pdf.set_font("Arial", "", font_size)
        words = remainder.split()
        candidate = " ".join(words)
        while words and pdf.get_string_width(prefix + candidate) > bullet_width_limit:
            words.pop()
            candidate = " ".join(words)
        if not words:
            candidate = remainder
        while candidate and pdf.get_string_width(prefix + candidate) > bullet_width_limit:
            candidate = candidate[:-1].rstrip()
        if not candidate:
            candidate = remainder[:1]
        return f"{prefix}{candidate}"

    def enforce_skill_list_length(text_line: str) -> str:
        """Drop the final skill when the category exceeds seven words after the colon."""
        stripped = text_line.lstrip()
        bullet_char = "-"
        remainder = stripped
        if stripped and stripped[0] in "-•*–":
            bullet_char = stripped[0]
            remainder = stripped[1:].lstrip()
        if ":" not in remainder:
            return text_line
        category, skills = remainder.split(":", 1)
        cleaned_skills = skills.strip()
        if len(cleaned_skills.replace(",", " ").split()) <= 7:
            return text_line
        if "," in cleaned_skills:
            segments = [seg.strip() for seg in cleaned_skills.split(",") if seg.strip()]
            if len(segments) > 1:
                segments = segments[:-1]
            cleaned_skills = ", ".join(segments)
        else:
            words = cleaned_skills.split()
            cleaned_skills = " ".join(words[:-1])
        updated = cleaned_skills.strip()
        if not updated:
            return text_line
        return f"{bullet_char} {category.strip()}: {updated}"

    def is_bullet_line(text_line: str) -> bool:
        stripped = text_line.lstrip()
        return stripped.startswith(("-", "•", "*", "–"))

    def detect_bold_line(text_line: str) -> tuple[str, bool, bool]:
        """Return the cleaned text and whether it should be bold or treated as a project title."""
        stripped = text_line.strip()
        if stripped.startswith(PROJECT_TITLE_PREFIX):
            return stripped[len(PROJECT_TITLE_PREFIX) :].strip(), True, True
        match = BOLD_DETECTION_PATTERN.search(text_line)
        if match:
            cleaned_line = (
                text_line[: match.start()]
                + match.group(1)
                + text_line[match.end() :]
            )
            return cleaned_line, True, False
        return text_line, False, False

    def render_contact_line(line_text: str):
        segments = [seg.strip() for seg in line_text.split("|") if seg.strip()]
        if selected_format == "Experience-Focused (No LinkedIn/Projects)":
            email_seg = None
            phone_seg = None
            for seg in segments:
                lower = seg.lower()
                if "@" in seg:
                    email_seg = seg
                elif any(ch.isdigit() for ch in seg):
                    phone_seg = seg
            ordered = []
            if phone_seg:
                ordered.append(phone_seg)
            if email_seg:
                ordered.append(email_seg)
            segments = ordered
        pdf.set_font("Arial", "", font_size)
        pdf.set_text_color(0, 0, 0)
        x_start = left_margin
        y_start = pdf.get_y()
        text_widths = []
        links = []
        for seg in segments:
            link = None
            seg_clean = seg.rstrip(",")
            if "@" in seg:
                link = f"mailto:{seg}"
            elif "http" in seg.lower() or "www." in seg.lower():
                url = seg if seg.lower().startswith("http") else f"https://{seg}"
                link = url
            elif "parmeetsingh.com" in seg.lower():
                link = "https://parmeetsingh.com"
            elif "linkedin" in seg.lower():
                link = "https://linkedin.com"
            links.append(link)
            text_widths.append(pdf.get_string_width(seg_clean))

        total_text_width = sum(text_widths) + max(len(segments) - 1, 0) * pdf.get_string_width(" | ")
        x_start = left_margin + (usable_width - total_text_width) / 2 if total_text_width < usable_width else left_margin
        pdf.set_xy(x_start, y_start)
        for idx, seg in enumerate(segments):
            link = links[idx]
            if link:
                pdf.set_text_color(0, 0, 255)
            else:
                pdf.set_text_color(0, 0, 0)
            pdf.cell(text_widths[idx], line_height, seg, ln=0, align="C", link=link)
            pdf.set_text_color(0, 0, 0)
            if idx < len(segments) - 1:
                pdf.cell(pdf.get_string_width(" | "), line_height, " | ", ln=0, align="C")
        pdf.ln(blank_line_height)

    def render_body_line(line_text: str):
        # Detect a single URL-like token for hyperlinking.
        url_match = re.search(r"(https?://\S+|www\.\S+|parmeetsingh\.com)", line_text)
        link = None
        if url_match:
            url = url_match.group(1)
            link = url if url.startswith("http") else f"https://{url}"
        if link:
            pdf.set_text_color(0, 0, 255)
        else:
            pdf.set_text_color(0, 0, 0)
        render_text = line_text
        bold_mode = False
        if (
            line_text.startswith("**")
            and line_text.endswith("**")
            and len(line_text) > 4
        ):
            render_text = line_text[2:-2].strip()
            bold_mode = True
        pdf.set_font("Arial", "B" if bold_mode else "", font_size)
        pdf.cell(usable_width, line_height, render_text, ln=1, align="J", link=link)
        pdf.set_text_color(0, 0, 0)
        if bold_mode:
            pdf.set_font("Arial", "", font_size)

    # Header rendering: use first non-empty as name, second non-empty as contact.
    pdf.set_xy(left_margin, top_margin)
    heading_count = 0
    line_idx = 0
    name_line = ""
    contact_line = ""
    current_section = None
    for ln in safe_lines:
        if ln.strip():
            name_line = ln.strip()
            break
        line_idx += 1
    line_idx += 1
    for ln in safe_lines[line_idx:]:
        if ln.strip():
            contact_line = ln.strip()
            break
        line_idx += 1

    no_line_after_contact = selected_format == "Experience-Focused (No LinkedIn/Projects)"
    if name_line:
        name_line = re.sub(r"\s{2,}", " ", name_line)
        pdf.set_font("Arial", "B", name_size)
        pdf.cell(usable_width, line_height, name_line, ln=1, align="C")
    if contact_line:
        render_contact_line(contact_line)
        y = pdf.get_y() + (1.0 if no_line_after_contact else 1.5)
        if not no_line_after_contact:
            pdf.line(left_margin, y, pdf.w - right_margin, y)
            pdf.set_y(y + 3)
        else:
            pdf.set_y(y + 1)

    start_idx = 0
    # Skip consumed lines
    consumed = [name_line, contact_line]
    for idx, line in enumerate(safe_lines):
        if line.strip() in consumed:
            start_idx = idx + 1

    expect_company_meta = False
    education_keywords = [
        "B.E. Computer Science Engineering",
        "Computer Science Engineering - PESCOE",
    ]

    idx = start_idx
    project_heading_count = 0
    in_skills_section = False
    while idx < len(safe_lines):
        line = safe_lines[idx]
        stripped = line.strip()

        render_line, _, is_project_title = detect_bold_line(line)
        if is_project_title and stripped:
            if project_heading_count > 0:
                pdf.ln(blank_line_height)
            pdf.set_font("Arial", "B", project_heading_size)
            pdf.cell(usable_width, line_height, render_line, ln=1, align="L")
            pdf.set_font("Arial", "", font_size)
            idx += 1
            project_heading_count += 1
            continue

        if is_heading(stripped):
            y = pdf.get_y() + 1
            if heading_count > 0 and stripped.lower() != "projects":
                pdf.line(left_margin, y, pdf.w - right_margin, y)
            pdf.set_y(y + (2 if heading_count > 0 else 1))
            pdf.set_font("Arial", "B", heading_size)
            pdf.cell(usable_width, line_height, stripped, ln=1, align="L")
            if stripped.lower() == "projects":
                pdf.ln(blank_line_height)
            heading_count += 1
            expect_company_meta = False
            current_section = stripped
            in_skills_section = stripped.lower() in {"core skills", "skills"}
            idx += 1
            continue

        if not stripped:
            next_heading = ""
            for j in range(idx + 1, len(safe_lines)):
                candidate = safe_lines[j].strip()
                if candidate:
                    next_heading = candidate
                    break
            if (
                selected_format == "Experience-Focused (No LinkedIn/Projects)"
                and next_heading
                and is_heading(next_heading)
            ):
                idx += 1
                continue
            pdf.ln(blank_line_height)
            expect_company_meta = False
            in_skills_section = False
            idx += 1
            continue

        if expect_company_meta:
            pdf.set_font("Arial", "I", max(font_size - 0.5, 8))
            pdf.cell(usable_width, line_height, stripped, ln=1, align="L")
            expect_company_meta = False
            idx += 1
            continue

        is_education_line = any(keyword in stripped for keyword in education_keywords)

        if in_skills_section and stripped:
            pdf.set_font("Arial", "", font_size)
            skill_entry = stripped if is_bullet_line(stripped) else f"- {stripped}"
            skill_entry = enforce_skill_list_length(skill_entry)
            bullet_line = format_single_line_bullet(skill_entry)
            render_line, bold, _ = detect_bold_line(bullet_line)
            pdf.set_font("Arial", "B" if bold else "", font_size)
            pdf.cell(usable_width, line_height, render_line, ln=1, align="J")
            pdf.set_font("Arial", "", font_size)
            expect_company_meta = False
            idx += 1
            continue

        if is_company_role(stripped) and not is_education_line:
            pdf.set_font("Arial", "B", heading_size - 1)
            pdf.cell(usable_width, line_height, stripped, ln=1, align="L")
            expect_company_meta = True
            idx += 1
            continue

        # Render bullet lines one-per-line without reflow.
        if is_bullet_line(stripped):
            pdf.set_font("Arial", "", font_size)
            bullet_lines = wrap_bullet_line(stripped)
            for bullet in bullet_lines:
                render_line, bold, _ = detect_bold_line(bullet)
                pdf.set_font("Arial", "B" if bold else "", font_size)
                pdf.cell(usable_width, line_height, render_line, ln=1, align="J")
            pdf.set_font("Arial", "", font_size)
            expect_company_meta = False
            idx += 1
            continue

        # Reflow normal body block to the same line count but fuller lines.
        block = []
        block_start = idx
        while idx < len(safe_lines):
            candidate = safe_lines[idx].strip()
            if (
                not candidate
                or is_heading(candidate)
                or (is_company_role(candidate) and not any(k in candidate for k in education_keywords))
                or expect_company_meta
                or is_bullet_line(candidate)
            ):
                break
            block.append(candidate)
            idx += 1

        if not block:
            idx += 1
            continue

        is_summary_block = current_section and current_section.lower().strip() == "professional summary"
        if is_summary_block:
            paragraph = " ".join(block).strip()
            lines_to_render = wrap_text_to_width(paragraph)
        else:
            lines_to_render = reflow_block(block)

        for ln in lines_to_render:
            render_line, bold, is_project_title = detect_bold_line(ln)
            if is_project_title:
                if project_heading_count > 0:
                    pdf.ln(blank_line_height)
                pdf.set_font("Arial", "B", project_heading_size)
                pdf.cell(usable_width, line_height, render_line, ln=1, align="L")
                project_heading_count += 1
            else:
                pdf.set_font("Arial", "B" if bold else "", font_size)
                pdf.cell(usable_width, line_height, render_line, ln=1, align="J")
            pdf.set_font("Arial", "", font_size)
        pdf.set_font("Arial", "", font_size)

    pdf.output(filename)
    return filename


def derive_file_role_label(description: str) -> str:
    """Return a file-friendly role label derived from the first line of the job description."""
    if not description:
        return "Role"
    first_line = description.strip().splitlines()[0].strip()
    if not first_line:
        return "Role"
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", first_line)
    return sanitized or "Role"


# -----------------------------
# Streamlit UI
# -----------------------------
st.title("📄 Adaptive Resume Generator (Codex + Streamlit)")
st.write(
    "Automatically tailor your resume to any job description while keeping the same "
    "structure & line count. The template is loaded directly from the project folder."
)

if TEMPLATE_TEXT == "":
    st.error(
        "Template resume not found. Place `Parmeet_Singh_Resume_Template.pdf`, "
        "`Resume_Parmeet_Singh.pdf`, or `parmeet_singh_resume.pdf` in the main folder to continue."
    )
    st.stop()

# --- Job Description Input ---
FORMAT_STYLES = {
    "LinkedIn + Projects": {
        "description": "Includes LinkedIn link, project links, and keeps Independent Projects section.",
        "instructions": (
            "Preserve the LinkedIn link and any project links from the contact block. "
            "Keep the Independent Projects section intact, highlighting standout work. "
            "Balance space between company experience and independent projects."
        ),
    },
    "Experience-Focused (No LinkedIn/Projects)": {
        "description": (
            "Removes LinkedIn link and Independent Projects section, using the extra space to deepen company experience."
        ),
        "instructions": (
            "Remove the LinkedIn link from the contact block and omit the Independent Projects section entirely. "
            "Reuse the reclaimed lines to expand company experience bullet points with richer impact and metrics. "
            "Preserve the original line count and section ordering; replace removed lines with richer experience content so formatting stays identical to the template."
            "Make the Professional Summary a single experience-focused paragraph composed of exactly eight sentences that align with the job description and keep the document length equal to the template, while omitting any LinkedIn or project references. "
            "Weave in language that underscores ethics, responsibility, impact, and a problem-solving mindset so the paragraph reads as someone who believes in responsible change."
            "Ensure every experience bullet stays concise, precise, and within the page margins, leveraging strong numbers from the job description so they can be rendered on a single line without wrapping."
            "If a bullet would overflow the width, rewrite it to be shorter—capture the impact in one sentence that fits on a single line without wrapping."
            "Treat the Core Skills section the same way: list the most important skills first and omit any tokens that would force a second line so the entire row stays single line within the margins."
            "Keep the LTI - Larsen & Toubro Infotech Ltd. - Software Engineer section to exactly four bullets and the Kiran Engineering Works - AI & Software Engineer section to seven to nine bullets; choose more bullets only when the final education line still fits on the last page, and drop to seven if adding extras would push that education entry off the page."
            "Insert a Projects subsection immediately after the Experience section (after LTI) with three role-aligned initiatives, each titled in bold and supported by two concise impact bullets."
            "Clarify that the eight sentences should naturally occupy eight lines in the Experience-Focused PDF; rewrite sentences if needed to avoid wrapping and maintain the single-line bullet rule."
            "Avoid inserting literal labels such as 'Description:', 'Summary:', or 'Role:' inside the Professional Summary; the paragraph should flow as natural sentences without prefatory keywords."
            "Write each sentence with a human tone—vary cadence, use conversational transitions, and skip formulaic or overly technical boilerplate so the summary reads like a thoughtful narrative rather than generated copy."
        ),
    },
}


EXPERIENCE_GUIDELINES = """
- Every experience bullet must quantify its impact with concrete metrics (percentages, time saved, revenue lifted, downtime reduced, adoption increased, etc.). If the exact number is not stated, infer a realistic yet defensible metric from the job description and responsibilities.
- Keep each employer aligned with its domain: the first company is a software/AI organization - highlight platform engineering, AI delivery, cloud scale, SLOs, or product impact. The second company is Kiran Engineering Works - showcase automation, embedded systems, mechanical-electrical integration, manufacturing throughput, or robotics improvements.
- Metrics must sound credible (e.g., "reduced deployment time 35%", "improved uptime to 99.3%", "cut calibration effort by 28%", "boosted analytics adoption 2.1x"). Avoid generic statements without measurable change.
- When describing impact, do not default to percentages. Pick a meaningful, real-world metric (hours saved, tickets resolved, downtime avoided, etc.) that fits the work, and only use percentages when they feel natural.
- Each impact statement must explain why the change mattered to the business; infer conservative but realistic numbers when exact data is missing and keep everything defensible in interviews.
- Skip using cost figures; rely on hours, percentages, throughput, or other operational metrics tied to time or scale instead of INR or USD savings.
- For the Experience-Focused layout, keep each bullet and the Core Skills row to one line; list the most pertinent skills first and drop any extra keywords that would push the row to a second line.
- For the Experience-Focused layout, keep each bullet short enough to stay on one line; rewrite any sentence that would otherwise wrap so it is precise, impact-driven, and remains within the margins.
- For the Experience-Focused layout, keep LTI - Larsen & Toubro Infotech Ltd. - Software Engineer to exactly four precise bullets and Kiran Engineering Works - AI & Software Engineer to seven to nine bullets, choosing fewer when the page is near full so the education entry stays visible.
- For the Experience-Focused format in particular, keep every bullet short enough to stay on a single line, rewriting them to be precise, impact-first sentences so they never exceed the template's column width.
- Always write each bullet as a standalone sentence that naturally fits within the right-hand margin, so no post-processing trimming is necessary to keep it one line.
- Rewrite any bullet that risks wrapping so it already fits the margin; rely on rephrasing at the generation stage instead of post-processing cuts.
- For the Experience-Focused layout, present exactly five Core Skills entries so the section maintains a consistent five-bullet appearance; choose the top skills that can stay on one line each.
- Each Core Skills bullet should follow "Category: Skill1, Skill2, Skill3, Skill4" with exactly four keywords to keep the formatting uniform.
- If any keyword is multi-word, list only three skills after the category to prevent wrapping.
""".strip()

SESSION_DEFAULTS = {
    "job_desc_input": "",
    "job_analysis": None,
    "job_desc_for_analysis": "",
    "resume_consent": False,
    "resume_generated": False,
    "cover_letter": "",
    "cover_letter_generated": False,
    "cover_letter_pdf_filename": "",
    "cover_letter_pdf_bytes": None,
    "updated_resume": "",
    "pdf_filename": "",
    "pdf_bytes": None,
    "selected_format": "Experience-Focused (No LinkedIn/Projects)",
    "resume_comment": "",
}
for key, value in SESSION_DEFAULTS.items():
    st.session_state.setdefault(key, value)

job_desc = st.text_area(
    "Paste the Job Description Here",
    height=300,
    value=st.session_state.get("job_desc_input", ""),
)
st.session_state["job_desc_input"] = job_desc

format_option = st.radio(
    "Choose Resume Formatting Style",
    options=list(FORMAT_STYLES.keys()),
    index=list(FORMAT_STYLES.keys()).index(
        st.session_state.get("selected_format", list(FORMAT_STYLES.keys())[0])
    ),
)
if format_option != st.session_state.get("selected_format"):
    st.session_state["selected_format"] = format_option
    st.session_state["resume_generated"] = False
    st.session_state["updated_resume"] = ""
    st.session_state["pdf_filename"] = ""
    st.session_state["pdf_bytes"] = None

st.caption(FORMAT_STYLES[format_option]["description"])

if format_option == "Experience-Focused (No LinkedIn/Projects)":
    resume_comment = st.text_area(
        "Optional note to weave into the Experience-Focused resume",
        value=st.session_state.get("resume_comment", ""),
        help="If you provide a short comment, the generator will integrate it somewhere in the resume content (summary, experience bullet, or skills) instead of creating a separate section.",
        height=80,
    )
    st.session_state["resume_comment"] = resume_comment
else:
    st.session_state.setdefault("resume_comment", "")


def analyze_job_description(description):
    """Use OpenAI to extract remote status, salary, and experience with citations."""
    SYSTEM_ANALYSIS_PROMPT = """
You are a Job Eligibility & Info Extraction Engine.

Your task is to analyze the job description and return structured information
that will be displayed on the frontend BEFORE generating the resume.

----------------------------------------------
WHAT YOU MUST DETECT AND RETURN
----------------------------------------------

1. **Remote Eligibility (GLOBAL vs LIMITED REMOTE)**
   - Determine whether this job can be done from India (or anywhere in the world).
   - Use ONLY information from the job description.
   - Your evaluation must fall into EXACTLY one of the following categories:

   A. **GLOBAL REMOTE — Green**
      - Job explicitly says: “remote worldwide”, “remote globally”,
        “work from anywhere”, “global team”, etc.
      - OR clearly implies no geographic restriction.
      → Output:
        STATUS = GREEN
        MESSAGE = "This job is remote-friendly worldwide and can be done from India."
        CITE = Provide the exact lines from the job description that support your conclusion.

   B. **NOT GLOBAL / REGION-BOUND — Red**
      - Job says remote but restricted to:
        “Europe only”, “US only”, “APAC only”, “Australia only”, “Canada only”, etc.
      - OR requires physical presence in a region/timezone not compatible with India.
      → Output:
        STATUS = RED
        MESSAGE = "This job is not remote worldwide and cannot be done from India."
        CITE = Provide the exact restricting lines.

   C. **UNCERTAIN / NOT CLEAR — Yellow**
      - No explicit statement about remote eligibility.
      - Remote status implied but not confirmed.
      → Output:
        STATUS = YELLOW
        MESSAGE = "It is unclear whether this job can be done from India."
        CITE = Provide ambiguous or missing lines.

----------------------------------------------
2. **Salary Detection**
----------------------------------------------
- Extract salary range EXACTLY as written.
- If equity, stock options, RSUs are mentioned — extract those too.
- If nothing mentioned → "Nothing is stated."
- Always include citation lines.

Format:
SALARY = "<extracted salary>" OR "Nothing is stated."
CITE = "<relevant lines>"

----------------------------------------------
3. **Experience Requirement Detection**
----------------------------------------------
- Extract required years of experience, if any.
- If multiple ranges exist, extract the primary requirement.
- If nothing is mentioned → "Nothing is stated."
- Include citation lines.

Format:
EXPERIENCE = "<extracted years>" OR "Nothing is stated."
CITE = "<relevant lines>"

----------------------------------------------
4. FINAL STRUCTURED OUTPUT FORMAT
----------------------------------------------
Return your results in the following EXACT JSON structure:

{
  "remote_status": "<GREEN | RED | YELLOW>",
  "remote_message": "<message>",
  "remote_citation": "<citation>",

  "salary": "<extracted or Nothing is stated>",
  "salary_citation": "<citation>",

  "experience": "<extracted or Nothing is stated>",
  "experience_citation": "<citation>",

  "question": "Would you like me to continue and generate the tailored resume for you? (yes/no)"
}

----------------------------------------------
BEFORE ANY RESUME GENERATION:
You must ALWAYS produce this JSON and WAIT for the user's confirmation.
Do NOT generate the resume unless the user explicitly replies “yes”.
----------------------------------------------

Begin analysis when the job description is provided.
""".strip()

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_ANALYSIS_PROMPT},
            {"role": "user", "content": description},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to parse analysis response.") from exc


def generate_resume_text(description, template_text, style_instructions):
    """Call OpenAI to tailor the resume text."""
    SYSTEM_PROMPT = """
You are an AI Resume Generator that transforms an existing resume into a job-specific resume
while preserving its structure, layout, and total number of lines.

Here are the rules:
1. The final resume MUST have the exact same number of lines as the template.
2. You must NOT add, remove, or reorder any sections.
3. Company names, job titles, dates, and education entries must stay EXACTLY the same.
4. You MAY rewrite the summary, skills, and work experience bullet points (same number of bullets).
5. Every rewritten bullet point must remain ONE line only.
6. Match the tone, keywords, and responsibilities of the job description.
7. Do NOT append LinkedIn links or any other contact links; preserve the template's contact block exactly.
8. After producing the text resume, DO NOT add commentary—return only the final formatted resume.
""".strip()

    combined_instructions = (
        EXPERIENCE_GUIDELINES + "\n\nFormatting Focus:\n" + style_instructions
    )

    USER_PROMPT = f"""
[JOB DESCRIPTION]
{description}

[RESUME TEMPLATE]
{template_text}

[STYLE INSTRUCTIONS]
{combined_instructions}

Return only the updated resume with EXACTLY the same number of lines as the template.
""".strip()

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content


def generate_cover_letter_text(description: str) -> str:
    """Create a cover letter referencing the job description in a standard format."""
    if not description:
        raise ValueError("Job description is required to build a cover letter.")

    today_str = date.today().strftime("%B %d, %Y")
    SYSTEM_COVER_PROMPT = """
You are a professional cover letter writer. Use the incoming job description to craft a thoughtful,
human-toned cover letter with a standard business structure (date, salutation, intro, body, closing, signature).
Highlight the most relevant skills, responsibilities, and impact the candidate can bring to the role,
and tie them back to the job description language. Include today's date at the top and sign the letter as
Parmeet Singh. Avoid adding placeholder blocks like "[Company Address]" or "[Your Email Address]". If the company
name is discoverable from the description, reference it in the greeting or opening sentence. Keep the tone confident,
respectful, and aligned with the target job, avoiding robotic phrasing. Return only the cover letter text without explanations.
""".strip()

    USER_COVER_PROMPT = f"""
Date: {today_str}

[JOB DESCRIPTION]
{description}

[INSTRUCTIONS]
- Stay within one-page letter convention and write 3 paragraphs (intro, body, closing) plus signature.
- Mention one measurable achievement or impact idea inspired by the job description.
- Keep the closing line forward-looking and express enthusiasm about contributing.
- Sign off with "Sincerely, Parmeet Singh" and explicitly include contact info as "Email: parmeet.singh@parmeetsingh.com" and "Phone: +91 74200 04161".
- Skip any bracketed placeholders such as "[Company Address]" or "[City, State, Zip]"—address real companies and locations when possible.
""".strip()

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_COVER_PROMPT},
            {"role": "user", "content": USER_COVER_PROMPT},
        ],
        temperature=0.4,
    )
    cover_letter = response.choices[0].message.content.strip()
    if not cover_letter:
        raise ValueError("Cover letter generation returned empty text.")
    lines = [
        ln
        for ln in cover_letter.splitlines()
        if not re.search(r"\[(Company Address|City, State, Zip)\]", ln, re.IGNORECASE)
    ]
    cleaned = "\n".join(lines)
    cleaned = cleaned.replace("[Your Email Address]", "Email: parmeet.singh@parmeetsingh.com")
    cleaned = cleaned.replace("[Your Phone Number]", "Phone: +91 74200 04161")
    return cleaned


def enforce_projects_block(text):
    """Ensure a canonical Independent Projects block for the LinkedIn + Projects format."""
    canonical = [
        "Independent Projects / Portfolio - Live at parmeetsingh.com",
        "- Featured Projects: YouTube RAG · NetZero Advisor · Research Agent · Legal Document Analyzer",
        "- YouTube RAG: Turns YouTube videos into a searchable knowledge base with transcript-grounded Q&A.",
        "- NetZero Advisor: AI advisor for carbon credits and sustainability insights using retrieval and reasoning.",
        "- Research Agent: Automates multi-source research by collecting and summarizing relevant information.",
        "- Legal Document Analyzer: Answers questions from long legal documents using structured retrieval.",
    ]

    lines = text.split("\n")
    start = None
    end = None
    for idx, ln in enumerate(lines):
        if "independent projects" in ln.lower():
            start = idx
            break
    if start is not None:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            nxt = lines[j].strip()
            if not nxt:
                end = j
                break
            if nxt.isupper() or nxt.lower() in {"experience", "skills", "education", "core skills"}:
                end = j
                break
        lines = lines[:start] + canonical + lines[end:]
    else:
        lines.extend([""] + canonical)
        return "\n".join(lines)


def build_comment_clause(comment: str, role_keyword: str) -> str:
    """Return a role-aligned clause derived from the user comment."""
    if not comment:
        return ""
    normalized = " ".join(comment.strip().split())
    if not normalized:
        return ""
    normalized = re.sub(
        r"^(I am|I'm|I'm|I'M|I AM|I AM)(\s+)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"^My\s+", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.rstrip(".!?").strip()
    if not normalized:
        return ""
    if not role_keyword:
        role_keyword = "Professional"
    clause = f"This {role_keyword} is committed to {normalized}."
    return clause


def clean_summary_labels(text: str) -> str:
    """Strip label prefixes such as 'Description:' or 'Role:' at the start of summary lines."""
    pattern = re.compile(
        r"^\s*(?:description|summary|professional summary|overview|role|position|job title)\s*:\s*",
        re.IGNORECASE,
    )
    lines = text.split("\n")
    summary_idx = next(
        (idx for idx, ln in enumerate(lines) if ln.strip().lower() == "professional summary"),
        None,
    )
    if summary_idx is None:
        return text

    found_text = False
    for idx in range(summary_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            if found_text:
                break
            continue
        found_text = True
        cleaned = re.sub(pattern, "", stripped)
        lines[idx] = cleaned
    return "\n".join(lines)


def rewrite_kiran_role_line(text: str, role_keyword: str) -> str:
    """Ensure the Kiran Engineering Works heading refers to the target job role only."""
    if not role_keyword:
        return text
    pattern = re.compile(r"(Kiran Engineering Works\s*[–—-]\s*)(.+)", re.IGNORECASE)
    def repl(match):
        return f"{match.group(1)}{role_keyword}"
    return pattern.sub(repl, text, count=1)


def build_projects_block(role_keyword: str) -> list[str]:
    """Generate the Projects subsection text that follows LTI in Experience-Focused resumes."""
    project_titles = [
        f"{role_keyword} Insight Sprint",
        f"{role_keyword} Reliability Loop",
        f"{role_keyword} Automation Studio",
    ]
    bullets = [
        [
            "Delivered a multi-source insight sprint that aligned operations telemetry, tackling inconsistent signals by standardizing collection flows.",
            "Solved the decision lag for leadership, learning to negotiate instrumentation trade-offs while keeping trust high.",
        ],
        [
            "Engineered a reliability loop that simulated failure modes to automate escalation and reduce manual downtimes.",
            "Documented observability handoffs and captured lessons about balancing safety, cost, and speed.",
        ],
        [
            "Built an automation studio that chained deployment scripts into reusable workflows, cutting setup time and human error.",
            "Mapped success criteria for each workflow and trained partners so the automation could scale without new hires.",
        ],
    ]
    block = ["", "Projects", ""]
    for title, bullet_set in zip(project_titles, bullets):
        block.append(f"{PROJECT_TITLE_PREFIX}{title}")
        for item in bullet_set:
            block.append(f"- {item}")
        block.append("")
    return block


def inject_comment_into_summary(text: str, comment: str, role_keyword: str) -> str:
    """Append a user comment clause to the last Professional Summary sentence when strategic."""
    clause = build_comment_clause(comment, role_keyword)
    if not clause:
        return text
    lower_text = text.lower()
    if clause.lower() in lower_text:
        return text

    lines = text.split("\n")
    summary_idx = next(
        (idx for idx, ln in enumerate(lines) if ln.strip().lower() == "professional summary"),
        None,
    )
    if summary_idx is None:
        return text

    last_summary_line = None
    for idx in range(summary_idx + 1, len(lines)):
        if not lines[idx].strip():
            break
        last_summary_line = idx

    if last_summary_line is None:
        return text

    lines[last_summary_line] = lines[last_summary_line].rstrip() + " " + clause
    return "\n".join(lines)


def insert_projects_section(text: str, role_keyword: str) -> str:
    """Insert the Projects block after the Experience section and before Education."""
    lines = text.split("\n")
    if any(ln.strip().lower() == "projects" for ln in lines):
        return text
    insert_idx = next(
        (idx for idx, ln in enumerate(lines) if ln.strip() == "Education"), None
    )
    block = build_projects_block(role_keyword)
    if insert_idx is None:
        return "\n".join(lines + block)
    return "\n".join(lines[:insert_idx] + block + lines[insert_idx:])


# --- Workflow Controls ---
col_check, col_generate = st.columns([3, 3])
with col_check:
    if st.button("Check Job Details (Remote, Salary, Experience)"):
        if not job_desc.strip():
            st.error("Job description cannot be empty.")
        else:
            with st.spinner("Analyzing job description…"):
                try:
                    analysis_result = analyze_job_description(job_desc.strip())
                except Exception as exc:  # pylint: disable=broad-except
                    st.error(f"Analysis failed: {exc}")
                else:
                    st.session_state["job_analysis"] = analysis_result
                    st.session_state["job_desc_for_analysis"] = job_desc.strip()
                    st.session_state["resume_consent"] = False
                    st.session_state["resume_generated"] = False
                    st.session_state["updated_resume"] = ""
                    st.session_state["pdf_filename"] = ""
                    st.session_state["pdf_bytes"] = None
                    st.success("Job analysis completed. Review the findings below.")

with col_generate:
    if st.button("Generate Tailored Resume"):
        clean_jd = job_desc.strip()
        if not clean_jd:
            st.error("Job description cannot be empty.")
        else:
            analysis = st.session_state.get("job_analysis")
            stored_desc = st.session_state.get("job_desc_for_analysis", "")
            has_valid_analysis = analysis and clean_jd == stored_desc

            if has_valid_analysis and not st.session_state.get("resume_consent"):
                st.warning(
                    "Please confirm below that you would like to continue before generating the resume."
                )
            else:
                if not has_valid_analysis:
                    if analysis:
                        st.warning(
                            "Job description has changed since the last analysis. "
                            "Generating resume directly without re-checking the job details."
                        )
                    else:
                        st.info(
                            "Generating resume directly without running the job details check."
                        )
                    st.session_state["resume_consent"] = True
                    st.session_state["job_analysis"] = None

                job_desc_for_generation = (
                    clean_jd
                    if not has_valid_analysis
                    else st.session_state.get("job_desc_for_analysis", "")
                )

                updated_resume = None
                pdf_file = ""
                pdf_bytes = None
                selected_format = st.session_state.get("selected_format")
                style_instructions = FORMAT_STYLES[selected_format]["instructions"]
                comment_value = st.session_state.get("resume_comment", "").strip()
                role_keyword = "Software Engineer"
                role_instruction = ""
                if selected_format == "Experience-Focused (No LinkedIn/Projects)":
                    kiran_role = extract_kiran_role_from_description(job_desc_for_generation)
                    if kiran_role:
                        role_keyword = sanitize_job_role_candidate(kiran_role)
                    else:
                        raw_role_line = job_desc_for_generation.split("\n")[0].strip()
                        role_keyword = sanitize_job_role_candidate(raw_role_line)
                    role_instruction = (
                        "\nEnsure the Professional Summary begins with "
                        f"'{role_keyword}' and stays focused on that functional role without defaulting to AI/ML unless the job description explicitly calls for it."
                        f" When referring to Kiran Engineering Works, label it as 'Kiran Engineering Works – {role_keyword}' and avoid any seniority prefixes."
                    )
                if comment_value and selected_format == "Experience-Focused (No LinkedIn/Projects)":
                    style_instructions += (
                        "\nInclude the following user emphasis somewhere naturally in the resume (summary, a bullet, or skills) without creating a standalone comment section: "
                        f"\"{comment_value}\""
                    )
                style_instructions += role_instruction

                with st.spinner("Generating resume…"):
                    updated_resume = generate_resume_text(
                        job_desc_for_generation,
                        TEMPLATE_TEXT,
                        style_instructions,
                    )

                    if selected_format == "Experience-Focused (No LinkedIn/Projects)":
                        updated_resume = updated_resume.replace(
                            "parmeetsingh.com", ""
                        ).replace("LinkedIn", "").strip()
                        updated_resume = inject_comment_into_summary(
                            updated_resume, comment_value, role_keyword
                        )
                        updated_resume = clean_summary_labels(updated_resume)
                        updated_resume = rewrite_kiran_role_line(
                            updated_resume, role_keyword
                        )
                        updated_resume = insert_projects_section(
                            updated_resume, role_keyword
                        )

                    if st.session_state.get("selected_format") == "LinkedIn + Projects":
                        updated_resume = enforce_projects_block(updated_resume)

                    if "granthi.parmeet@gmail.com" in updated_resume:
                        updated_resume = updated_resume.replace(
                            "granthi.parmeet@gmail.com", PRIMARY_EMAIL
                        )

                job_role = derive_file_role_label(job_desc_for_generation)

                pdf_file = generate_pdf(
                    updated_resume,
                    job_role,
                    st.session_state.get("selected_format"),
                    doc_label="resume",
                )
                with open(pdf_file, "rb") as pdf_handle:
                    pdf_bytes = pdf_handle.read()

                st.session_state["updated_resume"] = updated_resume
                st.session_state["pdf_filename"] = pdf_file
                st.session_state["pdf_bytes"] = pdf_bytes
                st.session_state["resume_generated"] = True
                st.success("Resume generated successfully!")

cover_col, _ = st.columns([3, 3])
with cover_col:
    if st.button("Generate Cover Letter", key="generate_cover_letter"):
        clean_jd = job_desc.strip()
        if not clean_jd:
            st.error("Job description cannot be empty.")
        else:
            with st.spinner("Generating cover letter…"):
                try:
                    cover_letter = generate_cover_letter_text(clean_jd)
                    job_role_label = derive_file_role_label(clean_jd)
                    cover_pdf_file = generate_pdf(
                        cover_letter,
                        job_role_label,
                        st.session_state.get("selected_format"),
                        doc_label="cover_letter",
                        fit_page=False,
                    )
                    with open(cover_pdf_file, "rb") as pdf_handle:
                        cover_pdf_bytes = pdf_handle.read()
                except Exception as exc:  # pylint: disable=broad-except
                    st.error(f"Cover letter generation failed: {exc}")
                else:
                    st.session_state["cover_letter"] = cover_letter
                    st.session_state["cover_letter_generated"] = True
                    st.session_state["cover_letter_pdf_filename"] = cover_pdf_file
                    st.session_state["cover_letter_pdf_bytes"] = cover_pdf_bytes
                    st.success("Cover letter generated.")


# --- Display Analysis & Decision ---
analysis = st.session_state.get("job_analysis")
if analysis:
    status = analysis.get("remote_status", "").upper()
    status_message = analysis.get("remote_message", "")
    citation = analysis.get("remote_citation", "")

    if status == "GREEN":
        st.success(status_message)
    elif status == "RED":
        st.error(status_message)
    else:
        st.warning(status_message)
    if citation:
        st.caption(f"Citation: {citation}")

    st.subheader("Salary Information")
    st.write(analysis.get("salary", "Nothing is stated."))
    if analysis.get("salary_citation"):
        st.caption(f"Citation: {analysis['salary_citation']}")

    st.subheader("Experience Requirement")
    st.write(analysis.get("experience", "Nothing is stated."))
    if analysis.get("experience_citation"):
        st.caption(f"Citation: {analysis['experience_citation']}")

    st.info(analysis.get("question", "Would you like me to continue?"))

    if job_desc.strip() != st.session_state.get("job_desc_for_analysis", ""):
        st.warning(
            "Job description has changed since the last analysis. Please re-run the analysis "
            "before generating a resume."
        )
        st.session_state["resume_consent"] = False
    else:
        if st.button("Yes, generate resume", key="confirm_yes"):
            st.session_state["resume_consent"] = True
            st.session_state["resume_generated"] = False
            st.info("Great! Click 'Generate Tailored Resume' to continue.")


# --- Output Resume & Downloads ---
if st.session_state.get("resume_generated"):
    st.download_button(
        label="⬇️ Download Tailored Resume (PDF)",
        data=st.session_state.get("pdf_bytes"),
        file_name=st.session_state.get("pdf_filename"),
        mime="application/pdf",
    )

    st.text_area(
        "Generated Resume (Text Format)",
        st.session_state.get("updated_resume", ""),
        height=400,
    )

if st.session_state.get("cover_letter_generated") and st.session_state.get(
    "cover_letter_pdf_bytes"
):
    st.download_button(
        label="⬇️ Download Cover Letter (PDF)",
        data=st.session_state.get("cover_letter_pdf_bytes"),
        file_name=st.session_state.get("cover_letter_pdf_filename"),
        mime="application/pdf",
    )

st.subheader("Generated Cover Letter (Text Format)")
st.text_area(
    "Cover Letter",
    st.session_state.get("cover_letter", ""),
    height=400,
    help="Use the same job description input above to regenerate if the content isn't aligned.",
)
