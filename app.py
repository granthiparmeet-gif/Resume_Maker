import json
import os
import re

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
]
TEMPLATE_PATH = next(
    (path for path in PREFERRED_TEMPLATE_NAMES if os.path.exists(path)),
    PREFERRED_TEMPLATE_NAMES[0],
)


def extract_text_from_pdf(source):
    """Return all text extracted from a PDF path or file-like object."""
    import PyPDF2

    close_after = False
    if isinstance(source, (str, os.PathLike)):
        source = open(source, "rb")
        close_after = True
    else:
        source.seek(0)

    try:
        reader = PyPDF2.PdfReader(source)
        return "\n".join(
            (page.extract_text() or "").rstrip() for page in reader.pages
        ).rstrip()
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

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_font("Arial", size=10)

    for line in text.split("\n"):
        pdf.multi_cell(0, 5, line)

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
        "Template resume not found. Place `Parmeet_Singh_Resume_Template.pdf` (or "
        "`Resume_Parmeet_Singh.pdf`) in the main folder to continue."
    )
    st.stop()

# --- Job Description Input ---
job_desc = st.text_area("Paste the Job Description Here", height=300)

SESSION_DEFAULTS = {
    "job_analysis": None,
    "job_desc_for_analysis": "",
    "resume_consent": False,
    "resume_generated": False,
    "updated_resume": "",
    "pdf_filename": "",
    "pdf_bytes": None,
}
for key, value in SESSION_DEFAULTS.items():
    st.session_state.setdefault(key, value)


def reset_workflow():
    for key in SESSION_DEFAULTS:
        st.session_state[key] = SESSION_DEFAULTS[key]
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
    content = response.choices[0].message["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Unable to parse analysis response.") from exc


def generate_resume_text(description, template_text):
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

    USER_PROMPT = f"""
[JOB DESCRIPTION]
{description}

[RESUME TEMPLATE]
{template_text}

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

    return response.choices[0].message["content"]


# --- Workflow Controls ---
col_analyze, col_reset = st.columns([3, 1])
with col_analyze:
    if st.button("Analyze Job Eligibility"):
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
        with no_col:
            if st.button("No, start over", key="confirm_no"):
                reset_workflow()


# --- Resume Generation After Consent ---
if (
    st.session_state.get("resume_consent")
    and not st.session_state.get("resume_generated")
    and st.session_state.get("job_analysis")
):
    with st.spinner("Generating resume…"):
        job_desc_for_generation = st.session_state.get("job_desc_for_analysis", "")
        updated_resume = generate_resume_text(job_desc_for_generation, TEMPLATE_TEXT)

        first_line = job_desc_for_generation.split("\n")[0].strip()
        job_role = re.sub(r"[^A-Za-z0-9]+", "_", first_line) or "Role"

        pdf_file = generate_pdf(updated_resume, job_role)
        with open(pdf_file, "rb") as pdf_handle:
            pdf_bytes = pdf_handle.read()

    st.session_state["updated_resume"] = updated_resume
    st.session_state["pdf_filename"] = pdf_file
    st.session_state["pdf_bytes"] = pdf_bytes
    st.session_state["resume_generated"] = True


# --- Output Resume & Downloads ---
if st.session_state.get("resume_generated"):
    st.success("Resume generated successfully!")
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
