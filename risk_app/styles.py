QUALTRICS_CSS = """
<style>
    :root {
        --hec-blue: #003b5c;
        --hec-red: #b3203b;
        --ink: #202124;
        --muted: #667085;
        --line: #d9dde3;
        --soft: #f5f7f9;
    }
    .stApp { background: #f1f3f5; color: var(--ink); }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stAppViewContainer"] > .main { background: #f1f3f5; }
    .block-container {
        max-width: 920px;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
    }
    .survey-shell {
        background: white;
        border: 1px solid #e1e4e8;
        border-top: 6px solid var(--hec-blue);
        box-shadow: 0 3px 16px rgba(16, 24, 40, .08);
        padding: 1.75rem 2.25rem .4rem;
        margin-bottom: 1.25rem;
    }
    .survey-brand {
        color: var(--hec-blue);
        font-size: .84rem;
        font-weight: 800;
        letter-spacing: .15em;
        margin-bottom: .25rem;
    }
    .survey-title { font-size: 1.6rem; font-weight: 650; margin: 0 0 .4rem; }
    .survey-meta { color: var(--muted); font-size: .92rem; margin-bottom: 1.2rem; }
    .case-card {
        border-left: 4px solid var(--hec-red);
        background: #fafafa;
        padding: 1rem 1.15rem .85rem;
        margin: 1rem 0 1.25rem;
    }
    .case-label {
        color: var(--hec-red);
        font-size: .82rem;
        font-weight: 750;
        letter-spacing: .08em;
        text-transform: uppercase;
        margin-bottom: .35rem;
    }
    .summary-panel {
        background: var(--soft);
        border: 1px solid var(--line);
        padding: 1rem 1.2rem .55rem;
        margin: .6rem 0 1rem;
    }
    .privacy-note { color: var(--muted); font-size: .83rem; margin-top: .5rem; }
    div[data-testid="stForm"] {
        background: white;
        border: 1px solid #e1e4e8;
        padding: 1.25rem 1.45rem 1.4rem;
    }
    .stButton button, .stFormSubmitButton button {
        border-radius: 2px;
        border: 1px solid var(--hec-blue);
        background: var(--hec-blue);
        color: white;
        font-weight: 650;
        min-height: 2.7rem;
    }
    .stButton button:hover, .stFormSubmitButton button:hover {
        border-color: #002a42;
        background: #002a42;
        color: white;
    }
    textarea, input { border-radius: 2px !important; }
    h1, h2, h3 { color: var(--ink); }
    @media (max-width: 700px) {
        .block-container { padding: .75rem .65rem 2rem; }
        .survey-shell { padding: 1.25rem 1rem .2rem; }
        div[data-testid="stForm"] { padding: 1rem .85rem 1.15rem; }
    }
</style>
"""

