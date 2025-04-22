import os
import fitz # type: ignore



ABM_FOLDER = "abm_reports"


def extract_text_from_pdf(uploaded_pdf):
    try:
          # PyMuPDF
        doc = fitz.open(stream=uploaded_pdf.read(), filetype="pdf")
        return "\n".join([page.get_text() for page in doc])
    except Exception as e:
        print(f"Error reading ABM PDF: {e}")
        return ""


def get_abm_report_text():
    all_text = []
    if not os.path.exists(ABM_FOLDER):
        print(f"Directory '{ABM_FOLDER}' not found. Returning empty context.")
        return ""

    for fname in os.listdir(ABM_FOLDER):
        if fname.endswith(".pdf"):
            fpath = os.path.join(ABM_FOLDER, fname)
            with open(fpath, "rb") as f:
                extracted = extract_text_from_pdf(fpath)
                all_text.append(extracted)

            
            
    
    return "\n\n".join(all_text)
