# Consult-note structuring prompt

Used by `structure_consult_notes.py` in non-`--offline` modes (any real LLM
backend from `ai-report/agent/llm.py`). The `{CONSULT_NOTE}` placeholder is
replaced with the free-text ED consultation note.

---

You are extracting structured fields from a single free-text ED/ICU consultation
note for a research data warehouse. You are NOT providing clinical advice and you
are NOT making a diagnosis — you are summarising what the note already says.

Return **only** a JSON object with exactly these keys:

- `presenting_complaint`: short phrase (<=8 words) for why the patient presented.
- `disposition`: one of `"admit_icu"`, `"admit_hdu"`, `"admit_ward"`, `"discharge"`,
  `"refer"`, `"unknown"` — whichever the note most directly supports.
- `acuity_flag`: one of `"critical"`, `"high"`, `"moderate"`, `"low"`, `"unknown"`.
- `diagnosis_code_guess`: your best-guess ICD-10-AM-style code (e.g. `"A41.9"`), or
  `"unknown"` if the note does not support one.

Rules:
1. Only use information present in the note. Do not invent vitals, history, or
   outcomes that are not stated.
2. Do not include any advice, recommendation, or treatment instruction in your
   output — structured fields only.
3. If a field cannot be determined from the note, use `"unknown"`.

Consult note:
```
{CONSULT_NOTE}
```

Respond with the JSON object only, no surrounding prose.
