from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Callable, Optional, Any

class SeparationModelAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the model adapter."""
        pass

    @property
    @abstractmethod
    def supported_modes(self) -> List[str]:
        """Supported separation modes: ['two_stem', 'four_stem']."""
        pass

    @abstractmethod
    def load(self, device: Optional[str] = None) -> bool:
        """Load model weights and prepare inference pipeline."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if model is loaded and ready for inference."""
        pass

    @abstractmethod
    def separate(
        self,
        input_audio_path: Path,
        output_dir: Path,
        mode: str = "two_stem",
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, Path]:
        """
        Execute separation on input audio.
        Returns a dictionary mapping stem name to generated stem file path.
        e.g., {'vocals': Path(...), 'instrumental': Path(...)}
        """
        pass
