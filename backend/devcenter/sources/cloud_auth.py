"""Cloud sign-in: MSAL public client, token cache, silent first (technical design section 10.1).

``msal`` is an optional dependency (``pip install .[cloud]``). This module
imports it only when the user signs in. The tests use a fake token provider
with the same interface (``TokenProvider``).

The Entra app ID comes from the settings only (task T1). The repo has no
default value. The token stays in memory and in the MSAL token cache, which
Windows protects (DPAPI). No session file and no ``connection.json`` gets a
token or the account name.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Protocol
from collections.abc import Mapping, Sequence

from backend.devcenter.errors import DevCenterError, not_allowed

POWER_BI_SCOPES = ("https://analysis.windows.net/powerbi/api/.default",)
FABRIC_SCOPES = ("https://api.fabric.microsoft.com/.default",)

PROMPT_NONE = "none"
PROMPT_SELECT_ACCOUNT = "select_account"

# Reason codes of a sign-in failure (UI design: sign-in failure copies).
REASON_CLIENT_ID_MISSING = "client_id_missing"
REASON_MSAL_MISSING = "msal_missing"
REASON_INTERACTION_REQUIRED = "interaction_required"
REASON_CANCELLED = "sign_in_cancelled"
REASON_ADMIN_CONSENT = "admin_consent_required"
REASON_NETWORK = "network"
REASON_FAILED = "sign_in_failed"

SETTINGS_ENV = "PBIBRAIN_CLOUD_CLIENT_ID"
TENANT_ENV = "PBIBRAIN_CLOUD_TENANT"


@dataclass(frozen=True)
class Account:
    """The signed-in account. Only memory holds it."""

    display_name: str
    tenant_id: str | None
    object_id: str | None


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_on: int

    def __repr__(self) -> str:  # The token never goes into a log line.
        return f"AccessToken(expires_on={self.expires_on})"


class TokenProvider(Protocol):
    def sign_in(self, scopes: Sequence[str], *, prompt: str | None = None) -> Account:
        """Get an account: ``None`` = silent, then interactive; ``none`` = silent only; ``select_account`` = account picker."""

    def token(self, scopes: Sequence[str], *, force_refresh: bool = False) -> AccessToken:
        """Get a token silently. Raise ``SignInRequired`` when the app must ask the user."""

    def account(self) -> Account | None:
        """Give the account of the last sign-in, or None."""


class SignInRequired(DevCenterError):
    def __init__(self, reason: str = REASON_INTERACTION_REQUIRED) -> None:
        super().__init__("action_not_allowed", "Sign in with Microsoft first.", {"reason": reason})


def sign_in_error(reason: str) -> DevCenterError:
    messages = {
        REASON_CLIENT_ID_MISSING: "Set the cloud app ID in the PBIBrain settings first.",
        REASON_MSAL_MISSING: "Install the cloud parts of PBIBrain first.",
        REASON_CANCELLED: "You closed the Microsoft window before the sign-in was complete.",
        REASON_ADMIN_CONSENT: "An admin must give consent to the PBIBrain app in Microsoft Entra ID.",
        REASON_NETWORK: "PBIBrain did not get a reply from the Microsoft sign-in service.",
    }
    return not_allowed(messages.get(reason, "Microsoft did not accept the sign-in."), reason)


@dataclass(frozen=True)
class CloudSettings:
    client_id: str
    authority: str


def settings_path() -> Path | None:
    value = os.environ.get("APPDATA")
    return Path(value) / "PBIBrain" / "settings.json" if value else None


def cloud_settings(path: Path | None = None) -> CloudSettings:
    """Read the Entra app ID from the environment or from the settings file. There is no default."""

    client_id = os.environ.get(SETTINGS_ENV, "").strip()
    tenant = os.environ.get(TENANT_ENV, "").strip()
    file = path if path is not None else settings_path()
    if not client_id and file is not None and file.is_file():
        try:
            cloud = json.loads(file.read_text(encoding="utf-8")).get("cloud") or {}
        except (OSError, ValueError, AttributeError):
            cloud = {}
        if isinstance(cloud, Mapping):
            client_id = str(cloud.get("client_id") or "").strip()
            tenant = tenant or str(cloud.get("tenant") or "").strip()
    if not client_id:
        raise sign_in_error(REASON_CLIENT_ID_MISSING)
    return CloudSettings(client_id, f"https://login.microsoftonline.com/{tenant or 'organizations'}")


def token_cache_path() -> Path | None:
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) / "PBIBrain" / "msal_token_cache.bin" if value else None


def _reason(result: Mapping[str, Any]) -> str:
    error = str(result.get("error") or "")
    description = str(result.get("error_description") or "")
    if error in {"authentication_canceled", "access_denied"} or "cancel" in description.casefold():
        return REASON_CANCELLED
    if "AADSTS65001" in description or "AADSTS90094" in description or "consent" in description.casefold():
        return REASON_ADMIN_CONSENT
    return REASON_FAILED


def _window_handle() -> int | None:
    """Give the window of the app (the foreground window at the click) for the Windows broker."""

    if sys.platform != "win32":
        return None
    try:
        import ctypes

        return int(ctypes.windll.user32.GetForegroundWindow()) or None
    except (AttributeError, OSError):
        return None


class MsalTokenProvider:
    """The real token provider: MSAL public client with the Windows broker (WAM)."""

    def __init__(self, settings: CloudSettings | None = None) -> None:
        self._settings = settings
        self._application: Any = None
        self._account: Account | None = None
        self._msal_account: Any = None
        self._lock = threading.RLock()

    def _app(self) -> Any:
        if self._application is not None:
            return self._application
        settings = self._settings or cloud_settings()
        try:
            import msal  # Optional dependency: import only at sign-in.
        except ImportError as exc:
            raise sign_in_error(REASON_MSAL_MISSING) from exc
        self._application = msal.PublicClientApplication(
            settings.client_id,
            authority=settings.authority,
            token_cache=self._cache(msal),
            enable_broker_on_windows=True,
        )
        return self._application

    @staticmethod
    def _cache(msal: Any) -> Any:
        path = token_cache_path()
        try:
            from msal_extensions import PersistedTokenCache, build_encrypted_persistence
        except ImportError:
            return msal.TokenCache()  # Memory only: no unprotected cache file.
        if path is None:
            return msal.TokenCache()
        path.parent.mkdir(parents=True, exist_ok=True)
        return PersistedTokenCache(build_encrypted_persistence(str(path)))

    def _remember(self, result: Mapping[str, Any]) -> AccessToken:
        if "access_token" not in result:
            raise sign_in_error(_reason(result))
        claims = result.get("id_token_claims") or {}
        if claims:
            self._account = Account(str(claims.get("name") or claims.get("preferred_username") or ""),
                                    claims.get("tid"), claims.get("oid"))
        expires_in = int(result.get("expires_in") or 0)
        return AccessToken(str(result["access_token"]), int(time.time()) + expires_in)

    def _silent(self, scopes: Sequence[str], force_refresh: bool) -> AccessToken | None:
        app = self._app()
        accounts = [self._msal_account] if self._msal_account else app.get_accounts()
        for account in accounts[:1]:
            result = app.acquire_token_silent(list(scopes), account=account, force_refresh=force_refresh)
            if result and "access_token" in result:
                self._msal_account = account
                token = self._remember(result)
                if self._account is None:
                    self._account = Account(str(account.get("username") or ""), account.get("realm"), None)
                return token
        return None

    def sign_in(self, scopes: Sequence[str], *, prompt: str | None = None) -> Account:
        with self._lock:
            try:
                if prompt != PROMPT_SELECT_ACCOUNT and self._silent(scopes, False) is not None:
                    assert self._account is not None
                    return self._account
                if prompt == PROMPT_NONE:
                    raise SignInRequired()
                app = self._app()
                result = app.acquire_token_interactive(
                    list(scopes), prompt=PROMPT_SELECT_ACCOUNT if prompt == PROMPT_SELECT_ACCOUNT else None,
                    parent_window_handle=_window_handle() or app.CONSOLE_WINDOW_HANDLE)
                self._remember(result)
                self._msal_account = None
                accounts = app.get_accounts()
                if accounts and self._account is not None:
                    wanted = self._account.object_id
                    self._msal_account = next((item for item in accounts if wanted and wanted in str(item.get("home_account_id"))), accounts[0])
            except (ConnectionError, OSError) as exc:
                raise sign_in_error(REASON_NETWORK) from exc
            if self._account is None:
                raise sign_in_error(REASON_FAILED)
            return self._account

    def token(self, scopes: Sequence[str], *, force_refresh: bool = False) -> AccessToken:
        with self._lock:
            try:
                token = self._silent(scopes, force_refresh)
            except (ConnectionError, OSError) as exc:
                raise sign_in_error(REASON_NETWORK) from exc
            if token is None:
                raise SignInRequired()
            return token

    def account(self) -> Account | None:
        return self._account
