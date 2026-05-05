import torch
import pymupdf4llm
import logging
from pathlib import Path
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PDFExtractor:
    def __init__(self, use_gpu: bool = True):
        """
        Initializes the PDF extraction engines.
        :param use_gpu: If True, attempts to use CUDA. Falls back to CPU if unavailable.
        """
        if use_gpu and torch.cuda.is_available():
            self.device = "cuda"
            logging.info("GPU detected and will be used for PDF extraction.")
        elif use_gpu and not torch.cuda.is_available():
            logging.warning("GPU requested but not available. Falling back to CPU. Install PyTorch with CUDA support for GPU acceleration.")
            self.device = "cpu"
        else:
            self.device = "cpu"
            logging.info("Using CPU for PDF extraction (GPU disabled).")
        
        logging.info(f"Initializing PDFExtractor on: {self.device.upper()}")
        self.config_dict = {
            "use_llm": False, 
            "batch_multiplier": 2,     # Adjust to 4 if you have >8GB VRAM
            "ocr_engine": "surya",
            "paged_output": True
        }
        
        self.model_dict = create_model_dict(device=self.device)
        self.config_parser = ConfigParser(self.config_dict)
        
        self.converter = PdfConverter(
            artifact_dict=self.model_dict,
            config=self.config_parser.generate_config_dict()
        )

    def fast_extract(self, path: str) -> Optional[str]:
        """
        Fastest extraction using PyMuPDF4LLM. 
        Best for text-heavy PDFs without complex math/equations.
        """
        path_obj = Path(path)
        logging.info(f"Reading {path_obj.name} via PyMuPDF4LLM")
        
        try:
            content = pymupdf4llm.to_markdown(doc=path, write_images=False)
            
            # Ensure output is a clean string
            if not isinstance(content, str):
                content = str(content)

            OUTPUT_DIR = Path("outputs")
            OUTPUT_DIR.mkdir(exist_ok=True)
            output_file = OUTPUT_DIR / f"{path_obj.stem}_fast.md"
            output_file.write_text(content, encoding="utf-8")
            
            return content
        except Exception as e:
            logging.error(f"Fast extraction failed: {e}")
            return None

    def precision_extract(self, path: str) -> Optional[str]:
        """
        High-accuracy extraction using Marker.
        Best for Engineering/Science PDFs with equations, tables, and complex layouts.
        """
        path_obj = Path(path)
        logging.info(f"Converting {path_obj.name} via Marker (GPU: {self.device.upper()})")
        
        try:
            # Run the conversion
            rendered = self.converter(path)
            content = rendered.markdown
            
            # Save the result
            OUTPUT_DIR = Path("outputs")
            OUTPUT_DIR.mkdir(exist_ok=True)
            output_file = OUTPUT_DIR / f"{path_obj.stem}_marker.md"
            output_file.write_text(content, encoding="utf-8")
            
            logging.info(f"Extracted {len(content)} characters")
            return content

        except torch.cuda.OutOfMemoryError:
            logging.critical("GPU Out of Memory! Try reducing batch_multiplier or using CPU.")
            return None
        except Exception as e:
            logging.error(f"Marker extraction failed: {e}")
            return None