"""IM Attachment Editor package."""
from .core import Attachment, CAB_DEFAULT, ImDocument, parse_attachments, rebuild_im, selfcheck

__all__ = [
    "Attachment",
    "CAB_DEFAULT",
    "ImDocument",
    "parse_attachments",
    "rebuild_im",
    "selfcheck",
]
