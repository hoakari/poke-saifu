"""Core image processing and OCR pipeline for Poke-Saifu.

Handles color masking, ruby (furigana) removal, ROI cropping, and EasyOCR integration.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import cv2
import numpy as np

# 16:9 Screen standard relative coordinates (ymin, xmin, ymax, xmax)
# 1. Main message box (lower bottom)
DEFAULT_ROI_MAIN: Tuple[float, float, float, float] = (0.68, 0.18, 0.88, 0.58)

# 2. Ability / Item popups (left: player, right: opponent)
DEFAULT_ROI_POPUP_LEFT: Tuple[float, float, float, float] = (0.33, 0.01, 0.47, 0.28)
DEFAULT_ROI_POPUP_RIGHT: Tuple[float, float, float, float] = (0.33, 0.72, 0.47, 0.99)

# 3. Team preview 6on6 screen detection ROIs
DEFAULT_ROI_PREVIEW_CENTER: Tuple[float, float, float, float] = (0.16, 0.35, 0.36, 0.60)
DEFAULT_ROI_PREVIEW_OPPONENT: Tuple[float, float, float, float] = (0.07, 0.72, 0.15, 0.90)


def save_image_unicode(file_path: Union[str, Path], img_bgr: np.ndarray) -> bool:
    """Save an image supporting full Unicode / Japanese file paths on Windows."""
    if img_bgr is None or img_bgr.size == 0:
        return False
    path_obj = Path(file_path)
    ext = path_obj.suffix.lower() or ".png"
    success, encoded = cv2.imencode(ext, img_bgr)
    if success:
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        with open(path_obj, "wb") as f:
            f.write(encoded.tobytes())
        return True
    return False


def read_image_unicode(file_path: Union[str, Path]) -> Optional[np.ndarray]:
    """Read an image supporting full Unicode / Japanese file paths on Windows."""
    path_obj = Path(file_path)
    if not path_obj.exists():
        return None
    try:
        with open(path_obj, "rb") as f:
            file_bytes = np.frombuffer(f.read(), dtype=np.uint8)
        return cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    except Exception:
        return None


def crop_by_ratio(
    frame: np.ndarray,
    ratio: Tuple[float, float, float, float],
) -> np.ndarray:
    """Crop an image frame using normalized relative coordinates (ymin, xmin, ymax, xmax)."""
    h, w = frame.shape[:2]
    ymin = max(0, min(h, int(h * ratio[0])))
    xmin = max(0, min(w, int(w * ratio[1])))
    ymax = max(0, min(h, int(h * ratio[2])))
    xmax = max(0, min(w, int(w * ratio[3])))
    return frame[ymin:ymax, xmin:xmax]


def preprocess_and_remove_ruby(
    img_bgr: np.ndarray,
    scale_factor: float = 2.0,
    ruby_height_threshold: int = 15,
) -> np.ndarray:
    """Extract white and yellow text while filtering out ruby characters and background noise."""
    if img_bgr is None or img_bgr.size == 0:
        return np.zeros((10, 10), dtype=np.uint8)

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # 1. White text mask (low saturation, high brightness)
    lower_white = np.array([0, 0, 175], dtype=np.uint8)
    upper_white = np.array([180, 55, 255], dtype=np.uint8)
    mask_white = cv2.inRange(hsv, lower_white, upper_white)

    # 2. Yellow text mask (critical hit / super effective emphasis text)
    lower_yellow = np.array([18, 90, 140], dtype=np.uint8)
    upper_yellow = np.array([42, 255, 255], dtype=np.uint8)
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

    # Combined mask
    mask = cv2.bitwise_or(mask_white, mask_yellow)

    # Fast resize (INTER_LINEAR is much faster than LANCZOS with identical OCR accuracy)
    resized = cv2.resize(
        mask,
        (0, 0),
        fx=scale_factor,
        fy=scale_factor,
        interpolation=cv2.INTER_LINEAR,
    )

    # 3. Geometric ruby (furigana) removal
    contours, _ = cv2.findContours(
        resized, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    clean_mask = resized.copy()
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Small noise or ruby text (significantly smaller height than main body text)
        if h < ruby_height_threshold or w < 3:
            cv2.drawContours(clean_mask, [cnt], -1, 0, -1)

    return clean_mask


def is_likely_text_mask(
    binary_mask: np.ndarray,
    min_char_count: int = 2,
    min_pixels: int = 150,
) -> bool:
    """Ultra-fast geometric verification to filter out background light noise before running expensive OCR."""
    if binary_mask is None or binary_mask.size == 0:
        return False

    total_pixels = cv2.countNonZero(binary_mask)
    if total_pixels < min_pixels:
        return False

    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_letter_count = 0
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Text character minimum bounding box dimensions at 2x scale
        if h >= 11 and w >= 4:
            valid_letter_count += 1
            if valid_letter_count >= min_char_count:
                return True
    return False


class OCRProcessor:
    """Lazy-loading wrapper for EasyOCR reader with performance optimizations."""

    def __init__(self, languages: Optional[list] = None, gpu: bool = True):
        self.languages = languages or ["ja", "en"]
        self.gpu = gpu
        self._reader: Any = None

    @property
    def reader(self) -> Any:
        if self._reader is None:
            try:
                import easyocr
                import torch
                import os
                # Optimize PyTorch CPU threads
                threads = max(1, (os.cpu_count() or 4) - 1)
                torch.set_num_threads(threads)
            except ImportError as e:
                raise ImportError(
                    "easyocr がインストールされていません。'pip install easyocr' を実行してください。"
                ) from e
            except Exception:
                pass

            # Fall back to CPU if GPU is not available, with quantization for fast inference
            try:
                self._reader = easyocr.Reader(
                    self.languages,
                    gpu=self.gpu,
                    quantize=True,
                )
            except Exception:
                try:
                    self._reader = easyocr.Reader(self.languages, gpu=False, quantize=True)
                except Exception:
                    self._reader = easyocr.Reader(self.languages, gpu=False)
        return self._reader

    def extract_text_from_mask(
        self,
        binary_mask: np.ndarray,
    ) -> Dict[str, Any]:
        """Perform OCR on an already preprocessed binary mask."""
        if binary_mask is None or binary_mask.size == 0 or cv2.countNonZero(binary_mask) < 30:
            return {"text": "", "confidence": 0.0}

        try:
            results = self.reader.readtext(
                binary_mask,
                detail=1,
                paragraph=False,
                batch_size=4,
                text_threshold=0.6,
                link_threshold=0.4,
                low_text=0.3,
            )
        except Exception:
            return {"text": "", "confidence": 0.0}

        if not results:
            return {"text": "", "confidence": 0.0}

        texts = []
        confs = []
        for res in results:
            if len(res) >= 3:
                text_part = res[1].strip()
                if text_part:
                    texts.append(text_part)
                    confs.append(float(res[2]))

        full_text = " ".join(texts).strip()
        avg_conf = sum(confs) / len(confs) if confs else 0.0

        return {
            "text": full_text,
            "confidence": round(avg_conf, 2),
        }

    def extract_text(
        self,
        crop_bgr: np.ndarray,
        min_nonzero_pixels: int = 50,
    ) -> Dict[str, Any]:
        """Process crop, perform OCR and return detected text with average confidence score."""
        if crop_bgr is None or crop_bgr.size == 0:
            return {"text": "", "confidence": 0.0}

        binary_mask = preprocess_and_remove_ruby(crop_bgr)
        if cv2.countNonZero(binary_mask) < min_nonzero_pixels:
            return {"text": "", "confidence": 0.0}

        return self.extract_text_from_mask(binary_mask)
