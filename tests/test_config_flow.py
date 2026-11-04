"""Tests for the Pura config flow."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

from pypura import PuraApiException, PuraAuthenticationError
import pytest

from custom_components.pura.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

USER_INPUT = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "password"}


@pytest.fixture
def mock_login() -> Generator[MagicMock]:
    """Mock the Pura client used to log in."""
    with patch("custom_components.pura.config_flow.Pura", autospec=True) as pura_cls:
        client = pura_cls.return_value
        client.get_tokens.return_value = {"id_token": "id-token"}
        yield client


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PuraAuthenticationError("Rejected"), "invalid_auth"),
        (PuraApiException("Connection failed"), "cannot_connect"),
        (ValueError("Unexpected"), "unknown"),
    ],
)
async def test_login_errors(
    hass: HomeAssistant, mock_login: MagicMock, error: Exception, expected: str
) -> None:
    """Test a failed login shows its error, and the form can be submitted again."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    mock_login.authenticate.side_effect = error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    mock_login.authenticate.side_effect = None
    with patch("custom_components.pura.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == USER_INPUT[CONF_USERNAME]
