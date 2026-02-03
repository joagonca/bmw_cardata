"""Config flow for BMW CarData integration."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from typing import Any

import aiohttp
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
)
from .utils import parse_token_response

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
    data = {
        "client_id": client_id,
        "response_type": "device_code",
        "scope": DEFAULT_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    def _do_request() -> dict[str, Any]:
        """Execute the HTTP request in executor."""
        import requests

        response = requests.post(
            DEVICE_CODE_ENDPOINT,
            data=data,
            timeout=30,
        )

        if response.status_code == 400:
            error_data = response.json()
            if error_data.get("error") == "invalid_client":
                raise InvalidClientError()
            raise AuthError(error_data.get("error_description", "Unknown error"))
        response.raise_for_status()
        return response.json()

    result = await hass.async_add_executor_job(_do_request)
    _LOGGER.debug("Device code requested, expires in %ds", result.get("expires_in", 0))
    return result


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
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(max_attempts):
            await asyncio.sleep(interval)

            data = {
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "code_verifier": code_verifier,
            }

            async with session.post(
                TOKEN_ENDPOINT,
                data=data,
            ) as response:
                if response.status == 200:
                    _LOGGER.info("OAuth authorization completed successfully")
                    return await response.json()

                error_data = await response.json()
                error = error_data.get("error", "")

                if error == "authorization_pending":
                    if attempt % 6 == 0:  # Log every 30s (assuming 5s interval)
                        _LOGGER.debug("Waiting for user authorization (attempt %d/%d)", attempt + 1, max_attempts)
                    continue
                elif error == "slow_down":
                    interval += 5
                    _LOGGER.debug("Slowing down polling to %ds interval", interval)
                    continue
                elif error == "expired_token":
                    _LOGGER.warning("Device code expired before user authorized")
                    raise AuthTimeoutError()
                elif error == "access_denied":
                    _LOGGER.warning("User denied authorization")
                    raise AuthDeniedError()
                else:
                    _LOGGER.error("Token request error: %s", error_data.get("error_description", error))
                    raise AuthError(error_data.get("error_description", f"Error: {error}"))

    raise AuthTimeoutError()


async def _get_vehicles(
    hass: HomeAssistant, access_token: str
) -> list[dict[str, Any]]:
    """Get list of mapped vehicles."""
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{API_BASE_URL}/customers/vehicles/mappings",
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-version": "v1",
            },
        ) as response:
            response.raise_for_status()
            vehicles = await response.json()
            _LOGGER.debug("Found %d vehicle mappings", len(vehicles))
            return vehicles


async def _get_basic_data(
    hass: HomeAssistant, access_token: str, vin: str
) -> dict[str, Any]:
    """Get basic vehicle data to validate VIN access."""
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{API_BASE_URL}/customers/vehicles/{vin}/basicData",
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-version": "v1",
            },
        ) as response:
            if response.status == 403:
                _LOGGER.warning("No permission to access VIN %s", vin[-6:])
                raise VINPermissionError()
            response.raise_for_status()
            data = await response.json()
            _LOGGER.debug(
                "Vehicle: %s %s (%s)",
                data.get("brand", "?"),
                data.get("modelName", "?"),
                vin[-6:],
            )
            return data


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

    def _get_existing_tokens(self) -> tuple[str, dict[str, Any]] | None:
        """Get tokens from an existing config entry if available."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if CONF_TOKENS in entry.data and CONF_CLIENT_ID in entry.data:
                return entry.data[CONF_CLIENT_ID], entry.data[CONF_TOKENS]
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - get client ID or reuse existing credentials."""
        errors: dict[str, str] = {}

        # Check for existing credentials
        existing = self._get_existing_tokens()
        if existing:
            self._client_id, self._tokens = existing
            # Skip auth, go directly to VIN selection
            return await self.async_step_select_vin()

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
                _LOGGER.error("Device code request failed: %s", err)
                errors["base"] = "api_error"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the auth step - show URL and code, poll when user confirms."""
        if self._device_code_response is None:
            return await self.async_step_user()

        errors: dict[str, str] = {}
        
        verification_url = (
            self._device_code_response.get("verification_uri_complete") 
            or self._device_code_response.get("verification_uri")
        )
        user_code = self._device_code_response.get("user_code", "")

        if user_input is not None:
            # User clicked confirm, start polling for token
            try:
                token_data = await _poll_for_token(
                    self.hass,
                    self._client_id,
                    self._device_code_response["device_code"],
                    self._code_verifier,
                    self._device_code_response.get("interval", 5),
                    self._device_code_response.get("expires_in", 600),
                )
                self._tokens = parse_token_response(token_data)
                return await self.async_step_select_vin()
            except AuthTimeoutError:
                return self.async_abort(reason="auth_timeout")
            except AuthDeniedError:
                return self.async_abort(reason="auth_denied")
            except Exception as err:
                _LOGGER.error("Auth polling failed: %s", err)
                errors["base"] = "auth_failed"

        # Show form with URL and code
        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema({}),
            description_placeholders={
                "url": verification_url,
                "user_code": user_code,
            },
            errors=errors,
        )

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
                _LOGGER.error("Failed to fetch vehicles: %s", err)
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
                _LOGGER.error("VIN validation failed for %s: %s", vin[-6:], err)
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
