import json
import os
import re
import textwrap

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

# -----------------------------
# Load Resume Template From File
# -----------------------------
PREFERRED_TEMPLATE_NAMES = [
    "Parmeet_Singh_Resume_Template.pdf",
    "Resume_Parmeet_Singh.pdf",
    "parmeet_singh_resume.pdf",
]
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
        return textwrap.fill(combined, width=90, break_long_words=False)
    finally:
        if close_after:
            source.close()


if os.path.exists(TEMPLATE_PATH):
    TEMPLATE_TEXT = extract_text_from_pdf(TEMPLATE_PATH)
else:
    TEMPLATE_TEXT = ""


# -----------------------------
# PDF Generator
# -----------------------------
def generate_pdf(text, job_role):
    filename = f"Parmeet_Singh_{job_role}.pdf"
    lines = text.split("\n")
    total_lines = max(len(lines), 1)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    left_margin = 15
    right_margin = 15
    top_margin = 15
    bottom_margin = 15
    pdf.set_margins(left_margin, top_margin, right_margin)

    available_height = pdf.h - top_margin - bottom_margin
    usable_width = pdf.w - left_margin - right_margin

    base_font_size = 11
    def normalize_line(text_line: str) -> str:
        cleaned = re.sub(r"\s\?\s", " - ", text_line)
        cleaned = re.sub(r"\s\?(\W|$)", r" -\1", cleaned)
        cleaned = re.sub(r"(\W|^)\?\s", r"\1- ", cleaned)
        return (cleaned.encode("latin-1", "replace").decode("latin-1")) or " "

    safe_lines = [normalize_line(line) for line in lines]

    # Determine body font size to fit longest line within width.
    font_size = base_font_size
    pdf.set_font("Arial", size=font_size)
    max_line_width = max(pdf.get_string_width(line) for line in safe_lines if line.strip()) or 0
    if max_line_width > usable_width:
        scale = usable_width / max_line_width
        font_size = max(7, round(base_font_size * scale, 1))
        pdf.set_font("Arial", size=font_size)

    # Line height scaled to fill the page without overflow.
    line_height = available_height / total_lines
    min_line_height = font_size * 1.15
    if line_height < min_line_height:
        line_height = min_line_height
    if line_height * total_lines > available_height:
        line_height = available_height / total_lines

    name_size = max(font_size + 6, 16)
    heading_size = max(font_size + 2, font_size * 1.2)

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

    pdf.set_xy(left_margin, top_margin)
    heading_count = 0

    for idx, line in enumerate(safe_lines):
        stripped = line.strip()

        if idx == 0:
            pdf.set_font("Arial", "B", name_size)
            pdf.cell(usable_width, line_height, stripped, ln=1, align="C")
            continue

        if idx == 1 and ("@" in line or "|" in line or "+" in line):
            pdf.set_font("Arial", "", font_size)
            pdf.cell(usable_width, line_height, stripped, ln=1, align="C")
            # Horizontal rule after contact
            y = pdf.get_y() + 1
            pdf.line(left_margin, y, pdf.w - right_margin, y)
            pdf.set_y(y + 2)
            continue

        if is_heading(stripped):
            if heading_count >= 0:
                y = pdf.get_y() + 1
                pdf.line(left_margin, y, pdf.w - right_margin, y)
                pdf.set_y(y + 2)
            pdf.set_font("Arial", "B", heading_size)
            pdf.cell(usable_width, line_height, stripped, ln=1, align="L")
            heading_count += 1
            continue

        # Body text
        pdf.set_font("Arial", "", font_size)
        if not stripped:
            pdf.ln(line_height)
        else:
            pdf.cell(usable_width, line_height, stripped, ln=1, align="J")

    pdf.output(filename)
    return filename


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
        ),
    },
}

EXPERIENCE_GUIDELINES = """
- Every experience bullet must quantify its impact with concrete metrics (percentages, time saved, revenue lifted, downtime reduced, adoption increased, etc.). If the exact number is not stated, infer a realistic yet defensible metric from the job description and responsibilities.
- Keep each employer aligned with its domain: the first company is a software/AI organization—highlight platform engineering, AI delivery, cloud scale, SLOs, or product impact. The second company is Kiran Engineering Works—showcase automation, embedded systems, mechanical-electrical integration, manufacturing throughput, or robotics improvements.
- Metrics must sound credible (e.g., "reduced deployment time 35%", "improved uptime to 99.3%", "cut calibration effort by 28%", "boosted analytics adoption 2.1x"). Avoid generic statements without measurable change.
""".strip()

SESSION_DEFAULTS = {
    "job_desc_input": "",
    "job_analysis": None,
    "job_desc_for_analysis": "",
    "resume_consent": False,
    "resume_generated": False,
    "updated_resume": "",
    "pdf_filename": "",
    "pdf_bytes": None,
    "selected_format": list(FORMAT_STYLES.keys())[0],
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


def reset_workflow():
    for key, value in SESSION_DEFAULTS.items():
        st.session_state[key] = value
    st.rerun()


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


# --- Workflow Controls ---
col_check, col_generate, col_reset = st.columns([3, 3, 1])
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

                with st.spinner("Generating resume…"):
                    updated_resume = generate_resume_text(
                        job_desc_for_generation,
                        TEMPLATE_TEXT,
                        FORMAT_STYLES[st.session_state.get("selected_format")][
                            "instructions"
                        ],
                    )

                    if st.session_state.get("selected_format") == "Experience-Focused (No LinkedIn/Projects)":
                        updated_resume = updated_resume.replace(
                            "parmeetsingh.com", ""
                        ).replace("LinkedIn", "").strip()

                first_line = job_desc_for_generation.split("\n")[0].strip()
                job_role = re.sub(r"[^A-Za-z0-9]+", "_", first_line) or "Role"

                pdf_file = generate_pdf(updated_resume, job_role)
                with open(pdf_file, "rb") as pdf_handle:
                    pdf_bytes = pdf_handle.read()

                st.session_state["updated_resume"] = updated_resume
                st.session_state["pdf_filename"] = pdf_file
                st.session_state["pdf_bytes"] = pdf_bytes
                st.session_state["resume_generated"] = True
                st.success("Resume generated successfully!")

with col_reset:
    if st.button("Start New Resume"):
        reset_workflow()


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
        yes_col, no_col = st.columns(2)
        with yes_col:
            if st.button("Yes, generate resume", key="confirm_yes"):
                st.session_state["resume_consent"] = True
                st.session_state["resume_generated"] = False
                st.info("Great! Click 'Generate Tailored Resume' to continue.")
        with no_col:
            if st.button("No, start over", key="confirm_no"):
                reset_workflow()


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
