# Choice under Risk Assignment

Streamlit implementation of the active Qualtrics assignment flow. Each participant:

1. enters an e-mail address to begin or resume;
2. enters a surname on first use and receives a random, unique eight-digit subject ID;
3. receives two reproducibly assigned cases out of four;
4. answers the component and explanation questions together on one page for each case;
5. reviews and confirms or edits an LLM-generated bullet summary of the explanation.

There is no grading or feedback in the LLM prompt. The model is instructed only to
summarize arguments already present in the participant's answer.

## Run locally

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open <http://localhost:8501>.

The default `LLM_MODE=demo` completes the workflow without an API key. To use the
OpenAI Responses API, set `LLM_MODE=openai`, `OPENAI_API_KEY`, and optionally
`OPENAI_MODEL` (default `gpt-4.1-mini`). A Streamlit secret named `KEY_OPENAI`
is also supported. Do not put the key in source control.

## Local data files

- `data/responses/<random-key>.json`: the authoritative private response record, updated after each confirmed case.
- `data/answers.csv`: one de-identified row per completed subject; it is created only after both cases are complete.
- `data/subjects.csv`: the separate `SubjectId`, name and e-mail identity log.
- `data/_email_index/<email-hash>.json`: the private resume lookup, without a plain-text e-mail address.

The answer CSV contains `SubjectId` but never name or e-mail. Completion writes the
response JSON first, merges the row into `answers.csv`, then marks the JSON as synced,
so a failed final merge can be retried without duplicating a row. Storage is isolated
behind `JsonCsvRepository`; it can be replaced when the production DB details arrive
without changing the question or LLM workflow.

## Deployment

The app is ready for a standard Streamlit deployment. Production deployment should wait
for the database connection because a hosted app's local filesystem may be ephemeral.
The production adapter should retain the same JSON-first, completion-only export and
separate identity-log rules.

