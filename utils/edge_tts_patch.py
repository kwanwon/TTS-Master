"""
Edge-TTS Global Patch for Microsoft 2026 Endpoint & Locale Fix
Fixes:
1. 2026-10 Microsoft 403 Forbidden shutdown of speech.platform.bing.com:
   Routes WebSocket synthesis through official Edge 155 endpoint: api.msedgeservices.com
2. SkewAdjustmentError: Failed to parse server date:
   Uses email.utils.parsedate_to_datetime to parse RFC 2616 Date header reliably across all locales.
"""

def apply_edge_tts_patch():
    try:
        import edge_tts
        import edge_tts.constants
        import edge_tts.communicate
        import edge_tts.drm
        from email.utils import parsedate_to_datetime
        from datetime import timezone as tz

        new_wss_url = (
            "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
            f"?Ocp-Apim-Subscription-Key={edge_tts.constants.TRUSTED_CLIENT_TOKEN}"
        )
        edge_tts.constants.WSS_URL = new_wss_url
        edge_tts.communicate.WSS_URL = new_wss_url

        def _safe_parse_rfc2616_date(date: str):
            try:
                parsed = parsedate_to_datetime(date)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=tz.utc)
                return parsed.timestamp()
            except Exception:
                return None

        edge_tts.drm.DRM.parse_rfc2616_date = staticmethod(_safe_parse_rfc2616_date)
        return True
    except Exception as e:
        print(f"[edge_tts_patch] Patch failed: {e}")
        return False

# 자동 실행
apply_edge_tts_patch()
