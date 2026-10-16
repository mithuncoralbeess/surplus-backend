"""
Rule-Based Natural Language Query Parser for Typesense Search.
Zero-cost, ultra-fast deterministic parser that extracts domain intent,
geographic location, multi-currency price constraints, brand, condition,
and bulk wholesale lot intent from conversational buyer queries without external LLMs.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from .typesense_service import to_usd, RATES_TO_USD

# Common conversational stop words to strip
STOP_WORDS = {
    "show", "me", "find", "get", "look", "looking", "for", "i", "need", "want", "can", "you",
    "please", "give", "display", "search", "list", "all", "any", "some", "a", "an", "the",
    "with", "without", "having", "available", "located", "where", "which", "are", "is",
    "that", "under", "below", "less", "than", "above", "over", "more", "price", "priced",
    "budget", "cost", "costing", "in", "at", "from", "between", "to"
}

# Known enterprise & surplus brands
KNOWN_BRANDS = [
    "dell", "hp", "hewlett packard", "cisco", "lenovo", "apple", "ibm", "intel", "amd",
    "asus", "acer", "samsung", "lg", "sony", "siemens", "schneider", "schneider electric",
    "abb", "rockwell", "honeywell", "bosch", "danfoss", "grundfos", "cat", "caterpillar",
    "komatsu", "yamaha", "honda", "toyota", "mitsubishi", "omron", "fanuc", "fluke", "kuka",
    "dewalt", "makita", "3m", "flowserve"
]

# Known geographic locations (GCC, India, Global Hubs)
KNOWN_LOCATIONS = [
    # Qatar
    "qatar", "doha", "ras laffan", "al wakrah", "al khor", "mesaieed",
    # UAE
    "uae", "dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah", "fujairah",
    "jebel ali", "al quoz", "kizad", "jafza", "mussafah",
    # Saudi Arabia
    "saudi arabia", "saudi", "ksa", "riyadh", "jeddah", "dammam", "khobar", "jubail",
    # Other GCC
    "bahrain", "manama", "oman", "muscat", "sohar", "kuwait", "kuwait city",
    # India
    "india", "maharashtra", "mumbai", "pune", "delhi", "bengaluru", "bangalore", "karnataka",
    "hyderabad", "telangana", "chennai", "tamil nadu", "gujarat", "ahmedabad", "surat",
    "kolkata", "west bengal",
    # Global Hubs
    "usa", "united states", "california", "texas", "new york", "uk", "london", "singapore", "germany", "europe"
]

# Words that should never be mistaken for locations
NON_LOCATION_WORDS = {
    "bulk", "wholesale", "lot", "lots", "pallet", "pallets", "stock", "surplus",
    "case", "cases", "pack", "packs", "box", "boxes", "container", "containers",
    "advance", "demand", "cash", "store", "total", "units", "pieces", "pcs",
    "order", "sale", "auction", "rfq", "deal", "discount", "qty", "quantity",
    "parts", "spares", "goods", "items", "tshirt", "tshirts", "clothing", "wear"
}

# Regex patterns indicating buyer wants wholesale surplus lots / bulk buying
BULK_LOT_PHRASES = [
    r'\bin\s+bulk\b', r'\bbulk\b', r'\bwholesale\s+lots?\b', r'\bwholesale\b',
    r'\bin\s+lots?\b', r'\blots?\b', r'\bpallets?\b', r'\bmanifest\b',
    r'\bcontainer\s+loads?\b', r'\bbulk\s+quantity\b', r'\blarge\s+quantity\b'
]

# Category and domain mapping
DOMAIN_CATEGORY_KEYWORDS = {
    "ICT": [
        "server", "servers", "rackmount", "switch", "switches", "networking", "router",
        "routers", "workstation", "workstations", "laptop", "laptops", "datacenter", "ict"
    ],
    "Electricals": [
        "cable", "cables", "wire", "wires", "breaker", "breakers", "switchgear",
        "transformer", "panel", "lighting", "motor", "motors"
    ],
    "Industrial Machinery & Equipment": [
        "pump", "pumps", "compressor", "compressors", "generator", "generators",
        "valve", "valves", "flange", "flanges", "machinery", "hydraulic"
    ],
    "Apparel, Footwear & Accessories": [
        "tshirt", "tshirts", "clothing", "garment", "garments", "apparel", "wear",
        "uniform", "uniforms", "textile", "textiles"
    ],
    "Safety & PPE": [
        "safety", "ppe", "helmet", "helmets", "respirator", "respirators", "mask", "goggle"
    ],
}


class TypesenseQueryParser:
    """
    Parses conversational user query into:
    - cleaned_query: cleaned string for Typesense prefix and typo-tolerant search
    - is_lot: bool or None (True if bulk/lot intent detected)
    - currency: detected currency code (USD, AED, SAR, QAR, INR, EUR, GBP)
    - min_price: raw minimum price
    - max_price: raw maximum price
    - min_price_usd: normalized min price in USD
    - max_price_usd: normalized max price in USD
    - location: geographic filter string
    - brand: matched brand name
    - condition: condition string
    - category: inferred catalog category
    """

    @classmethod
    def parse(cls, query: str) -> Dict[str, Any]:
        raw_query = (query or "").strip()
        q_lower = raw_query.lower()

        parsed: Dict[str, Any] = {
            "original_query": raw_query,
            "cleaned_query": raw_query,
            "is_lot": None,
            "currency": None,
            "min_price": None,
            "max_price": None,
            "min_price_usd": None,
            "max_price_usd": None,
            "location": None,
            "brand": None,
            "condition": None,
            "category": None,
            "has_warranty": None,
            "has_filters": False,
        }

        if not raw_query:
            return parsed

        # 1. Detect Bulk / Wholesale Lot Intent
        for bp in BULK_LOT_PHRASES:
            if re.search(bp, q_lower):
                parsed["is_lot"] = True
                parsed["has_filters"] = True
                break

        # 2. Extract Currency Code
        if "$" in q_lower or re.search(r'\busd\b', q_lower):
            parsed["currency"] = "USD"
        elif "₹" in q_lower or re.search(r'\b(?:inr|rs|rupee|rupees)\b', q_lower):
            parsed["currency"] = "INR"
        elif re.search(r'\b(?:aed|dirham|dirhams)\b', q_lower):
            parsed["currency"] = "AED"
        elif re.search(r'\b(?:sar|riyal|riyals)\b', q_lower):
            parsed["currency"] = "SAR"
        elif re.search(r'\b(?:qar)\b', q_lower):
            parsed["currency"] = "QAR"
        elif "€" in q_lower or re.search(r'\b(?:eur|euro|euros)\b', q_lower):
            parsed["currency"] = "EUR"
        elif "£" in q_lower or re.search(r'\b(?:gbp|pound|pounds)\b', q_lower):
            parsed["currency"] = "GBP"

        # 3. Extract Price Range: 'between X and Y'
        range_match = re.search(
            r'(?:between|from)\s*(?:[$₹€£]|usd|inr|aed|sar|qar|eur|gbp|rs\.?)?\s*([\d,]+(?:\.\d+)?)\s*(?:and|to|-)\s*(?:[$₹€£]|usd|inr|aed|sar|qar|eur|gbp|rs\.?)?\s*([\d,]+(?:\.\d+)?)',
            q_lower
        )
        if range_match:
            try:
                parsed["min_price"] = float(range_match.group(1).replace(",", ""))
                parsed["max_price"] = float(range_match.group(2).replace(",", ""))
                parsed["has_filters"] = True
            except ValueError:
                pass

        # Max Price: 'under 500', 'below 1000', 'less than 200'
        if parsed["max_price"] is None:
            max_price_match = re.search(
                r'(?:under|below|less\s+than|max|maximum|up\s+to|within|budget\s+of)\s*(?:[$₹€£]|usd|inr|aed|sar|qar|eur|gbp|rs\.?)?\s*([\d,]+(?:\.\d+)?)',
                q_lower
            )
            if max_price_match:
                try:
                    parsed["max_price"] = float(max_price_match.group(1).replace(",", ""))
                    parsed["has_filters"] = True
                except ValueError:
                    pass

        # Min Price: 'above 200', 'over 100', 'min 500'
        if parsed["min_price"] is None:
            min_price_match = re.search(
                r'(?:above|over|more\s+than|min|minimum|starting\s+from|greater\s+than)\s*(?:[$₹€£]|usd|inr|aed|sar|qar|eur|gbp|rs\.?)?\s*([\d,]+(?:\.\d+)?)',
                q_lower
            )
            if min_price_match:
                try:
                    parsed["min_price"] = float(min_price_match.group(1).replace(",", ""))
                    parsed["has_filters"] = True
                except ValueError:
                    pass

        # Standalone price: '$500'
        if parsed["max_price"] is None and parsed["min_price"] is None:
            standalone_price = re.search(r'[$₹€£]\s*([\d,]+(?:\.\d+)?)', q_lower)
            if standalone_price:
                try:
                    parsed["max_price"] = float(standalone_price.group(1).replace(",", ""))
                    parsed["has_filters"] = True
                except ValueError:
                    pass

        # Normalize extracted prices to USD
        curr = parsed["currency"] or "USD"
        if parsed["min_price"] is not None:
            parsed["min_price_usd"] = to_usd(parsed["min_price"], curr)
        if parsed["max_price"] is not None:
            parsed["max_price_usd"] = to_usd(parsed["max_price"], curr)

        # 4. Extract Location
        for loc in KNOWN_LOCATIONS:
            if re.search(r'\b' + re.escape(loc) + r'\b', q_lower):
                parsed["location"] = loc.title()
                parsed["has_filters"] = True
                break

        if not parsed["location"]:
            loc_match = re.search(
                r'(?:available\s+in|located\s+in|in|from|at)\s+([A-Za-z]{3,20})(?:\s+(?:under|with|below|for|having)|$)',
                q_lower
            )
            if loc_match:
                cand = loc_match.group(1).strip().lower()
                if cand not in STOP_WORDS and cand not in NON_LOCATION_WORDS and len(cand) > 3:
                    parsed["location"] = cand.title()
                    parsed["has_filters"] = True

        # 5. Extract Brand
        for b in KNOWN_BRANDS:
            if re.search(r'\b' + re.escape(b) + r'\b', q_lower):
                parsed["brand"] = b.upper() if len(b) <= 3 else b.title()
                parsed["has_filters"] = True
                break

        # 6. Extract Condition
        if "brand new" in q_lower or "factory new" in q_lower:
            parsed["condition"] = "Brand New"
            parsed["has_filters"] = True
        elif "surplus" in q_lower:
            parsed["condition"] = "Surplus"
        elif "refurbished" in q_lower:
            parsed["condition"] = "Refurbished"
            parsed["has_filters"] = True
        elif "used" in q_lower or "second hand" in q_lower:
            parsed["condition"] = "Used"
            parsed["has_filters"] = True

        # 7. Extract Warranty
        if re.search(r'\b(?:with\s+warranty|has\s+warranty|under\s+warranty|warranty\s+included)\b', q_lower):
            parsed["has_warranty"] = True
            parsed["has_filters"] = True

        # 8. Infer Category
        for cat_name, kw_list in DOMAIN_CATEGORY_KEYWORDS.items():
            for kw in kw_list:
                if re.search(r'\b' + re.escape(kw) + r'\b', q_lower):
                    parsed["category"] = cat_name
                    break
            if parsed["category"]:
                break

        # 9. Clean Query Terms
        cleaned = q_lower
        # Strip price patterns
        cleaned = re.sub(
            r'(?:between|from)?\s*(?:[$₹€£]|usd|inr|aed|sar|qar|eur|gbp|rs\.?)?\s*[\d,]+(?:\.\d+)?\s*(?:and|to|-)\s*(?:[$₹€£]|usd|inr|aed|sar|qar|eur|gbp|rs\.?)?\s*[\d,]+(?:\.\d+)?',
            ' ', cleaned
        )
        cleaned = re.sub(
            r'(?:under|below|less\s+than|max|maximum|up\s+to|within|budget\s+of|above|over|more\s+than|min|starting\s+from)\s*(?:[$₹€£]|usd|inr|aed|sar|qar|eur|gbp|rs\.?)?\s*[\d,]+(?:\.\d+)?',
            ' ', cleaned
        )
        cleaned = re.sub(r'[$₹€£]\s*[\d,]+(?:\.\d+)?', ' ', cleaned)
        # Strip location
        if parsed["location"]:
            cleaned = re.sub(r'(?:available\s+in|located\s+in|in|from|at)?\s*' + re.escape(parsed["location"].lower()), ' ', cleaned)
        # Strip bulk phrases
        for bp in BULK_LOT_PHRASES:
            cleaned = re.sub(bp, ' ', cleaned)
        # Strip warranty phrases
        cleaned = re.sub(r'\b(?:with|has|under|no|without)?\s*warranty(?:\s+included)?\b', ' ', cleaned)

        # Extract tokens and discard pure stop words
        tokens = [t for t in re.findall(r'[a-zA-Z0-9]+', cleaned) if t not in STOP_WORDS and len(t) > 1]
        parsed["cleaned_query"] = " ".join(tokens) if tokens else raw_query

        return parsed
