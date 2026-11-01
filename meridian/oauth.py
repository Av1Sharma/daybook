"""Read-only Gmail installed-app OAuth with one-use state and PKCE."""

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode
import httpx

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GoogleOAuth:
    def __init__(self, settings):
        self.settings = settings
        self.pending = {}

    def begin(self, redirect_uri):
        client_id = self.settings.get("GOOGLE_CLIENT_ID")
        if not client_id:
            raise ValueError("Add your Google Desktop OAuth client ID first.")
        verifier = secrets.token_urlsafe(48)
        state = secrets.token_urlsafe(32)
        self.pending = {
            s: v for s, v in self.pending.items() if v["expires"] > time.monotonic()
        }
        if len(self.pending) >= 10:
            self.pending.clear()
        self.pending[state] = {
            "verifier": verifier,
            "redirect": redirect_uri,
            "expires": time.monotonic() + 600,
        }
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "access_type": "offline",
                "prompt": "consent select_account",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )

    async def finish(self, state, code):
        item = self.pending.pop(state, None)
        if not item or item["expires"] < time.monotonic():
            raise ValueError(
                "This sign-in expired or was already used. Start Connect Gmail again."
            )
        async with httpx.AsyncClient(timeout=30) as client:
            body = {
                "client_id": self.settings.get("GOOGLE_CLIENT_ID"),
                "code": code,
                "code_verifier": item["verifier"],
                "redirect_uri": item["redirect"],
                "grant_type": "authorization_code",
            }
            secret = self.settings.get("GOOGLE_CLIENT_SECRET")
            if secret:
                body["client_secret"] = secret
            response = await client.post(
                "https://oauth2.googleapis.com/token", data=body
            )
            response.raise_for_status()
            tokens = response.json()
            if SCOPE not in tokens.get("scope", "").split():
                raise ValueError("Gmail read-only permission was not granted.")
            if not tokens.get("refresh_token"):
                raise ValueError(
                    "Google did not return offline access. Reconnect with consent to keep Gmail connected."
                )
            profile = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": "Bearer " + tokens["access_token"]},
            )
            profile.raise_for_status()
            email = profile.json()["emailAddress"]
        accounts = json.loads(self.settings.get("GOOGLE_ACCOUNTS") or "{}")
        accounts[email] = tokens["refresh_token"]
        self.settings.set("GOOGLE_ACCOUNTS", json.dumps(accounts))
        self.settings.set("GOOGLE_EMAIL", email)
        return email
