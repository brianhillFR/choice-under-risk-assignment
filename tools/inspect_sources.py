from __future__ import annotations

import html
import json
import re
import sys
import zipfile
from pathlib import Path

from docx import Document


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"[ \t\r\f\v]+")


def clean_html(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = "\n".join(SPACE_RE.sub(" ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_qsf(path: Path) -> dict[str, object]:
    survey = json.loads(path.read_text(encoding="utf-8-sig"))
    questions = {
        item["PrimaryAttribute"]: item["Payload"]
        for item in survey["SurveyElements"]
        if item.get("Element") == "SQ"
    }
    blocks_payload = next(
        item["Payload"] for item in survey["SurveyElements"] if item.get("Element") == "BL"
    )
    flow = next(
        item["Payload"] for item in survey["SurveyElements"] if item.get("Element") == "FL"
    )

    active_block_ids: list[str] = []

    def visit(nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            if node.get("Type") in {"Block", "Standard"} and node.get("ID"):
                active_block_ids.append(str(node["ID"]))
            if isinstance(node.get("Flow"), list):
                visit(node["Flow"])

    visit(flow.get("Flow", []))
    blocks = {value["ID"]: value for value in blocks_payload.values()}
    active_qids: list[str] = []
    active_blocks: list[dict[str, object]] = []
    for block_id in active_block_ids:
        block = blocks[block_id]
        qids = [element["QuestionID"] for element in block.get("BlockElements", [])]
        active_qids.extend(qids)
        active_blocks.append(
            {
                "id": block_id,
                "description": block.get("Description"),
                "questions": qids,
            }
        )

    active_questions: list[dict[str, object]] = []
    for qid in dict.fromkeys(active_qids):
        q = questions[qid]
        choices = {
            str(key): clean_html(value.get("Display", value)) if isinstance(value, dict) else clean_html(value)
            for key, value in (q.get("Choices") or {}).items()
        }
        answers = {
            str(key): clean_html(value.get("Display", value)) if isinstance(value, dict) else clean_html(value)
            for key, value in (q.get("Answers") or {}).items()
        }
        active_questions.append(
            {
                "qid": qid,
                "data_export_tag": q.get("DataExportTag"),
                "question_type": q.get("QuestionType"),
                "selector": q.get("Selector"),
                "sub_selector": q.get("SubSelector"),
                "question_text": clean_html(q.get("QuestionText")),
                "question_description": clean_html(q.get("QuestionDescription")),
                "choices": choices,
                "answers": answers,
                "choice_order": q.get("ChoiceOrder"),
                "validation": q.get("Validation"),
                "display_logic": q.get("DisplayLogic"),
                "configuration": q.get("Configuration"),
            }
        )

    return {
        "survey_entry": survey["SurveyEntry"],
        "flow": flow,
        "active_blocks": active_blocks,
        "active_questions": active_questions,
    }


def extract_docx(path: Path) -> dict[str, object]:
    document = Document(path)
    paragraphs = [
        {"index": index, "style": paragraph.style.name, "text": paragraph.text}
        for index, paragraph in enumerate(document.paragraphs)
        if paragraph.text.strip()
    ]
    tables = []
    for table_index, table in enumerate(document.tables):
        tables.append(
            {
                "index": table_index,
                "rows": [[cell.text for cell in row.cells] for row in table.rows],
            }
        )
    return {"paragraphs": paragraphs, "tables": tables}


def scan_zip(path: Path) -> list[dict[str, object]]:
    allowed = {".py", ".html", ".js", ".mjs", ".md", ".txt", ".json", ".toml"}
    terms = ("email", "return", "subject code", "participant code", "qualtrics")
    results: list[dict[str, object]] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or Path(info.filename).suffix.lower() not in allowed:
                continue
            if info.file_size > 5_000_000:
                continue
            try:
                content = archive.read(info).decode("utf-8", errors="ignore")
            except Exception:
                continue
            lowered = content.lower()
            hits = [term for term in terms if term in lowered]
            if not hits:
                continue
            excerpts = []
            for term in hits:
                start = max(0, lowered.find(term) - 160)
                end = min(len(content), lowered.find(term) + 320)
                excerpts.append(SPACE_RE.sub(" ", content[start:end]).replace("\n", " "))
            results.append(
                {
                    "path": info.filename,
                    "size": info.file_size,
                    "hits": hits,
                    "excerpts": excerpts,
                }
            )
    return results


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("usage: inspect_sources.py QSF DOCX ZIP OUTPUT_DIR")
    qsf_path, docx_path, zip_path, output_dir = map(Path, sys.argv[1:])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "qualtrics_active.json").write_text(
        json.dumps(extract_qsf(qsf_path), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "word_content.json").write_text(
        json.dumps(extract_docx(docx_path), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "zip_identity_search.json").write_text(
        json.dumps(scan_zip(zip_path), ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
