"""OCR-based soft verification that an uploaded ID or utility bill resembles
a real, recognized document format - reads the actual text on the page and
checks it against keyword patterns for known issuers, rather than trusting
the file blindly (magic-byte checks in routers/auth.py only confirm it's a
real image/PDF, not that it depicts the right kind of document) or trying to
pixel-match it against a fixed reference photo (which would fail on any real
photo taken at a different angle/lighting/crop than the sample).

This is NOT a hard gate. A blurry photo, an odd angle, or a genuinely valid
document type/issuer we don't have a keyword list for would all OCR poorly
or not match - rejecting registration outright over that would lock out real
applicants. Instead this produces a confidence signal (matched / not matched
/ unavailable) that the HOA/Super Admin sees during manual review, same
person who already looks at every document today.

Requires the Tesseract OCR engine installed separately (a system binary, not
just a pip package - see README). Without it, verification is skipped
entirely: every document comes back unavailable/unflagged rather than
failing closed.
"""

import difflib
import io
import logging
import os

logger = logging.getLogger("tit4tat.document_verification")

TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

AVAILABLE = False
try:
    import pytesseract
    from PIL import Image, ImageOps

    if os.path.exists(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        AVAILABLE = True
    else:
        logger.warning("Tesseract not found at %s - document format verification disabled.", TESSERACT_CMD)
except ImportError:
    logger.warning("pytesseract/Pillow not installed - document format verification disabled.")

# Single words matched individually with typo tolerance (majority=1.0, so
# the one word must itself pass the fuzzy threshold); multi-word phrases
# only need a majority of their words to fuzzy-match, since OCR on a real
# photographed/scanned document routinely mangles a word or two.
ID_KEYWORDS = ["ELECTOR", "REGISTRATION", "IDENTIFICATION"]
BILL_KEYWORD_GROUPS = {
    "Digicel": ["DIGICEL"],
    "FLOW": ["FLOW"],
    "JPS": ["JPSCO", "JAMAICA PUBLIC SERVICE"],
    "National Water Commission": ["NATIONAL WATER COMMISSION", "NWC"],
}


def _extract_text(content: bytes) -> str:
    image = Image.open(io.BytesIO(content)).convert("L")
    # Upscale small images - Tesseract needs roughly 300 DPI-equivalent text
    # height to read reliably, and phone photos/compressed uploads are often
    # much smaller than that.
    scale = max(1, 1600 // max(image.size))
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    image = ImageOps.autocontrast(image)
    return pytesseract.image_to_string(image).upper()


def _word_matches_text(word: str, text: str, text_words: list[str], *, fuzzy_threshold: float = 0.8) -> bool:
    """True if a single word is found in OCR'd text - exact substring always
    counts (handles it being glued to other text, e.g. "JPSCO" inside
    "WWW.JPSCO.COM"); a fuzzy per-word match only counts for words over 5
    characters. Short words (<=5 chars, e.g. "FLOW", "LI", "JPS") get no
    fuzzy tolerance at all - they can fuzzy-match all sorts of unrelated
    words by pure coincidence (e.g. "LOW" resembles "FLOW" at 86%
    similarity), which would false-positive on completely unrelated text.
    """
    if word in text:
        return True
    if len(word) <= 5:
        return False
    return any(difflib.SequenceMatcher(None, word, w).ratio() >= fuzzy_threshold for w in text_words)


def _matches_keyword(text: str, text_words: list[str], keyword: str) -> bool:
    """True if `keyword` (a single word or multi-word phrase) is found in the
    OCR'd text, tolerating real OCR noise without being so lenient that
    short/common substrings match by pure chance.

    - Single word: see _word_matches_text.
    - Multi-word phrase (e.g. "NATIONAL WATER COMMISSION"): a majority of
      its words need a fuzzy match against some word in the text. No single
      random word can trigger this alone, so a more lenient per-word
      threshold is safe here even though it wouldn't be for a lone word.
    """
    keyword_words = keyword.split()
    if len(keyword_words) == 1:
        return _word_matches_text(keyword_words[0], text, text_words, fuzzy_threshold=0.8)

    matched = sum(
        1 for kw in keyword_words
        if any(difflib.SequenceMatcher(None, kw, w).ratio() >= 0.6 for w in text_words)
    )
    return matched / len(keyword_words) >= 0.5


def check_id_document(content: bytes) -> bool | None:
    """True if it reads like a real ID, False if not, None if OCR isn't
    available (verification skipped, not a failure)."""
    if not AVAILABLE:
        return None
    try:
        text = _extract_text(content)
    except Exception:
        logger.exception("OCR failed while checking an ID document")
        return None
    words = text.split()
    matched = sum(1 for kw in ID_KEYWORDS if _matches_keyword(text, words, kw))
    return matched >= 2


def check_utility_bill(content: bytes) -> tuple[bool, str | None] | None:
    """(matched, issuer name if matched) if OCR is available, else None."""
    if not AVAILABLE:
        return None
    try:
        text = _extract_text(content)
    except Exception:
        logger.exception("OCR failed while checking a utility bill")
        return None
    words = text.split()
    for issuer, phrases in BILL_KEYWORD_GROUPS.items():
        if any(_matches_keyword(text, words, p) for p in phrases):
            return True, issuer
    return False, None


def _name_word_matches(word: str, text_words: list[str]) -> bool:
    """Matches a single name word against an ID card's OCR'd words, more
    leniently than _word_matches_text's brand-keyword logic: a name is
    checked against one ID card's relatively small amount of text rather
    than a whole page, so a fuzzy match on a short word is much less likely
    to be a coincidence here. Also checks adjacent-word joins, since OCR
    sometimes splits one word into two around a watermark or fold (e.g.
    "JOHN" misread as "J" / "OHN")."""
    joined_pairs = [a + b for a, b in zip(text_words, text_words[1:])]
    candidates = text_words + joined_pairs
    if word in candidates:
        return True
    return any(difflib.SequenceMatcher(None, word, c).ratio() >= 0.75 for c in candidates)


def check_name_matches_id(id_content: bytes, typed_name: str) -> bool | None:
    """True if every word of the typed name can be found somewhere in the
    ID's OCR'd text - order-independent, since ID cards commonly show
    Surname/First Name/Middle Name as separate fields rather than in
    whatever order someone types their full name. Bare initials (single
    letters) are ignored, since those are essentially impossible to
    confidently locate in noisy OCR output either way.

    None if OCR isn't available or the typed name has no usable words -
    verification skipped, not a mismatch."""
    if not AVAILABLE:
        return None
    name_words = [w for w in typed_name.upper().split() if len(w) > 1]
    if not name_words:
        return None
    try:
        text = _extract_text(id_content)
    except Exception:
        logger.exception("OCR failed while checking a name against an ID")
        return None
    text_words = text.split()
    return all(_name_word_matches(w, text_words) for w in name_words)
