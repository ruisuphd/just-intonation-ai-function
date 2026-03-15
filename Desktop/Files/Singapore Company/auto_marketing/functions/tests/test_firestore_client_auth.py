from __future__ import annotations

import subprocess

import pytest
from google.auth.exceptions import RefreshError

from shared import firestore_client


class DummyCredentials:
    valid = False
    expired = True

    def __init__(self, error: Exception | None = None):
        self._error = error

    def refresh(self, request) -> None:
        if self._error:
            raise self._error


def test_client_kwargs_falls_back_to_gcloud_when_adc_needs_reauth(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "intonation-labs-marketing")
    monkeypatch.setattr(
        firestore_client.google.auth,
        "default",
        lambda: (
            DummyCredentials(
                RefreshError("Reauthentication is needed. Please reauthenticate.")
            ),
            "ignored-project",
        ),
    )
    monkeypatch.setattr(
        firestore_client.shutil, "which", lambda name: "/usr/bin/gcloud"
    )
    monkeypatch.setattr(
        firestore_client.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="test-token\n",
            stderr="",
        ),
    )

    kwargs, expires_at = firestore_client._client_kwargs()

    assert kwargs["project"] == "intonation-labs-marketing"
    assert kwargs["credentials"].__class__.__name__ == "Credentials"
    assert kwargs["credentials"].token == "test-token"
    assert expires_at is not None


def test_client_kwargs_raises_clear_error_when_reauth_has_no_fallback(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setattr(
        firestore_client.google.auth,
        "default",
        lambda: (
            DummyCredentials(
                RefreshError("Reauthentication is needed. Please reauthenticate.")
            ),
            "intonation-labs-marketing",
        ),
    )
    monkeypatch.setattr(firestore_client.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="application-default login"):
        firestore_client._client_kwargs()
