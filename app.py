import os
import re

import openai
import streamlit as st
from fpdf import FPDF

openai.api_key = os.getenv("OPENAI_API_KEY")

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

# --- Button ---
if st.button("Generate Tailored Resume"):
    if not job_desc.strip():
        st.error("Job description cannot be empty.")
        st.stop()

    st.info("Generating resume… Please wait.")

    # Extract job role for naming
    first_line = job_desc.split("\n")[0].strip()
    job_role = re.sub(r"[^A-Za-z0-9]+", "_", first_line) or "Role"

    # -----------------------------
    # Sending prompt to Codex / Your Tool
    # -----------------------------
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
7. After producing the text resume, DO NOT add commentary—return only the final formatted resume.
""".strip()

    USER_PROMPT = f"""
[JOB DESCRIPTION]
{job_desc}

[RESUME TEMPLATE]
{TEMPLATE_TEXT}

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

    updated_resume = response.choices[0].message["content"]

    # -----------------------------
    # Generate PDF
    # -----------------------------
    pdf_file = generate_pdf(updated_resume, job_role)

    with open(pdf_file, "rb") as pdf_handle:
        pdf_bytes = pdf_handle.read()

    st.success("Resume generated successfully!")
    st.download_button(
        label="⬇️ Download Tailored Resume (PDF)",
        data=pdf_bytes,
        file_name=pdf_file,
        mime="application/pdf",
    )

    st.text_area("Generated Resume (Text Format)", updated_resume, height=400)
