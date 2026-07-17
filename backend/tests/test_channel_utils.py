from app.utils.channel_utils import (
    channel_from_session,
    is_whatsapp_session,
    is_instagram_session,
    is_web_session,
    phone_from_session,
    session_prefixes_for_role,
)


def test_channel_from_session():
    assert channel_from_session("wa_5492944112233") == "whatsapp"
    assert channel_from_session("ig_1234567890") == "instagram"
    assert channel_from_session("web-abc-123") == "web"
    assert channel_from_session("550e8400-e29b-41d4-a716-446655440000") == "web"
    assert channel_from_session("owner_5492944112233") == "whatsapp"
    assert channel_from_session("") == "web"
    assert channel_from_session(None) == "web"


def test_is_whatsapp_session():
    assert is_whatsapp_session("wa_5492944112233") is True
    assert is_whatsapp_session("ig_123") is False
    assert is_whatsapp_session("web-123") is False


def test_is_instagram_session():
    assert is_instagram_session("ig_123") is True
    assert is_instagram_session("wa_123") is False


def test_is_web_session():
    assert is_web_session("web-123") is True
    assert is_web_session("wa_123") is False
    assert is_web_session("ig_123") is False


def test_phone_from_session():
    assert phone_from_session("wa_5492944112233") == "+5492944112233"
    assert phone_from_session("ig_123") is None
    assert phone_from_session("web-123") is None


def test_session_prefixes_for_role():
    assert session_prefixes_for_role("management") == ["owner_"]
    assert session_prefixes_for_role("staff") == ["staff_"]
    assert "ig_" in session_prefixes_for_role("guest")
    assert "wa_" in session_prefixes_for_role("guest")
