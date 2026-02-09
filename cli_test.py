#!/usr/bin/env python3
"""CLI test script to inspect BMW CarData API responses."""

import base64
import hashlib
import json
import secrets
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

API_BASE_URL = "https://api-cardata.bmwgroup.com"
AUTH_BASE_URL = "https://customer.bmwgroup.com"
DEVICE_CODE_ENDPOINT = f"{AUTH_BASE_URL}/gcdm/oauth/device/code"
TOKEN_ENDPOINT = f"{AUTH_BASE_URL}/gcdm/oauth/token"
DEFAULT_SCOPES = "authenticate_user openid cardata:streaming:read cardata:api:read"


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def post_form(url: str, data: dict) -> dict:
    """POST form data and return JSON response."""
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=encoded_data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, access_token: str) -> dict:
    """GET JSON with authorization header."""
    request = urllib.request.Request(url)
    request.add_header("Authorization", f"Bearer {access_token}")
    request.add_header("x-version", "v1")
    
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_device_code(client_id: str, code_challenge: str) -> dict:
    """Request device code from BMW."""
    return post_form(DEVICE_CODE_ENDPOINT, {
        "client_id": client_id,
        "response_type": "device_code",
        "scope": DEFAULT_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })


def poll_for_token(client_id: str, device_code: str, code_verifier: str, interval: int, expires_in: int) -> dict:
    """Poll for access token after user authorizes."""
    max_attempts = expires_in // interval

    for attempt in range(max_attempts):
        time.sleep(interval)

        data = urllib.parse.urlencode({
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "code_verifier": code_verifier,
        }).encode("utf-8")

        request = urllib.request.Request(TOKEN_ENDPOINT, data=data, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_data = json.loads(e.read().decode("utf-8"))
            error = error_data.get("error", "")

            if error == "authorization_pending":
                print(".", end="", flush=True)
                continue
            elif error == "slow_down":
                interval += 5
                continue
            elif error == "expired_token":
                raise Exception("Device code expired")
            elif error == "access_denied":
                raise Exception("Authorization denied")
            else:
                raise Exception(f"Token error: {error_data.get('error_description', error)}")

    raise Exception("Authorization timeout")


def get_vehicles(access_token: str) -> list[dict]:
    """Get list of vehicles."""
    return get_json(f"{API_BASE_URL}/customers/vehicles/mappings", access_token)


def get_basic_data(access_token: str, vin: str) -> dict:
    """Fetch basic vehicle data from BMW CarData API."""
    return get_json(f"{API_BASE_URL}/customers/vehicles/{vin}/basicData", access_token)


def main():
    if len(sys.argv) != 2:
        print("Usage: python cli_test.py <client_id>")
        sys.exit(1)

    client_id = sys.argv[1]

    # Step 1: Generate PKCE
    code_verifier, code_challenge = generate_pkce()

    # Step 2: Request device code
    print("Requesting device code...")
    device_code_response = request_device_code(client_id, code_challenge)

    verification_url = device_code_response.get("verification_uri_complete") or device_code_response.get("verification_uri")
    user_code = device_code_response.get("user_code", "")

    print(f"\n{'=' * 50}")
    print(f"Go to: {verification_url}")
    print(f"Enter code: {user_code}")
    print(f"{'=' * 50}\n")

    # Step 3: Poll for token
    print("Waiting for authorization", end="", flush=True)
    token_data = poll_for_token(
        client_id,
        device_code_response["device_code"],
        code_verifier,
        device_code_response.get("interval", 5),
        device_code_response.get("expires_in", 600),
    )
    print("\nAuthorized!")

    access_token = token_data["access_token"]

    # Step 4: Get vehicles
    print("\nFetching vehicles...")
    vehicles = get_vehicles(access_token)
    primary_vehicles = [v for v in vehicles if v.get("mappingType") == "PRIMARY"]

    if not primary_vehicles:
        print("No PRIMARY vehicles found")
        sys.exit(1)

    # Step 5: Get basic data for each vehicle
    for vehicle in primary_vehicles:
        vin = vehicle["vin"]
        print(f"\n{'=' * 50}")
        print(f"VIN: {vin}")
        print(f"{'=' * 50}")

        try:
            data = get_basic_data(access_token, vin)
            print(json.dumps(data, indent=2))
        except urllib.error.HTTPError as e:
            print(f"HTTP Error: {e.code}")
            print(e.read().decode("utf-8"))


if __name__ == "__main__":
    main()
