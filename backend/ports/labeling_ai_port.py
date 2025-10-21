from abc import ABC, abstractmethod
from typing import Dict, List


class ILabelingAI(ABC):
    """Port for using an AI to generate human-friendly labels for form fields."""

    @abstractmethod
    async def generate_display_names(
        self, field_names: List[str], pdf_context: str
    ) -> Dict[str, str]:
        """
        Generates human-friendly display names for a list of technical field names.

        Args:
            field_names: A list of raw field names from the PDF.
            pdf_context: Text content from the PDF to provide context.

        Returns:
            A dictionary mapping raw field names to generated display names.
        """
        pass
