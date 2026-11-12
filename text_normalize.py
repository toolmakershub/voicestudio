"""
Text clean-up before speech synthesis.

- Detects the Indian language from the script (Tamil, Devanagari, Telugu, ...).
- Spells out numbers, decimals, currency (₹ / Rs), percentages, times and
  dates in that language (via indic-numtowords, MIT).
- Applies the user's pronunciation dictionary (e.g. "YouTube" -> "யூடியூப்").
"""
import re

# Unicode script blocks -> language code used by indic_numtowords
SCRIPTS = [
    (0x0B80, 0x0BFF, "ta"), (0x0900, 0x097F, "hi"), (0x0C00, 0x0C7F, "te"),
    (0x0C80, 0x0CFF, "kn"), (0x0D00, 0x0D7F, "ml"), (0x0980, 0x09FF, "bn"),
    (0x0A80, 0x0AFF, "gu"), (0x0A00, 0x0A7F, "pa"), (0x0B00, 0x0B7F, "or"),
]

LANG_NAMES = {"ta": "Tamil", "hi": "Hindi", "te": "Telugu", "kn": "Kannada",
              "ml": "Malayalam", "bn": "Bengali", "gu": "Gujarati", "pa": "Punjabi",
              "or": "Odia", "mr": "Marathi", "as": "Assamese"}

# Words for "point" (decimal), "rupees" and "percent"
WORDS = {
    "ta": ("புள்ளி", "ரூபாய்", "சதவீதம்"),
    "hi": ("दशमलव", "रुपये", "प्रतिशत"),
    "mr": ("दशांश", "रुपये", "टक्के"),
    "te": ("దశాంశం", "రూపాయలు", "శాతం"),
    "kn": ("ದಶಮಾಂಶ", "ರೂಪಾಯಿ", "ಶೇಕಡಾ"),
    "ml": ("ദശാംശം", "രൂപ", "ശതമാനം"),
    "bn": ("দশমিক", "টাকা", "শতাংশ"),
    "as": ("দশমিক", "টকা", "শতাংশ"),
    "gu": ("દશાંશ", "રૂપિયા", "ટકા"),
    "pa": ("ਦਸ਼ਮਲਵ", "ਰੁਪਏ", "ਪ੍ਰਤੀਸ਼ਤ"),
    "or": ("ଦଶମିକ", "ଟଙ୍କା", "ପ୍ରତିଶତ"),
}

ZERO_WIDTH = re.compile("[​‌‍﻿]")


def detect_lang(text):
    counts = {}
    for ch in text:
        o = ord(ch)
        for lo, hi, code in SCRIPTS:
            if lo <= o <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    return max(counts, key=counts.get) if counts else None


def _n2w(n, lang):
    from indic_numtowords import num2words
    return ZERO_WIDTH.sub("", num2words(n, lang=lang)).strip()


def number_words(s, lang):
    """'1,50,000' / '3.14' / '007' -> words in `lang`."""
    s = s.replace(",", "")
    whole, _, frac = s.partition(".")
    if len(whole) > 9:   # library limit: read very long numbers digit by digit
        words = " ".join(_n2w(int(d), lang) for d in whole)
    else:
        words = _n2w(int(whole or "0"), lang)
    if frac:
        point = WORDS.get(lang, WORDS["hi"])[0]
        words += f" {point} " + " ".join(_n2w(int(d), lang) for d in frac)
    return words


NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"


def normalize_numbers(text, lang):
    point, rupee, percent = WORDS.get(lang, WORDS["hi"])
    nw = lambda m: number_words(m, lang)  # noqa: E731
    # ₹1,500 / Rs. 1500 / INR 1500 / 1500 rupees
    text = re.sub(rf"(?:₹|\bRs\.?|\bINR)\s*({NUM})", lambda m: f"{nw(m.group(1))} {rupee}", text)
    # 25% / 12.5 %
    text = re.sub(rf"({NUM})\s*%", lambda m: f"{nw(m.group(1))} {percent}", text)
    # times 10:30 and dates 12/11/2026 or 12-11-2026: read each part
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: f"{nw(m.group(1))} {nw(m.group(2))}", text)
    text = re.sub(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b",
                  lambda m: " ".join(nw(g) for g in m.groups()), text)
    # any remaining number
    text = re.sub(NUM, lambda m: nw(m.group(0)), text)
    return text


def apply_dictionary(text, entries):
    """entries: [(term, replacement)] — whole-word, case-insensitive."""
    for term, repl in sorted(entries, key=lambda e: -len(e[0])):
        if not term.strip():
            continue
        pat = re.escape(term.strip())
        # \b only works next to word characters; use look-arounds for safety
        text = re.sub(rf"(?<![\w]){pat}(?![\w])", repl, text, flags=re.IGNORECASE)
    return text


def prepare(text, engine, dictionary=(), lang=None):
    """Return (spoken_text, detected_lang)."""
    if engine != "indic":   # English engine can't read Indian scripts: skip those entries
        dictionary = [(t, r) for t, r in dictionary if not detect_lang(r)]
    text = apply_dictionary(text, dictionary)
    if engine == "indic":
        lang = lang or detect_lang(text)
        if lang:
            text = normalize_numbers(text, lang)
    return re.sub(r"[ \t]+", " ", text).strip(), lang
