"""POW Service Client - External POW service integration (POST /api/v1/sora/sentinel-token)"""
from typing import NamedTuple, Optional
from curl_cffi.requests import AsyncSession

from ..core.config import config
from ..core.logger import debug_logger


class SentinelResult(NamedTuple):
    """Result from external sentinel-token API."""

    sentinel_token: str
    device_id: Optional[str]
    user_agent: Optional[str]
    cookie_header: Optional[str]


class POWServiceClient:
    """Client for external POW service API."""

    async def get_sentinel_token(
        self,
        access_token: Optional[str] = None,
        session_token: Optional[str] = None,
        proxy_url: Optional[str] = None,
        device_type: str = "ios",
    ) -> Optional[SentinelResult]:
        """Get sentinel token from external POW service.

        Args:
            access_token: Sora access token (optional).
            session_token: Sora session token (optional).
            proxy_url: Proxy URL for upstream solver (optional).
            device_type: Device type hint for upstream solver.

        Returns:
            SentinelResult or None on failure.
        """
        server_url = config.pow_service_server_url
        api_key = config.pow_service_api_key
        request_proxy = config.pow_service_proxy_url if config.pow_service_proxy_enabled else None

        if not server_url or not api_key:
            debug_logger.log_error(
                error_message="POW service not configured: missing server_url or api_key",
                status_code=0,
                response_text="Configuration error",
                source="POWServiceClient"
            )
            return None

        api_url = f"{server_url.rstrip('/')}/api/v1/sora/sentinel-token"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        payload = {"device_type": device_type}
        if access_token:
            payload["access_token"] = access_token
        if session_token:
            payload["session_token"] = session_token
        if proxy_url:
            payload["proxy_url"] = proxy_url

        def _mask(token_value: Optional[str]) -> str:
            if not token_value:
                return "none"
            if len(token_value) <= 10:
                return "***"
            return f"{token_value[:6]}...{token_value[-4:]}"

        debug_logger.log_info(
            f"[POW Service] POST {api_url} access_token={_mask(access_token)} proxy_url={proxy_url or 'none'}"
        )

        try:
            async with AsyncSession(impersonate="chrome131") as session:
                response = await session.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    proxy=request_proxy,
                    timeout=30,
                )

                if response.status_code != 200:
                    debug_logger.log_error(
                        error_message=f"POW service request failed: {response.status_code}",
                        status_code=response.status_code,
                        response_text=response.text,
                        source="POWServiceClient",
                    )
                    return None

                data = response.json()
                token = data.get("sentinel_token")
                device_id = data.get("device_id")
                user_agent = data.get("user_agent")
                cookie_header = data.get("cookie_header")

                if not token:
                    debug_logger.log_error(
                        error_message="POW service returned empty token",
                        status_code=response.status_code,
                        response_text=response.text,
                        source="POWServiceClient"
                    )
                    return None

                debug_logger.log_info(
                    f"[POW Service] sentinel_token len={len(token)} device_id={device_id} "
                    f"ua={bool(user_agent)} cookie_header={bool(cookie_header)}"
                )
                return SentinelResult(
                    sentinel_token=token,
                    device_id=device_id,
                    user_agent=user_agent,
                    cookie_header=cookie_header,
                )

        except Exception as e:
            debug_logger.log_error(
                error_message=f"POW service request exception: {str(e)}",
                status_code=0,
                response_text=str(e),
                source="POWServiceClient"
            )
            return None


pow_service_client = POWServiceClient()
