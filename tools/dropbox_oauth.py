"""Create the offline Dropbox refresh token used by Streamlit deployment.

Run locally after creating a scoped Dropbox app with App Folder access:
    python tools/dropbox_oauth.py

The script prints credentials only to the terminal and never writes them.
"""

from __future__ import annotations

import getpass

from dropbox import DropboxOAuth2FlowNoRedirect


def main() -> None:
    app_key = input("Dropbox app key: ").strip()
    app_secret = getpass.getpass("Dropbox app secret: ").strip()
    if not app_key or not app_secret:
        raise SystemExit("Both the app key and app secret are required.")

    flow = DropboxOAuth2FlowNoRedirect(
        app_key,
        app_secret,
        token_access_type="offline",
    )
    print("\n1. Open this URL in your browser:\n")
    print(flow.start())
    print("\n2. Approve access, copy the authorization code, and paste it below.\n")
    authorization_code = getpass.getpass("Authorization code: ").strip()
    result = flow.finish(authorization_code)
    if not result.refresh_token:
        raise SystemExit("Dropbox did not return a refresh token.")

    print("\nAdd these values to Streamlit App settings → Secrets:\n")
    print(f'DROPBOX_APP_KEY = "{app_key}"')
    print(f'DROPBOX_APP_SECRET = "{app_secret}"')
    print(f'DROPBOX_REFRESH_TOKEN = "{result.refresh_token}"')
    print("\nDo not save these values in GitHub.")


if __name__ == "__main__":
    main()
