# Choice under Risk Assignment

Streamlit implementation of the active Qualtrics assignment flow. Each participant:

1. enters an e-mail address to begin or resume;
2. enters a full name on first use and receives a random, unique eight-digit subject ID;
3. receives two reproducibly assigned cases out of four;
4. answers the component and explanation questions together for Question 1;
5. assesses and corrects the supplied Qualtrics ChatGPT response for Question 2;
6. reviews and confirms or edits an LLM-generated bullet summary after each question.

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

- `data/responses/<random-key>.json`: the authoritative private response record, updated before the LLM call, after the LLM result, and after confirmation.
- `data/answers.csv`: one de-identified row per completed subject; it is created only after both cases are complete.
- `data/subjects.csv`: the separate `SubjectId`, name and e-mail identity log.
- `data/_email_index/<email-hash>.json`: the private resume lookup, without a plain-text e-mail address.

The answer CSV contains `SubjectId` but never name or e-mail. Completion writes the
response JSON first, merges the row into `answers.csv`, then marks the JSON as synced,
so a failed final merge can be retried without duplicating a row.

## Keep the deployed app awake

The **Keep Streamlit awake** GitHub Action visits the public app every six hours
through Friday 20 November 2026. On Saturday 21 November it visits at 01:17,
07:17 and finally 12:47 CET, then stops at the configured deadline of 13:00 CET
(12:00 UTC). It clicks **Yes, get this app back up!** only when Streamlit shows
that control and verifies the assignment's e-mail field and **Next** button. It
never fills or submits the form, enters survey data, or calls the LLM.

The workflow is `.github/workflows/streamlit-keepalive.yml`; its browser check is
`scripts/wake_streamlit.py`. It assumes the public entry URL is
https://be-choice-under-risk-assignment.streamlit.app/. If the deployed slug differs,
set the repository Actions variable `STREAMLIT_APP_URL` to the correct root
`https://NAME.streamlit.app/` URL. The action can also be tested immediately from
**Actions → Keep Streamlit awake → Run workflow**.

## Deployment

For local development, leave `STORAGE_BACKEND = "local"`. For persistent Streamlit
deployment, create a scoped Dropbox app with App Folder access and enable
`files.content.read`, `files.content.write`, and `files.metadata.read`. Generate an
offline refresh token locally with:

```powershell
.\.venv\Scripts\python.exe tools\dropbox_oauth.py
```

In Streamlit **App settings → Secrets**, use root-level TOML values:

```toml
STORAGE_BACKEND = "dropbox"

DROPBOX_APP_KEY = "..."
DROPBOX_APP_SECRET = "..."
DROPBOX_REFRESH_TOKEN = "..."
DROPBOX_ROOT_PATH = "/choice_under_risk_assignment"
DROPBOX_CSV_NAME = "answers.csv"
DROPBOX_SUBJECT_CSV_NAME = "subjects.csv"

LLM_MODE = "openai"
KEY_OPENAI = "..."
OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_MAX_OUTPUT_TOKENS = "800"
OPENAI_TIMEOUT_SECONDS = "45"
```

The Dropbox app folder becomes the authoritative store. It contains one private JSON
per response, a hashed e-mail resume index, the separate `subjects.csv` identity log,
and the completion-only `answers.csv`. Remote writes use Dropbox revisions: stale tabs
cannot overwrite newer answers, concurrent CSV merges are retried, and an interrupted
final merge can be retried without duplicating a subject row. Never commit real secrets.

