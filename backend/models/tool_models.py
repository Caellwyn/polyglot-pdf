from typing import Dict, Any
from pydantic import BaseModel, Field


class UpdateFormFieldsTool(BaseModel):
    """
    A tool call model for updating form fields.
    The AI is expected to return a JSON object where keys are the human-friendly
    display names of the fields and values are the data to be filled in.
    """

    updates: Dict[str, Any] = Field(
        ...,
        description="A dictionary of field updates, keyed by their display name.",
        example={"Full Name": "Jane Doe", "Date of Birth": "1990-01-02"},
    )


class GetFormStatusTool(BaseModel):
    """
    A tool call model for requesting the current status of the form.
    This tool takes no parameters.
    """

    pass
