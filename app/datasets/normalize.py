"""Name normalisation shared by every dataset (districts, crops)."""
from __future__ import annotations
import re

def _key(s: str) -> str:
    s = re.sub(r"[*]+$", "", str(s)).strip().lower()
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

STATE_KEY = "tamil nadu"

# spelling variants -> key of the official spelling used in the CSVs
_DISTRICT_ALIASES = {
    "kanchipuram": "kancheepuram", "nilgiris": "the nilgiris", "trichy": "tiruchirappalli", "tiruchirapalli": "tiruchirappalli",
    "tuticorin": "thoothukudi", "villupuram": "viluppuram", "kanyakumari": "kanniyakumari", "tirupattur": "tirupathur",
    "thiruvallur": "tiruvallur", "thiruvarur": "tiruvarur", "thanjavur": "thanjavur", "tirunelveli": "tirunelveli", "coimbatore": "coimbatore",
}
_CROP_ALIASES = {
    "paddy": "rice", "sorghum": "jowar", "pearl millet": "bajra", "finger millet": "ragi", "redgram": "red gram",
    "tur": "red gram", "arhar": "red gram", "moong": "green gram", "greengram": "green gram", "urad": "black gram",
    "blackgram": "black gram", "gram": "bengal gram", "chickpea": "bengal gram", "sesamum": "gingelly", "sesame": "gingelly",
    "til": "gingelly", "cassava": "tapioca", "lady s finger": "lady s finger", "okra": "lady s finger", "ladyfinger": "lady s finger",
    "mustard": "rapeseed mustard", "rapeseed": "rapeseed mustard", "lentil masur": "lentil", "masur": "lentil", "sunflower seed": "sunflower", "soybean yellow": "soybean", "soyabean": "soybean", "tur arhar": "red gram", "tur": "red gram", "coconut copra": "coconut", "rapeseed mustard": "rapeseed mustard", "chilli": "chillies", "chili": "chillies",
}

def district_key(name: str) -> str:
    k = _key(name)
    if k.startswith("tamil nadu"):
        return STATE_KEY
    return _DISTRICT_ALIASES.get(k, k)

def crop_key(name: str) -> str:
    k = _key(name)
    return _CROP_ALIASES.get(k, k)
