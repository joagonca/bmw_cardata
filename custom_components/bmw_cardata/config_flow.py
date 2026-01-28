"""Config flow for BMW CarData integration."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from typing import Any

import httpx
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    API_BASE_URL,
    CONF_CLIENT_ID,
    CONF_TOKENS,
    CONF_VEHICLE_INFO,
    CONF_VIN,
    DEFAULT_SCOPES,
    DEVICE_CODE_ENDPOINT,
    DOMAIN,
    TOKEN_ACCESS,
    TOKEN_ENDPOINT,
    TOKEN_EXPIRES_AT,
    TOKEN_GCID,
    TOKEN_ID,
    TOKEN_REFRESH,
    TOKEN_REFRESH_EXPIRES_AT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): cv.string,
    }
)


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


async def _request_device_code(
    hass: HomeAssistant, client_id: str, code_challenge: str
) -> dict[str, Any]:
    """Request device code from BMW."""

    async def _do_request() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DEVICE_CODE_ENDPOINT,
                data={
                    "client_id": client_id,
                    "response_type": "device_code",
                    "scope": DEFAULT_SCOPES,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code == 400:
                error_data = response.json()
                if error_data.get("error") == "invalid_client":
                    raise InvalidClientError()
                raise AuthError(error_data.get("error_description", "Unknown error"))
            response.raise_for_status()
            return response.json()

    return await _do_request()


async def _poll_for_token(
    hass: HomeAssistant,
    client_id: str,
    device_code: str,
    code_verifier: str,
    interval: int,
    expires_in: int,
) -> dict[str, Any]:
    """Poll for access token after user authorizes."""
    max_attempts = expires_in // interval

    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(max_attempts):
            await asyncio.sleep(interval)

            response = await client.post(
                TOKEN_ENDPOINT,
                data={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                return response.json()

            error_data = response.json()
            error = error_data.get("error", "")

            if error == "authorization_pending":
                continue
            elif error == "slow_down":
                interval += 5
                continue
            elif error == "expired_token":
                raise AuthTimeoutError()
            elif error == "access_denied":
                raise AuthDeniedError()
            else:
                raise AuthError(error_data.get("error_description", f"Error: {error}"))

    raise AuthTimeoutError()


async def _get_vehicles(
    hass: HomeAssistant, access_token: str
) -> list[dict[str, Any]]:
    """Get list of mapped vehicles."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/customers/vehicles/mappings",
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-version": "v1",
            },
        )
        response.raise_for_status()
        return response.json()


async def _get_basic_data(
    hass: HomeAssistant, access_token: str, vin: str
) -> dict[str, Any]:
    """Get basic vehicle data to validate VIN access."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/customers/vehicles/{vin}/basicData",
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-version": "v1",
            },
        )
        if response.status_code == 403:
            raise VINPermissionError()
        response.raise_for_status()
        return response.json()


def _parse_token_response(token_data: dict[str, Any]) -> dict[str, Any]:
    """Parse token response and extract relevant data."""
    import time

    # Extract GCID from ID token (it's a JWT, decode the payload)
    id_token = token_data.get("id_token", "")
    gcid = ""
    if id_token:
        try:
            # JWT is header.payload.signature, we need payload
            payload_b64 = id_token.split(".")[1]
            # Add padding if needed
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            import json

            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            gcid = payload.get("sub", "")
        except Exception:
            _LOGGER.warning("Failed to extract GCID from ID token")

    expires_in = token_data.get("expires_in", 3600)
    refresh_expires_in = token_data.get("refresh_expires_in", 1209600)  # 2 weeks default

    return {
        TOKEN_ACCESS: token_data.get("access_token"),
        TOKEN_REFRESH: token_data.get("refresh_token"),
        TOKEN_ID: token_data.get("id_token"),
        TOKEN_GCID: gcid,
        TOKEN_EXPIRES_AT: int(time.time()) + expires_in,
        TOKEN_REFRESH_EXPIRES_AT: int(time.time()) + refresh_expires_in,
    }


class InvalidClientError(Exception):
    """Invalid client ID."""


class AuthError(Exception):
    """General auth error."""


class AuthTimeoutError(Exception):
    """Auth timeout."""


class AuthDeniedError(Exception):
    """Auth denied by user."""


class VINPermissionError(Exception):
    """No permission for VIN."""


class BMWCarDataConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BMW CarData."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._client_id: str | None = None
        self._code_verifier: str | None = None
        self._device_code_response: dict[str, Any] | None = None
        self._tokens: dict[str, Any] | None = None
        self._vehicles: list[dict[str, Any]] | None = None
        self._poll_task: asyncio.Task | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - get client ID."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._client_id = user_input[CONF_CLIENT_ID]

            # Generate PKCE parameters
            self._code_verifier, code_challenge = _generate_pkce()

            try:
                # Request device code
                self._device_code_response = await _request_device_code(
                    self.hass, self._client_id, code_challenge
                )
                return await self.async_step_auth()
            except InvalidClientError:
                errors["base"] = "invalid_client_id"
            except Exception as err:
                _LOGGER.exception("Error requesting device code: %s", err)
                errors["base"] = "api_error"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the auth step - show URL and poll for token."""
        if self._device_code_response is None:
            return await self.async_step_user()

        if self._poll_task is None:
            # Start polling in background
            self._poll_task = self.hass.async_create_task(
                self._async_poll_for_token()
            )

        if not self._poll_task.done():
            # Show progress with URL and code
            return self.async_show_progress(
                step_id="auth",
                progress_action="auth",
                description_placeholders={
                    "url": self._device_code_response.get(
                        "verification_uri", "https://bmw-cardata.bmwgroup.com"
                    ),
                    "user_code": self._device_code_response.get("user_code", ""),
                },
            )

        # Polling complete, check result
        try:
            self._tokens = self._poll_task.result()
            return self.async_show_progress_done(next_step_id="select_vin")
        except AuthTimeoutError:
            return self.async_abort(reason="auth_timeout")
        except AuthDeniedError:
            return self.async_abort(reason="auth_denied")
        except Exception as err:
            _LOGGER.exception("Auth error: %s", err)
            return self.async_abort(reason="unknown")

    async def _async_poll_for_token(self) -> dict[str, Any]:
        """Poll for token in background."""
        assert self._device_code_response is not None
        assert self._client_id is not None
        assert self._code_verifier is not None

        token_data = await _poll_for_token(
            self.hass,
            self._client_id,
            self._device_code_response["device_code"],
            self._code_verifier,
            self._device_code_response.get("interval", 5),
            self._device_code_response.get("expires_in", 600),
        )
        return _parse_token_response(token_data)

    async def async_step_select_vin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle VIN selection step."""
        errors: dict[str, str] = {}

        if self._tokens is None:
            return await self.async_step_user()

        # Fetch vehicles if not already done
        if self._vehicles is None:
            try:
                all_vehicles = await _get_vehicles(
                    self.hass, self._tokens[TOKEN_ACCESS]
                )
                # Filter to PRIMARY only
                self._vehicles = [
                    v for v in all_vehicles
                    if v.get("mappingType") == "PRIMARY"
                ]
            except Exception as err:
                _LOGGER.exception("Error fetching vehicles: %s", err)
                return self.async_abort(reason="api_error")

        if not self._vehicles:
            return self.async_abort(reason="no_vehicles")

        if user_input is not None:
            vin = user_input[CONF_VIN]

            # Check if already configured
            await self.async_set_unique_id(vin)
            self._abort_if_unique_id_configured()

            # Validate VIN access by fetching basic data
            try:
                vehicle_info = await _get_basic_data(
                    self.hass, self._tokens[TOKEN_ACCESS], vin
                )

                return self.async_create_entry(
                    title=f"{vehicle_info.get('brand', 'BMW')} {vehicle_info.get('modelName', vin[:8])}",
                    data={
                        CONF_CLIENT_ID: self._client_id,
                        CONF_VIN: vin,
                        CONF_TOKENS: self._tokens,
                        CONF_VEHICLE_INFO: {
                            "brand": vehicle_info.get("brand"),
                            "model": vehicle_info.get("modelName"),
                            "series": vehicle_info.get("series"),
                            "body_type": vehicle_info.get("bodyType"),
                            "drive_train": vehicle_info.get("driveTrain"),
                            "propulsion_type": vehicle_info.get("propulsionType"),
                        },
                    },
                )
            except VINPermissionError:
                errors["base"] = "vin_permission"
            except Exception as err:
                _LOGGER.exception("Error validating VIN: %s", err)
                errors["base"] = "api_error"

        # Build VIN selector
        vin_options = {v["vin"]: v["vin"] for v in self._vehicles}

        return self.async_show_form(
            step_id="select_vin",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VIN): vol.In(vin_options),
                }
            ),
            errors=errors,
        )
