"""Street-name normalisation shared by the index builder and the street lookup."""
import re

# Abbreviations written for the road type at the end of a street name.
_SUFFIXES = {"rd": "road", "ln": "lane", "st": "street", "str": "street", "ave": "avenue", "hwy": "highway",
             "mrg": "marg", "cr": "cross", "crs": "cross"}


def norm_street(name):
    """'5th Main Rd.' -> '5th main road'; 'HITEC City Rd' -> 'hitec city road'."""
    words = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).split()
    if words and words[-1] in _SUFFIXES:
        words[-1] = _SUFFIXES[words[-1]]
    return " ".join(words)
