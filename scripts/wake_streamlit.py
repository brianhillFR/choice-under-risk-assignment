"""Visit only the assignment entry screen; never enter or submit survey data."""
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    # `python scripts/wake_streamlit.py` otherwise exposes only scripts/ as the
    # import root on GitHub's runner, making risk_app unavailable.
    sys.path.insert(0, str(REPOSITORY_ROOT))

DEFAULT_URL = "https://choice-under-risk-assignment.streamlit.app/"
WAKE_BUTTON = re.compile(r"^Yes,?\s*get this app back up!?$", re.IGNORECASE)
ACCESS_HEADING = re.compile(
    r"You do not have access to this app or it does not exist", re.IGNORECASE
)


def app_url(value):
    """Prevent a participant resume link or credentials from entering the job."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".streamlit.app")
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "STREAMLIT_APP_URL must be the https://NAME.streamlit.app/ entry URL, "
            "without a participant link."
        )
    return value


def entry_labels():
    """Use the same entry label as the app instead of maintaining a duplicate."""
    from risk_app.content import EMAIL_QUESTION

    return EMAIL_QUESTION, "Next"


def wait_for_entry(
    page, labels, timeout_seconds=240, clock=time.monotonic, transient_errors=()
):
    """Allow the app to boot inside a Cloud wrapper iframe as well as directly."""
    deadline = clock() + timeout_seconds
    started = clock()
    wake_clicked = False
    while clock() < deadline:
        access_denied = False
        for frame in page.frames:
            try:
                email = frame.get_by_role(
                    "textbox", name=labels[0], exact=True
                ).first
                next_button = frame.get_by_role(
                    "button", name=labels[1], exact=True
                ).first
                if email.is_visible() and next_button.is_visible():
                    return wake_clicked
                wake = frame.get_by_role("button", name=WAKE_BUTTON).first
                if not wake_clicked and wake.is_visible():
                    wake.click(timeout=5000)
                    wake_clicked = True
                access_denied |= frame.get_by_role(
                    "heading", name=ACCESS_HEADING
                ).first.is_visible()
            except transient_errors:
                # Navigation can remove a wrapper iframe while the app wakes.
                continue
        if access_denied and clock() - started >= 10:
            raise RuntimeError(
                "Streamlit returned an access/not-found page. Check "
                "STREAMLIT_APP_URL and the app's public sharing setting."
            )
        page.wait_for_timeout(1000)
    raise RuntimeError(
        "The assignment email-entry screen did not become ready within "
        f"{timeout_seconds} seconds. Check the app URL and Streamlit deployment logs."
    )


def main():
    from playwright.sync_api import Error as BrowserError, sync_playwright

    url = app_url(os.environ.get("STREAMLIT_APP_URL", DEFAULT_URL))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            clicked = wait_for_entry(
                page, entry_labels(), transient_errors=(BrowserError,)
            )
            # Maintain the actual Streamlit browser connection briefly. Recheck
            # readiness before reporting success, without filling any input.
            page.wait_for_timeout(15000)
            wait_for_entry(
                page,
                entry_labels(),
                timeout_seconds=30,
                transient_errors=(BrowserError,),
            )
        finally:
            browser.close()
    message = (
        "Woke the sleeping app and verified its email-entry screen."
        if clicked
        else "App was already awake; verified its email-entry screen."
    )
    print(message)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write(
                message + "\n\nNo survey data was entered and no model calls were made.\n"
            )


def cli():
    if sys.argv[1:] == ["--check-entry-labels"]:
        print("\t".join(entry_labels()))
        return
    main()


if __name__ == "__main__":
    try:
        cli()
    except Exception as error:
        # Do not log page bodies, participant data or configuration secrets.
        detail = (
            str(error)
            if isinstance(error, (ValueError, RuntimeError, ImportError))
            else "Browser request failed; check the public URL and deployment logs."
        )
        print("Wake-up check failed: " + detail, file=sys.stderr)
        sys.exit(1)
