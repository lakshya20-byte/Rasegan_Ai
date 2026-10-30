import json
import logging
import os
import re
from collections import defaultdict
from typing import Any, Optional

import pymupdf as fitz  # PyMuPDF
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rasegan")

app = FastAPI(title="RASEGAN AI API", version="0.2.0")


frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Keep credentials on the server. Never send these values to the React client.
NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")
NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL")
MODEL = os.getenv("NEBIUS_MODEL")

if not NEBIUS_API_KEY or not NEBIUS_BASE_URL or not MODEL:
    raise RuntimeError(
        "Missing Nebius configuration. Check NEBIUS_API_KEY, "
        "NEBIUS_BASE_URL and NEBIUS_MODEL in backend/.env."
    )

client = OpenAI(api_key=NEBIUS_API_KEY, base_url=NEBIUS_BASE_URL)

MAX_FILES = 10
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB per PDF
MAX_PAGES_PER_FILE = 60
MAX_TEXT_CHARS_PER_FILE = 30_000
MAX_QUESTIONS_FOR_GROUPING = 150


class EvaluationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=5000)
    answer: str = Field(min_length=1, max_length=10000)
    max_marks: int = Field(default=10, ge=1, le=100)


def _extract_json_object(model_text: str) -> dict[str, Any]:
    """Parse a JSON object even if the model wraps it in a Markdown fence."""
    cleaned = model_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The AI response did not contain a JSON object.")
    return json.loads(cleaned[start : end + 1])


def _year_from_filename(filename: str) -> Optional[int]:
    match = re.search(r"\b(20\d{2})\b", filename or "")
    if not match:
        return None
    year = int(match.group(1))
    return year if 2000 <= year <= 2099 else None


def _extract_pdf_text(pdf_bytes: bytes, filename: str) -> tuple[str, int]:
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise ValueError(f"{filename}: the file does not appear to be a valid PDF.")

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            page_count = document.page_count
            if page_count == 0:
                raise ValueError(f"{filename}: the PDF contains no pages.")
            if page_count > MAX_PAGES_PER_FILE:
                raise ValueError(
                    f"{filename}: {page_count} pages exceeds the limit of "
                    f"{MAX_PAGES_PER_FILE}."
                )

            text_parts = [page.get_text("text") for page in document]
            extracted = "\n".join(part for part in text_parts if part).strip()
    except fitz.FileDataError as exc:
        raise ValueError(f"{filename}: the PDF is damaged or cannot be opened.") from exc

    if len(extracted) < 80:
        raise ValueError(
            f"{filename}: very little selectable text was found. It may be a "
            "scanned/image-only PDF. OCR is not enabled yet; please upload a "
            "text-based PDF."
        )

    return extracted[:MAX_TEXT_CHARS_PER_FILE], page_count


def _ask_model_for_questions(
    paper_text: str, filename: str, subject: str, exam_type: str
) -> list[dict[str, Any]]:
    prompt = f"""
You are extracting questions from a real university examination paper.
Subject: {subject or 'Not specified'}
Exam type: {exam_type or 'Not specified'}
Source filename: {filename}

Rules:
- Extract only questions that actually appear in the supplied paper.
- Preserve each question's wording as closely as possible.
- Include main questions and meaningful sub-questions as separate records when they can be answered independently.
- Do not invent questions, marks, units, or topics.
- If marks are not explicitly visible for a question, use null.
- If a unit is not explicit or confidently identifiable, use null.
- Ignore instructions, page headers, answer keys and general exam rules.

Return ONLY one JSON object in this exact shape:
{{
  "questions": [
    {{
      "question": "verbatim or near-verbatim question text",
      "topic": "short topic name or null",
      "unit": "unit label or null",
      "marks": 5
    }}
  ]
}}

PAPER TEXT:
{paper_text}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "Extract examination questions accurately. Never fabricate content. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=3500,
        temperature=0.1,
    )
    content = response.choices[0].message.content or ""
    parsed = _extract_json_object(content)
    questions = parsed.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError(f"Nemotron returned an invalid question list for {filename}.")

    cleaned_questions: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        question_text = item.get("question")
        if not isinstance(question_text, str) or len(question_text.strip()) < 8:
            continue
        marks = item.get("marks")
        if not isinstance(marks, (int, float)) or marks <= 0:
            marks = None
        cleaned_questions.append(
            {
                "question": question_text.strip()[:2000],
                "topic": item.get("topic") if isinstance(item.get("topic"), str) else None,
                "unit": item.get("unit") if isinstance(item.get("unit"), str) else None,
                "marks": float(marks) if marks is not None else None,
            }
        )
    return cleaned_questions


def _group_similar_questions(
    records: list[dict[str, Any]], subject: str
) -> list[dict[str, Any]]:
    """Ask Nemotron to cluster question record indices, not calculate statistics."""
    if not records:
        return []

    compact_records = [
        {
            "id": index,
            "question": record["question"],
            "topic": record.get("topic"),
        }
        for index, record in enumerate(records[:MAX_QUESTIONS_FOR_GROUPING])
    ]

    prompt = f"""
Group semantically similar university exam questions. Subject: {subject or 'Not specified'}.
Two questions belong together only when they test substantially the same core concept or skill,
even if their wording differs. Do not group questions merely because they share a broad subject.
Use only the supplied integer IDs. Every ID should appear in exactly one group.
Do not calculate frequencies or years. Python will calculate those from source-paper records.

Return ONLY JSON:
{{
  "families": [
    {{"label": "concise concept/question-family label", "ids": [0, 3]}},
    {{"label": "another concept", "ids": [1]}}
  ]
}}

RECORDS:
{json.dumps(compact_records, ensure_ascii=False)}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "Cluster similar questions conservatively. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=3500,
        temperature=0.1,
    )
    content = response.choices[0].message.content or ""
    parsed = _extract_json_object(content)
    families = parsed.get("families", [])
    if not isinstance(families, list):
        raise ValueError("Nemotron returned an invalid question grouping.")

    # Validate model-provided IDs and ensure no question disappears or is counted twice.
    validated: list[dict[str, Any]] = []
    assigned: set[int] = set()
    for family in families:
        if not isinstance(family, dict):
            continue
        ids = family.get("ids", [])
        if not isinstance(ids, list):
            continue
        valid_ids: list[int] = []
        for raw_id in ids:
            if isinstance(raw_id, int) and 0 <= raw_id < min(len(records), MAX_QUESTIONS_FOR_GROUPING):
                if raw_id not in assigned:
                    valid_ids.append(raw_id)
                    assigned.add(raw_id)
        if valid_ids:
            label = family.get("label")
            validated.append(
                {
                    "label": label.strip()[:160] if isinstance(label, str) and label.strip() else records[valid_ids[0]]["question"][:120],
                    "ids": valid_ids,
                }
            )

    # Keep any records omitted by the model as their own singleton families.
    for index in range(min(len(records), MAX_QUESTIONS_FOR_GROUPING)):
        if index not in assigned:
            validated.append({"label": records[index].get("topic") or records[index]["question"][:120], "ids": [index]})

    # Records beyond the model grouping cap are retained as singleton families.
    for index in range(MAX_QUESTIONS_FOR_GROUPING, len(records)):
        validated.append({"label": records[index].get("topic") or records[index]["question"][:120], "ids": [index]})

    return validated


def _build_priority_results(
    records: list[dict[str, Any]],
    families: list[dict[str, Any]],
    total_papers: int,
) -> list[dict[str, Any]]:
    """Score preparation priority while explicitly discounting tiny samples."""
    known_years = [record["year"] for record in records if record.get("year") is not None]
    distinct_years = sorted(set(known_years))
    newest_year = max(distinct_years) if distinct_years else None
    oldest_year = min(distinct_years) if distinct_years else None
    year_span = (newest_year - oldest_year + 1) if newest_year is not None and oldest_year is not None else None

    # Five or more independently analysed papers are needed for an undiscounted score.
    # This prevents one uploaded paper from producing a misleading 90/100 ranking.
    sample_confidence_factor = min(total_papers / 5.0, 1.0)
    if total_papers < 3:
        confidence_label = "Very low"
    elif total_papers < 5:
        confidence_label = "Limited"
    else:
        confidence_label = "Moderate"

    results: list[dict[str, Any]] = []
    for family in families:
        family_records = [records[index] for index in family["ids"]]
        paper_indices = sorted({record["paper_index"] for record in family_records})
        appearance_count = len(paper_indices)
        historical_frequency = appearance_count / max(total_papers, 1)

        family_years = sorted({record["year"] for record in family_records if record.get("year") is not None})
        components: list[tuple[float, float]] = [(historical_frequency * 100.0, 0.70)]

        # Recency is only meaningful when the analysed set contains at least two distinct years.
        if len(distinct_years) >= 2 and newest_year is not None and year_span and family_years:
            age = newest_year - max(family_years)
            recency_score = max(0.0, 100.0 * (1.0 - age / year_span))
            components.append((recency_score, 0.20))

        marks_values = [record["marks"] for record in family_records if record.get("marks") is not None]
        max_observed_marks = max(
            (record["marks"] for record in records if record.get("marks") is not None),
            default=None,
        )
        average_marks = sum(marks_values) / len(marks_values) if marks_values else None
        if average_marks is not None and max_observed_marks:
            marks_score = min(100.0, (average_marks / max_observed_marks) * 100.0)
            components.append((marks_score, 0.10))

        available_weight = sum(weight for _, weight in components)
        raw_score = sum(score * weight for score, weight in components) / available_weight
        priority_score = round(raw_score * sample_confidence_factor, 1)

        # Small samples cannot earn a High label, even if every uploaded paper contains the topic.
        if total_papers < 3:
            priority = "Low"
        elif total_papers < 5 and priority_score >= 70:
            priority = "Medium"
        else:
            priority = "High" if priority_score >= 70 else "Medium" if priority_score >= 40 else "Low"

        representative = max(family_records, key=lambda item: len(item["question"]))
        variants = []
        seen_text: set[str] = set()
        for record in family_records:
            key = re.sub(r"\W+", " ", record["question"].lower()).strip()
            if key not in seen_text:
                variants.append(
                    {
                        "question": record["question"],
                        "source_file": record["source_file"],
                        "year": record["year"],
                        "marks": record["marks"],
                    }
                )
                seen_text.add(key)

        results.append(
            {
                "label": family["label"],
                "representative_question": representative["question"],
                "topic": representative.get("topic"),
                "unit": representative.get("unit"),
                "appearance_count": appearance_count,
                "total_papers": total_papers,
                "historical_frequency_percent": round(historical_frequency * 100.0, 1),
                "years_appeared": family_years,
                "average_marks": round(average_marks, 1) if average_marks is not None else None,
                "priority_score": priority_score,
                "priority": priority,
                "data_confidence": confidence_label,
                "question_variants": variants,
            }
        )

    return sorted(results, key=lambda item: (-item["priority_score"], -item["appearance_count"], item["label"]))


@app.get("/")
def home():
    return {"message": "RASEGAN AI API is running"}


@app.get("/health")
def health():
    return {"status": "healthy", "model": MODEL}


@app.post("/api/evaluate")
def evaluate(request: EvaluationRequest):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are RASEGAN AI, a rigorous but fair university exam evaluator. "
                        "Award partial credit for correct concepts even when an answer is incomplete. "
                        "Evaluate correctness, relevance, completeness and clarity. Do not award marks "
                        "for incorrect claims. Return: marks awarded out of maximum marks, percentage, "
                        "what the student did well, missing concepts and mistakes, specific improvement "
                        "advice, and a model answer. Use clear headings and readable formatting."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question ({request.max_marks} marks): {request.question}\n\n"
                        f"Student answer: {request.answer}"
                    ),
                },
            ],
            max_tokens=1000,
            temperature=0.2,
        )
        result = response.choices[0].message.content
        return {"success": True, "evaluation": result}
    except Exception as error:
        logger.exception("Answer evaluation failed")
        raise HTTPException(status_code=502, detail="AI evaluation failed. Check the backend logs and Nebius service status.") from error


@app.post("/api/past-papers/analyze")
async def analyze_past_papers(
    files: list[UploadFile] = File(..., description="One or more previous-year exam paper PDFs"),
    university: str = Form(default="Not specified"),
    subject: str = Form(default="Not specified"),
    exam_type: str = Form(default="Not specified"),
):
    """Extract questions from uploaded PDFs, group similar questions, and score study priority."""
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one PDF paper.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Upload no more than {MAX_FILES} PDF files at once.")

    paper_summaries: list[dict[str, Any]] = []
    question_records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for paper_index, upload in enumerate(files):
        filename = upload.filename or f"paper_{paper_index + 1}.pdf"
        if not filename.lower().endswith(".pdf"):
            errors.append({"file": filename, "error": "Only PDF files are supported."})
            continue

        try:
            pdf_bytes = await upload.read(MAX_FILE_BYTES + 1)
            if len(pdf_bytes) > MAX_FILE_BYTES:
                raise ValueError("File exceeds the 15 MB limit.")

            text, page_count = _extract_pdf_text(pdf_bytes, filename)
            extracted_questions = _ask_model_for_questions(text, filename, subject, exam_type)
            if not extracted_questions:
                raise ValueError("No examination questions could be identified in this PDF.")

            year = _year_from_filename(filename)
            accepted_paper_index = len(paper_summaries)
            paper_summaries.append(
                {
                    "filename": filename,
                    "year": year,
                    "page_count": page_count,
                    "questions_extracted": len(extracted_questions),
                }
            )
            for item in extracted_questions:
                question_records.append(
                    {
                        **item,
                        "paper_index": accepted_paper_index,
                        "source_file": filename,
                        "year": year,
                    }
                )
        except ValueError as error:
            errors.append({"file": filename, "error": str(error)})
        except Exception as error:
            logger.exception("Past-paper processing failed for %s", filename)
            errors.append(
                {
                    "file": filename,
                    "error": "AI extraction failed for this paper. Check the backend logs and try again.",
                }
            )
        finally:
            await upload.close()

    if not paper_summaries:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No papers could be analysed.",
                "file_errors": errors,
            },
        )

    try:
        families = _group_similar_questions(question_records, subject)
        ranked_questions = _build_priority_results(
            question_records, families, total_papers=len(paper_summaries)
        )
    except Exception as error:
        logger.exception("Past-paper grouping failed")
        raise HTTPException(
            status_code=502,
            detail="Questions were extracted, but AI grouping failed. Please retry the analysis.",
        ) from error

    return {
        "success": True,
        "message": "Past papers analysed. Priority scores describe historical study importance, not guaranteed exam predictions.",
        "metadata": {
            "university": university,
            "subject": subject,
            "exam_type": exam_type,
            "papers_analysed": len(paper_summaries),
            "questions_extracted": len(question_records),
            "question_families": len(ranked_questions),
            "years_covered": sorted({paper["year"] for paper in paper_summaries if paper["year"] is not None}),
            "data_confidence": "Very low" if len(paper_summaries) < 3 else "Limited" if len(paper_summaries) < 5 else "Moderate",
            "recommended_minimum_papers": 5,
        },
        "papers": paper_summaries,
        "ranked_questions": ranked_questions,
        "file_errors": errors,
        "scoring_method": {
            "frequency_weight": 70,
            "recency_weight": 20,
            "marks_weight": 10,
            "sample_confidence_rule": "The weighted historical score is multiplied by min(successfully_analysed_papers / 5, 1). With fewer than 3 papers, questions cannot be labelled High priority. With 3-4 papers, the data confidence is Limited.",
            "note": "This is a preparation-priority indicator, not the probability that a question will appear in a future exam. Year is read from the PDF filename when it contains a four-digit year. Recency is omitted when fewer than two distinct paper years are known; component weights are then rebalanced. Marks are used only when extracted explicitly.",
        },
    }
