import torch
import pymupdf4llm
import logging
from pathlib import Path
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class PDFExtractor:
    def __init__(self, use_gpu: bool = True):
        """ 
        Initializes the PDF extraction engines.

        Marker/PdfConverter is heavy; we only construct it lazily when
        precision_extract() is called.

        :param use_gpu: If True, attempts to use CUDA. Falls back to CPU if unavailable.
        """
        if use_gpu and torch.cuda.is_available():
            self.device = "cuda"
            logging.info("GPU detected and will be used for PDF extraction.")
        elif use_gpu and not torch.cuda.is_available():
            logging.warning(
                "GPU requested but not available. Falling back to CPU. "
                "Install PyTorch with CUDA support for GPU acceleration."
            )
            self.device = "cpu"
        else:
            self.device = "cpu"
            logging.info("Using CPU for PDF extraction (GPU disabled).")

        logging.info(f"Initializing PDFExtractor on: {self.device.upper()}")

        self.config_dict = {
            "use_llm": False,
            "batch_multiplier": 2,  # Adjust if you have more VRAM
            "ocr_engine": "surya",
            "paged_output": True,
        }

        self.model_dict = None
        self.config_parser = ConfigParser(self.config_dict)
        self.converter = None  # Lazy init

    def _ensure_marker_initialized(self):
        """Lazily initialize Marker PdfConverter to avoid stalling fast mode."""
        if self.converter is not None:
            return

        self.model_dict = create_model_dict(device=self.device)
        self.converter = PdfConverter(
            artifact_dict=self.model_dict,
            config=self.config_parser.generate_config_dict(),
        )

    def fast_extract(self, path: str) -> Optional[str]:
        """Fast extraction using PyMuPDF4LLM."""
        path_obj = Path(path)
        logging.info(f"Reading {path_obj.name} via PyMuPDF4LLM")

        try:
            content = pymupdf4llm.to_markdown(doc=path, write_images=False)
            if not isinstance(content, str):
                content = str(content)

            output_dir = Path("outputs")
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"{path_obj.stem}_fast.md"
            output_file.write_text(content, encoding="utf-8")
            return content
        except Exception as e:
            logging.error(f"Fast extraction failed: {e}")
            return None

    def precision_extract(self, path: str) -> Optional[str]:
        """High-accuracy extraction using Marker."""
        self._ensure_marker_initialized()

        path_obj = Path(path)
        logging.info(f"Converting {path_obj.name} via Marker (GPU: {self.device.upper()})")

        try:
            rendered = self.converter(path)
            content = rendered.markdown

            output_dir = Path("outputs")
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"{path_obj.stem}_marker.md"
            output_file.write_text(content, encoding="utf-8")

            logging.info(f"Extracted {len(content)} characters")
            return content
        except torch.cuda.OutOfMemoryError:
            logging.critical(
                "GPU Out of Memory! Try reducing batch_multiplier or using CPU."
            )
            return None
        except Exception as e:
            logging.error(f"Marker extraction failed: {e}")
            return None

