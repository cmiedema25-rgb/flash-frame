"""FlashFrame — image ↔ camera-flash / screen-blink optical transfer."""

__version__ = "0.1.0"

from .decode import decode_signal_to_image, decode_video_to_image, mae_images
from .encode import encode_image_to_timeline, prepare_image
from .simulate import simulate_timeline

__all__ = [
    "__version__",
    "encode_image_to_timeline",
    "prepare_image",
    "simulate_timeline",
    "decode_signal_to_image",
    "decode_video_to_image",
    "mae_images",
]
