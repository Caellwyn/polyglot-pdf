import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Correctly patch the 'google.genai' module used by the adapter
@pytest.fixture
def mock_google_generative_client():
    """Mocks the google.genai.Client for labeling."""
    with patch("backend.adapters.labeling_ai_gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_model = AsyncMock()

        # Configure the client to return our mock model
        mock_client.get_async_generative_model.return_value = mock_model

        # Patch the Client constructor to return our mock client
        mock_genai.Client = MagicMock(return_value=mock_client)

        yield mock_genai, mock_model

@pytest.mark.asyncio
async def test_generate_display_names_success(mock_google_generative_client):
    """Tests successful generation of display names from valid JSON response."""
    from backend.adapters.labeling_ai_gemini import LabelingAIGemini
    mock_genai, mock_model = mock_google_generative_client
    
    # Mock the API response
    expected_response_dict = {
        "first_name": "First Name",
        "date_of_birth": "Date of Birth",
    }
    mock_response = MagicMock()
    # Simulate the API wrapping JSON in markdown
    mock_response.text = f"```json\n{json.dumps(expected_response_dict)}\n```"
    mock_model.generate_content_async.return_value = mock_response

    adapter = LabelingAIGemini(api_key="test_key")
    field_names = ["first_name", "date_of_birth"]
    pdf_context = "This is a form for new patients."

    result = await adapter.generate_display_names(field_names, pdf_context)

    assert result == expected_response_dict
    # The adapter constructs genai.Client(api_key=...) during init; assert constructor called
    mock_genai.Client.assert_called_once_with(api_key="test_key")
    mock_model.generate_content_async.assert_called_once()

@pytest.mark.asyncio
async def test_generate_display_names_fallback_on_bad_json(mock_google_generative_client):
    """Tests the fallback mechanism when the API returns non-JSON text."""
    from backend.adapters.labeling_ai_gemini import LabelingAIGemini
    _, mock_model = mock_google_generative_client

    # Mock a non-JSON API response
    mock_response = MagicMock()
    mock_response.text = "I am sorry, I cannot fulfill this request."
    mock_model.generate_content_async.return_value = mock_response

    adapter = LabelingAIGemini(api_key="test_key")
    field_names = ["first_name", "date_of_birth"]
    pdf_context = "Some context."

    result = await adapter.generate_display_names(field_names, pdf_context)

    # Expect the fallback behavior (title casing and replacing underscores)
    expected_fallback = {
        "first_name": "First Name",
        "date_of_birth": "Date Of Birth", # Note the title casing
    }
    assert result == expected_fallback

@pytest.mark.asyncio
async def test_generate_display_names_fallback_on_error(mock_google_generative_client):
    """Tests the fallback mechanism when the API response object is malformed."""
    from backend.adapters.labeling_ai_gemini import LabelingAIGemini
    _, mock_model = mock_google_generative_client

    # Mock a response that doesn't have the .text attribute
    mock_response = MagicMock()
    del mock_response.text
    mock_model.generate_content_async.return_value = mock_response

    adapter = LabelingAIGemini(api_key="test_key")
    field_names = ["complex_field_name"]
    
    result = await adapter.generate_display_names(field_names, "")

    assert result == {"complex_field_name": "Complex Field Name"}
