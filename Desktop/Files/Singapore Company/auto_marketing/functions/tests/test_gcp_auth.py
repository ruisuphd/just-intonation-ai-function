from __future__ import annotations

import subprocess

import pytest
from google.auth.exceptions import RefreshError

from shared import gcp_auth


class DummyCredentials:
    valid = False
    expired = True
    quota_project_id = None

    def __init__(self, error: Exception | None = None):
        self._error = error

    def refresh(self, request) -> None:
        if self._error:
            raise self._error

    def with_quota_project(self, project_id: str):
        self.quota_project_id = project_id
        return self


def test_get_google_credentials_falls_back_to_gcloud_with_quota_project(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "intonation-labs-marketing")
    monkeypatch.setattr(
        gcp_auth.google.auth,
        "default",
        lambda: (
            DummyCredentials(
                RefreshError("Reauthentication is needed. Please reauthenticate.")
            ),
            "ignored-project",
        ),
    )
    monkeypatch.setattr(gcp_auth.shutil, "which", lambda name: "/usr/bin/gcloud")
    monkeypatch.setattr(
        gcp_auth.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="test-token\n",
            stderr="",
        ),
    )

    creds, project_id, expires_at = gcp_auth.get_google_credentials(
        require_quota_project=True
    )

    assert project_id == "intonation-labs-marketing"
    assert creds.token == "test-token"
    assert creds.quota_project_id == "intonation-labs-marketing"
    assert expires_at is not None


def test_get_google_credentials_raises_clear_error_without_fallback(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "intonation-labs-marketing")
    monkeypatch.setattr(
        gcp_auth.google.auth,
        "default",
        lambda: (
            DummyCredentials(
                RefreshError("Reauthentication is needed. Please reauthenticate.")
            ),
            "ignored-project",
        ),
    )
    monkeypatch.setattr(gcp_auth.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="application-default login"):
        gcp_auth.get_google_credentials(require_quota_project=True)
