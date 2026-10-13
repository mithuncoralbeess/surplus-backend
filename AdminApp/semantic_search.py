import re
import math
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from django.db.models import Q
from django.conf import settings
from pgvector.django import CosineDistance

from .models import Product, ProductEmbedding, Lot, LotEmbedding, MainCategory, SubCategory

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 768

# Common stop words to strip from natural language query to focus on core semantic concepts
STOP_WORDS = {
    "show", "me", "find", "get", "look", "looking", "for", "i", "need", "want", "can", "you",
    "please", "give", "display", "search", "list", "all", "any", "some", "a", "an", "the",
    "with", "without", "having", "available", "located", "where", "which", "are", "is",
    "that", "under", "below", "less", "than", "above", "over", "more", "price", "priced",
    "budget", "cost", "costing", "in", "at", "from"
}

# Known enterprise & surplus brands to recognize
KNOWN_BRANDS = [
    "dell", "hp", "hewlett packard", "cisco", "lenovo", "apple", "ibm", "intel", "amd",
    "asus", "acer", "samsung", "lg", "sony", "siemens", "schneider", "abb", "rockwell",
    "honeywell", "bosch", "danfoss", "grundfos", "cat", "caterpillar", "komatsu", "yamaha",
    "honda", "toyota", "mitsubishi", "omron", "fanuc", "fluke", "kuka"
]

# Known locations & states (GCC, India, US, global hubs)
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

# Non-location words that must never be mistaken for locations (e.g., 'in bulk', 'in lots', 'in wholesale')
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

# Domain conceptual mappings for natural language B2B queries
DOMAIN_CONCEPTS = {
    "spare_parts": {
        "triggers": [
            "spare part", "spare parts", "spares", "spare", "replacement part", "replacement parts",
            "mro", "maintenance part", "maintenance parts", "machinery parts", "equipment parts",
            "industrial spares", "auto parts", "automobile spares", "hardware spares", "components"
        ],
        "categories": [
            "Oil & Gas Equipment & MRO",
            "Industrial Machinery & Equipment",
            "Automotive",
            "Construction, Hardware & MRO",
            "Electrical & Lighting",
        ],
        "subcategories": [
            "Valves, flanges, pipes, fittings",
            "Auto parts",
            "Tyres and batteries",
            "Motors and gearboxes",
            "Compressors and pumps",
            "Tools and workshop equipment",
            "Material-handling equipment",
            "Generators and backup-power equipment",
            "Control panels and sensors",
            "Cables, Wires & Accessories",
            "Hand tools",
            "Power tools"
        ],
        "keywords": [
            "valve", "valves", "pump", "pumps", "motor", "motors", "caliper", "brake", "filter", "filters",
            "seal", "seals", "gasket", "gaskets", "bearing", "bearings", "reducer", "gearbox", "breaker",
            "switch", "cable", "flange", "flanges", "fitting", "fittings", "compressor", "generator", "jack",
            "tool", "hose", "pipe", "spares", "parts", "component", "assembly"
        ],
        "label": "Spare Parts & MRO Components",
        "reason_template": "Classified as industrial spare parts & replacement components ({category})"
    },
    "apparel_clothing": {
        "triggers": [
            "tshirt", "tshirts", "t-shirt", "t-shirts", "tee", "tees", "shirt", "shirts",
            "boys tshirt", "boys t-shirt", "boys clothing", "kids clothing", "children clothing",
            "garment", "garments", "apparel", "clothing", "wear", "uniform", "coverall", "coveralls",
            "vest", "vests", "pants", "trousers", "jacket", "hoodie"
        ],
        "categories": [
            "Apparel, Footwear & Accessories"
        ],
        "subcategories": [
            "Clothing",
            "Uniforms and workwear",
            "Fashion accessories",
            "Textiles and fabrics"
        ],
        "keywords": [
            "t-shirt", "tshirt", "t-shirts", "tshirts", "tee", "tees", "shirt", "shirts", "cotton",
            "clothing", "apparel", "garment", "garments", "crew neck", "polo", "wear", "coveralls",
            "vest", "vests", "fabric", "textile", "boys", "kids", "children", "mens", "womens"
        ],
        "label": "Apparel, Garments & Clothing",
        "reason_template": "Matches apparel, garments & clothing catalog ({category})"
    },
    "safety_ppe": {
        "triggers": [
            "safety", "ppe", "safety equipment", "safety gear", "protective equipment",
            "helmet", "helmets", "respirator", "respirators", "face shield", "safety glasses"
        ],
        "categories": [
            "Oil & Gas Equipment & MRO",
            "Construction, Hardware & MRO"
        ],
        "subcategories": [
            "PPE and safety equipment"
        ],
        "keywords": [
            "safety", "ppe", "helmet", "helmets", "respirator", "respirators", "n95", "mask", "shield", "goggle"
        ],
        "label": "Safety Equipment & PPE",
        "reason_template": "Matches personal protective equipment & safety catalog"
    },
    "it_datacenter": {
        "triggers": [
            "server", "servers", "rackmount", "switch", "switches", "networking", "router", "routers",
            "workstation", "workstations", "laptop", "laptops", "datacenter", "ict", "it equipment"
        ],
        "categories": [
            "Electronics & ICT",
            "Consumer Electronics"
        ],
        "subcategories": [
            "Servers and networking equipment",
            "Computers and laptops",
            "Servers & Workstations"
        ],
        "keywords": [
            "server", "rack", "switch", "router", "cisco", "dell", "poweredge", "workstation", "thinkpad"
        ],
        "label": "IT & Datacenter Equipment",
        "reason_template": "Matches IT, networking & datacenter surplus equipment"
    }
}


class NaturalLanguageQueryParser:
    """
    Parses conversational user queries into structured constraints and semantic search terms.
    Example: 'Show me 2U rackmount servers under $500 available in Qatar'
    -> semantic_terms: '2U rackmount servers'
    -> max_price: 500.0
    -> currency: 'USD'
    -> location: 'Qatar'
    -> is_bulk: False
    """

    @classmethod
    def parse(cls, query: str) -> Dict[str, Any]:
        raw_query = query.strip()
        q_lower = raw_query.lower()

        extracted: Dict[str, Any] = {
            "original_query": raw_query,
            "semantic_keywords": "",
            "max_price": None,
            "min_price": None,
            "currency": None,
            "location": None,
            "has_warranty": None,
            "brand": None,
            "condition": None,
            "is_bulk": False,
            "detected_concepts": [],
        }

        # 1. Detect Bulk / Lot Buying Intent ('bulk means lot')
        for bp in BULK_LOT_PHRASES:
            if re.search(bp, q_lower):
                extracted["is_bulk"] = True
                break

        # 2. Detect Domain Concepts (e.g. 'spare parts', 'boys tshirt')
        detected = []
        for concept_id, concept_info in DOMAIN_CONCEPTS.items():
            for trig in concept_info["triggers"]:
                if re.search(r'\b' + re.escape(trig) + r'\b', q_lower):
                    detected.append(concept_id)
                    break
        extracted["detected_concepts"] = detected

        # 3. Extract Price Constraints & Currency
        if "$" in q_lower or "usd" in q_lower:
            extracted["currency"] = "USD"
        elif "₹" in q_lower or "inr" in q_lower or "rs" in q_lower or "rupee" in q_lower:
            extracted["currency"] = "INR"
        elif "aed" in q_lower or "dirham" in q_lower:
            extracted["currency"] = "AED"
        elif "€" in q_lower or "eur" in q_lower or "euro" in q_lower:
            extracted["currency"] = "EUR"
        elif "£" in q_lower or "gbp" in q_lower or "pound" in q_lower:
            extracted["currency"] = "GBP"

        max_price_match = re.search(
            r'(?:under|below|less\s+than|max|maximum|up\s+to|within|budget\s+of)\s*(?:[$₹€£]|usd|inr|aed|eur|rs\.?)?\s*([\d,]+(?:\.\d+)?)',
            q_lower
        )
        if max_price_match:
            try:
                extracted["max_price"] = float(max_price_match.group(1).replace(",", ""))
            except ValueError:
                pass

        min_price_match = re.search(
            r'(?:above|over|more\s+than|min|minimum|starting\s+from|greater\s+than)\s*(?:[$₹€£]|usd|inr|aed|eur|rs\.?)?\s*([\d,]+(?:\.\d+)?)',
            q_lower
        )
        if min_price_match:
            try:
                extracted["min_price"] = float(min_price_match.group(1).replace(",", ""))
            except ValueError:
                pass

        if extracted["max_price"] is None and extracted["min_price"] is None:
            standalone_price = re.search(r'[$₹€£]\s*([\d,]+(?:\.\d+)?)', q_lower)
            if standalone_price:
                try:
                    extracted["max_price"] = float(standalone_price.group(1).replace(",", ""))
                except ValueError:
                    pass

        # 4. Extract Location (Must match known locations or valid geographic names, NEVER bulk/wholesale words)
        for loc in KNOWN_LOCATIONS:
            if re.search(r'\b' + re.escape(loc) + r'\b', q_lower):
                extracted["location"] = loc.title()
                break

        if not extracted["location"]:
            loc_match = re.search(
                r'(?:available\s+in|located\s+in|in|from|at)\s+([A-Za-z]{3,20})(?:\s+(?:under|with|below|for|having)|$)',
                q_lower
            )
            if loc_match:
                cand = loc_match.group(1).strip().lower()
                if cand not in STOP_WORDS and cand not in NON_LOCATION_WORDS and len(cand) > 3:
                    extracted["location"] = cand.title()

        # 5. Extract Warranty Constraint
        if re.search(r'\b(?:with\s+warranty|has\s+warranty|under\s+warranty|warranty\s+included)\b', q_lower):
            extracted["has_warranty"] = True
        elif re.search(r'\b(?:no\s+warranty|without\s+warranty)\b', q_lower):
            extracted["has_warranty"] = False

        # 6. Extract Brand
        for b in KNOWN_BRANDS:
            if re.search(r'\b' + re.escape(b) + r'\b', q_lower):
                extracted["brand"] = b.upper() if len(b) <= 3 else b.title()
                break

        # 7. Extract Condition
        if "brand new" in q_lower or "factory new" in q_lower:
            extracted["condition"] = "Brand New"
        elif "surplus" in q_lower:
            extracted["condition"] = "Surplus"
        elif "refurbished" in q_lower:
            extracted["condition"] = "Refurbished"
        elif "used" in q_lower or "second hand" in q_lower:
            extracted["condition"] = "Used"

        # 8. Extract Semantic Keywords for Vector Search
        cleaned = q_lower
        # Remove price phrases
        cleaned = re.sub(r'(?:under|below|less\s+than|max|maximum|up\s+to|within|budget\s+of|above|over|more\s+than|min|starting\s+from)\s*(?:[$₹€£]|usd|inr|aed|eur|rs\.?)?\s*[\d,]+(?:\.\d+)?', ' ', cleaned)
        cleaned = re.sub(r'[$₹€£]\s*[\d,]+(?:\.\d+)?', ' ', cleaned)
        # Remove location phrase
        if extracted["location"]:
            cleaned = re.sub(r'(?:available\s+in|located\s+in|in|from|at)?\s*' + re.escape(extracted["location"].lower()), ' ', cleaned)
        # Remove bulk phrases ('in bulk', 'bulk', 'wholesale lots', etc.)
        for bp in BULK_LOT_PHRASES:
            cleaned = re.sub(bp, ' ', cleaned)
        # Remove warranty phrase
        cleaned = re.sub(r'\b(?:with|has|under|no|without)?\s*warranty(?:\s+included)?\b', ' ', cleaned)
        # Remove conversational stopwords
        tokens = [t for t in re.findall(r'[a-zA-Z0-9]+', cleaned) if t not in STOP_WORDS and len(t) > 1]
        
        extracted["semantic_keywords"] = " ".join(tokens) if tokens else raw_query
        return extracted


class SemanticEmbedder:
    """
    Generates 768-dimensional normalized dense vector embeddings for semantic search.
    Supports:
    1. Google Gemini Embeddings (text-embedding-004) if GEMINI_API_KEY is available.
    2. OpenAI Embeddings (text-embedding-3-small, dim=768) if OPENAI_API_KEY is available.
    3. Built-in Deterministic Domain Trigram Semantic Embedder (Zero-Config / Local Fallback).
    """

    @classmethod
    def get_embedding(cls, text: str) -> List[float]:
        text = (text or "").strip()
        if not text:
            return [0.0] * EMBEDDING_DIMENSION

        # 1. Try Gemini API
        gemini_key = getattr(settings, "GEMINI_API_KEY", None) or os_env_get("GEMINI_API_KEY")
        if gemini_key:
            try:
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={gemini_key}"
                resp = requests.post(url, json={"content": {"parts": [{"text": text[:2000]}]}}, timeout=3)
                if resp.status_code == 200:
                    values = resp.json().get("embedding", {}).get("values")
                    if values and len(values) == EMBEDDING_DIMENSION:
                        return cls._normalize(values)
            except Exception as e:
                logger.warning(f"Gemini embedding API call failed: {e}")

        # 2. Try OpenAI API
        openai_key = getattr(settings, "OPENAI_API_KEY", None) or os_env_get("OPENAI_API_KEY")
        if openai_key:
            try:
                import requests
                url = "https://api.openai.com/v1/embeddings"
                headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
                resp = requests.post(
                    url,
                    headers=headers,
                    json={"input": text[:2000], "model": "text-embedding-3-small", "dimensions": EMBEDDING_DIMENSION},
                    timeout=3
                )
                if resp.status_code == 200:
                    data = resp.json()
                    values = data["data"][0]["embedding"]
                    if values and len(values) == EMBEDDING_DIMENSION:
                        return cls._normalize(values)
            except Exception as e:
                logger.warning(f"OpenAI embedding API call failed: {e}")

        # 3. High-Quality Built-In Domain Semantic Embedder (Local Fallback)
        return cls._compute_domain_dense_embedding(text)

    @classmethod
    def _normalize(cls, vec: List[float]) -> List[float]:
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.tolist()

    @classmethod
    def _compute_domain_dense_embedding(cls, text: str) -> List[float]:
        """
        Deterministic, subword-aware, domain-clustered 768-dimensional dense vector.
        Maps keywords, semantic character trigrams, and word stems into continuous
        semantic feature dimensions with cosine normalization.
        """
        vec = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
        words = re.findall(r'[a-zA-Z0-9]+', text.lower())
        if not words:
            return vec.tolist()

        # Domain category clusters mapped to specific vector partitions
        cluster_offsets = {
            "server": 0, "rackmount": 10, "cpu": 20, "xeon": 30, "ram": 40, "storage": 50,
            "pump": 100, "valve": 110, "motor": 120, "hydraulic": 130, "compressor": 140,
            "laptop": 200, "desktop": 210, "mobile": 220, "tablet": 230, "monitor": 240,
            "camera": 250, "optical": 255, "lens": 260, "video": 265, "cinema": 270, "audio": 275,
            "industrial": 300, "machinery": 310, "generator": 320, "transformer": 330,
            "solar": 350, "inverter": 360, "photovoltaic": 370,
            "fitness": 380, "treadmill": 390,
            "electrical": 400, "circuit": 410, "breaker": 420, "cable": 430, "switch": 440,
            "packaging": 450, "strapping": 460,
            "vehicle": 470, "tyre": 480, "brake": 490, "forklift": 495,
            "warranty": 500, "certified": 510, "surplus": 520, "new": 530, "refurbished": 540,
            "tool": 550, "drill": 560, "cleaner": 570, "valve": 580,
            "spare": 150, "part": 155, "mro": 160, "bearing": 165, "gasket": 170, "fitting": 175,
            "tshirt": 670, "shirt": 675, "apparel": 680, "clothing": 685, "garment": 690, "cotton": 695,
            "qatar": 700, "doha": 705, "bulk": 720, "wholesale": 730,
            "dell": 600, "hp": 610, "cisco": 620, "siemens": 630, "schneider": 640, "sony": 650, "toyota": 660
        }

        for word in words:
            # Word hashing across primary partition
            h = int(hashlib.sha256(word.encode('utf-8')).hexdigest(), 16)
            idx = h % EMBEDDING_DIMENSION
            weight = 2.5 if word not in STOP_WORDS else 0.2
            vec[idx] += weight

            # Check domain clusters
            for cluster_term, offset in cluster_offsets.items():
                if cluster_term in word:
                    vec[(offset + (h % 30)) % EMBEDDING_DIMENSION] += 3.5

            # Subword character 3-grams (subtle smoothing for typos / variations)
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    trigram = word[i:i+3]
                    th = int(hashlib.md5(trigram.encode('utf-8')).hexdigest(), 16)
                    vec[th % EMBEDDING_DIMENSION] += 0.08

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


def os_env_get(key: str) -> Optional[str]:
    import os
    val = os.getenv(key)
    return val.strip() if val else None


def generate_product_semantic_text(product: Product) -> str:
    """
    Assembles a comprehensive semantic description document for a product
    containing all contextual attributes, categories, specifications, condition, and location.
    """
    parts = []
    if product.product_name:
        parts.append(f"Product: {product.product_name}")
    if product.product_id:
        parts.append(f"Listing ID: {product.product_id}")
    if product.brand_name:
        parts.append(f"Brand: {product.brand_name}")
    if product.model_no:
        parts.append(f"Model Number: {product.model_no}")
    if product.category:
        parts.append(f"Category: {product.category.name}")
    if product.subcategory:
        parts.append(f"Subcategory: {product.subcategory.name}")
    if product.inventory_location:
        parts.append(f"Inventory Location: {product.inventory_location}")
    if product.liquidating_price:
        parts.append(f"Price: {product.currency or 'USD'} {product.liquidating_price}")
    if product.quantity:
        parts.append(f"Available Quantity: {product.quantity} units")
    if product.manufacturing_country:
        parts.append(f"Country of Origin: {product.manufacturing_country}")
    if product.manufacturing_year:
        parts.append(f"Manufacturing Year: {product.manufacturing_year}")
    if product.dimensions:
        parts.append(f"Dimensions: {product.dimensions}")
    if product.warranty or product.warranty_attachment:
        parts.append("Warranty: Included with product warranty documentation")
    if product.third_party_certificate:
        parts.append("Inspection: 3rd Party Inspection Certificate Verified")
    if product.description:
        parts.append(f"Description: {product.description}")
    if product.reason_to_sell:
        parts.append(f"Reason for Sale / Surplus: {product.reason_to_sell}")

    return ". ".join(parts) + "."


def sync_product_embedding(product: Product, force: bool = False) -> Tuple[ProductEmbedding, bool]:
    """
    Creates or updates the 768-dimensional pgvector embedding for a Product.
    Skips re-embedding if content hash is unchanged unless force=True.
    """
    doc_text = generate_product_semantic_text(product)
    content_hash = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()

    emb_record, created = ProductEmbedding.objects.get_or_create(
        product=product,
        defaults={
            "embedded_text": doc_text,
            "content_hash": content_hash,
            "embedding": None,
        }
    )

    if not created and not force and emb_record.content_hash == content_hash and emb_record.embedding is not None:
        return emb_record, False

    vec = SemanticEmbedder.get_embedding(doc_text)
    emb_record.embedding = vec
    emb_record.embedded_text = doc_text
    emb_record.content_hash = content_hash
    emb_record.save(update_fields=["embedding", "embedded_text", "content_hash", "updated_at"])

    return emb_record, True


def get_lot_category_name(lot: Lot) -> str:
    """
    Extracts the primary category string from a Lot's category_allocations.
    """
    if lot.category_allocations and isinstance(lot.category_allocations, list) and len(lot.category_allocations) > 0:
        first_cat = lot.category_allocations[0]
        if isinstance(first_cat, dict):
            return first_cat.get("category_name") or first_cat.get("name") or "Wholesale Surplus Lots"
        elif isinstance(first_cat, str):
            return first_cat
    return "Wholesale Surplus Lots"


def get_lot_image_url(lot: Lot) -> str:
    """
    Extracts the first representative warehouse image URL for a Lot.
    """
    if lot.warehouse_images and isinstance(lot.warehouse_images, list) and len(lot.warehouse_images) > 0:
        first_img = str(lot.warehouse_images[0]).strip()
        if first_img:
            return first_img
    return ""


def generate_lot_semantic_text(lot: Lot) -> str:
    """
    Assembles a comprehensive semantic description document for a Lot
    containing lot title, lot number, brands, categories, manifest items, condition, and location.
    """
    parts = []
    if lot.title:
        parts.append(f"Wholesale Surplus Lot: {lot.title}")
    if lot.lot_number:
        parts.append(f"Lot Listing ID: {lot.lot_number}")
    if lot.key_brands_included:
        parts.append(f"Brands: {lot.key_brands_included}")

    cats = []
    if lot.category_allocations and isinstance(lot.category_allocations, list):
        for c in lot.category_allocations:
            if isinstance(c, dict):
                cname = c.get("category_name") or c.get("name") or ""
                if cname:
                    cats.append(cname)
            elif isinstance(c, str):
                cats.append(c)
    if cats:
        parts.append(f"Categories: {', '.join(cats)}")

    if lot.inventory_location:
        parts.append(f"Inventory Location: {lot.inventory_location}")
    if lot.ask_price_surplus_payout:
        parts.append(f"Liquidation Payout Price: {lot.currency or 'USD'} {lot.ask_price_surplus_payout}")
    if lot.total_est_retail_value_msrp:
        parts.append(f"Estimated Retail Value: {lot.currency or 'USD'} {lot.total_est_retail_value_msrp}")
    if lot.total_units_quantity:
        parts.append(f"Total Quantity: {lot.total_units_quantity} units")
    if lot.number_of_distinct_skus:
        parts.append(f"Distinct SKUs: {lot.number_of_distinct_skus}")
    if lot.condition:
        parts.append(f"Condition: {lot.condition}")
    if lot.third_party_certificate_available:
        parts.append("Inspection: 3rd Party Inspection Certificate Verified")
    if lot.description:
        parts.append(f"Description: {lot.description}")

    prod_names = list(lot.products.values_list("product_name", flat=True)[:40])
    if prod_names:
        parts.append(f"Manifest Products: {', '.join(prod_names)}")

    return ". ".join(parts) + "."


def sync_lot_embedding(lot: Lot, force: bool = False) -> Tuple[Optional[LotEmbedding], bool]:
    """
    Creates or updates the 768-dimensional pgvector embedding for a Lot.
    Skips re-embedding if content hash is unchanged unless force=True.
    """
    doc_text = generate_lot_semantic_text(lot)
    content_hash = hashlib.sha256(doc_text.encode("utf-8")).hexdigest()

    emb_record, created = LotEmbedding.objects.get_or_create(
        lot=lot,
        defaults={
            "embedded_text": doc_text,
            "content_hash": content_hash,
            "embedding": None,
        }
    )

    if not created and not force and emb_record.content_hash == content_hash and emb_record.embedding is not None:
        return emb_record, False

    vec = SemanticEmbedder.get_embedding(doc_text)
    emb_record.embedding = vec
    emb_record.embedded_text = doc_text
    emb_record.content_hash = content_hash
    emb_record.save(update_fields=["embedding", "embedded_text", "content_hash", "updated_at"])

    return emb_record, True


def stem_token(t: str) -> str:
    """
    Lightweight rule-based stemmer for search token normalization (plurals and common suffixes).
    """
    t = t.lower().strip()
    if len(t) > 3 and t.endswith('ies'):
        return t[:-3] + 'y'
    if len(t) > 3 and t.endswith('es') and not t.endswith('ses'):
        return t[:-2]
    if len(t) > 3 and t.endswith('s') and not t.endswith('ss'):
        return t[:-1]
    return t


def extract_word_set(text: Optional[str]) -> Tuple[set, set]:
    """
    Extracts lowercase words and their stemmed forms with word-boundary preservation.
    """
    words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', text or "") if len(w) > 0]
    stemmed = [stem_token(w) for w in words]
    return set(words), set(stemmed)


def semantic_product_search(
    query_text: str,
    limit: int = 12,
    threshold: Optional[float] = None,
    entity_type: str = "all"
) -> Dict[str, Any]:
    """
    Executes a Conversational Semantic & Hybrid Search across Products and Lots using pgvector in Neon DB.
    Combines:
    1. Natural Language Intent & Constraint Extraction (price, location, warranty, brand)
    2. High-precision Lexical Matching (exact phrase, multi-field title/brand/category/manifest token overlap)
    3. Dense Vector Cosine Similarity via pgvector for both individual Products and wholesale Lots
    4. Dynamic Relevance Cutoff Thresholding so irrelevant items are not returned as noise.
    5. Entity filtering: entity_type="all" | "product" | "lot"
    """
    parsed = NaturalLanguageQueryParser.parse(query_text)
    search_keywords = (parsed.get("semantic_keywords") or query_text).strip()

    # Extract clean query tokens (ignoring stop words)
    raw_tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]+', search_keywords) if len(t) > 1 and t not in STOP_WORDS]
    if not raw_tokens:
        raw_tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]+', query_text) if len(t) > 1]
    stemmed_tokens = [stem_token(t) for t in raw_tokens]
    query_phrase = " ".join(raw_tokens).lower()
    num_tokens = len(raw_tokens) if raw_tokens else 1

    # Generate query vector
    query_vector = SemanticEmbedder.get_embedding(search_keywords)

    scored_candidates = []
    is_relaxed = False

    entity_norm = (entity_type or "all").strip().lower()
    include_products = entity_norm in ("all", "product", "products", "")
    include_lots = entity_norm in ("all", "lot", "lots", "")

    # ----------------------------------------------------
    # 1. SEARCH PRODUCTS
    # ----------------------------------------------------
    if include_products:
        prod_base_qs = ProductEmbedding.objects.filter(
            product__is_active=True,
            product__enquiry_status__iexact="APPROVED",
            embedding__isnull=False
        ).select_related(
            "product",
            "product__category",
            "product__subcategory",
            "product__vendor"
        ).prefetch_related("product__images")

        prod_annotated_qs = prod_base_qs.annotate(distance=CosineDistance("embedding", query_vector))
        prod_filtered_qs = prod_annotated_qs

        if parsed["max_price"] is not None:
            prod_filtered_qs = prod_filtered_qs.filter(product__liquidating_price__lte=parsed["max_price"])
        if parsed["min_price"] is not None:
            prod_filtered_qs = prod_filtered_qs.filter(product__liquidating_price__gte=parsed["min_price"])

        # Smart Location Filtering: Check if matching inventory exists in requested location
        prod_has_local_stock = False
        if parsed["location"]:
            loc_term = parsed["location"]
            loc_qs = prod_filtered_qs.filter(
                Q(product__inventory_location__icontains=loc_term) |
                Q(product__vendor__business_location__icontains=loc_term) |
                Q(product__vendor__country__icontains=loc_term)
            )
            if loc_qs.exists():
                prod_filtered_qs = loc_qs
                prod_has_local_stock = True
            else:
                is_relaxed = True

        if parsed["has_warranty"] is True:
            prod_filtered_qs = prod_filtered_qs.filter(
                Q(product__warranty__isnull=False) & ~Q(product__warranty="") |
                Q(product__warranty_attachment__isnull=False) & ~Q(product__warranty_attachment="")
            )
        if parsed["brand"]:
            prod_filtered_qs = prod_filtered_qs.filter(product__brand_name__icontains=parsed["brand"])

        prod_candidates = list(prod_filtered_qs.order_by("distance")[:75])
        if not prod_candidates:
            prod_candidates = list(prod_annotated_qs.order_by("distance")[:75])
            is_relaxed = True

        for rec in prod_candidates:
            prod = rec.product
            dist = float(rec.distance) if rec.distance is not None else 1.0

            dot_product = max(0.0, 1.0 - dist)
            vector_sim = dot_product * 100.0

            p_name = (prod.product_name or "").lower()
            p_name_words, p_name_stems = extract_word_set(prod.product_name)
            p_brand_words, p_brand_stems = extract_word_set(prod.brand_name)
            p_model_words, p_model_stems = extract_word_set(prod.model_no)
            p_cat_name = (prod.category.name or "") if prod.category else ""
            p_cat_words, p_cat_stems = extract_word_set(p_cat_name)
            p_subcat_name = (prod.subcategory.name or "") if prod.subcategory else ""
            p_subcat_words, p_subcat_stems = extract_word_set(p_subcat_name)
            p_desc_words, p_desc_stems = extract_word_set(prod.description)

            # Word-boundary matching across catalog attributes
            matched_tokens_name = set()
            matched_tokens_brand_model = set()
            matched_tokens_cat = set()
            matched_tokens_desc = set()

            for tok, stem in zip(raw_tokens, stemmed_tokens):
                if tok in p_name_words or stem in p_name_stems:
                    matched_tokens_name.add(tok)
                if tok in p_brand_words or stem in p_brand_stems or tok in p_model_words or stem in p_model_stems:
                    matched_tokens_brand_model.add(tok)
                if tok in p_cat_words or stem in p_cat_stems or tok in p_subcat_words or stem in p_subcat_stems:
                    matched_tokens_cat.add(tok)
                if tok in p_desc_words or stem in p_desc_stems:
                    matched_tokens_desc.add(tok)

            all_matched_tokens = matched_tokens_name | matched_tokens_brand_model | matched_tokens_cat | matched_tokens_desc
            name_coverage = len(matched_tokens_name) / num_tokens
            all_coverage = len(all_matched_tokens) / num_tokens

            exact_phrase_in_name = (len(query_phrase) > 2 and query_phrase in p_name)
            exact_phrase_in_subcat = (len(query_phrase) > 2 and query_phrase in p_subcat_name.lower())

            # Domain Concept Evaluation (e.g. 'spare parts' matches valves, pumps, motors, auto parts)
            prod_concept_matched = False
            prod_concept_reason = ""
            for cid in parsed.get("detected_concepts", []):
                cinfo = DOMAIN_CONCEPTS.get(cid, {})
                c_cats = cinfo.get("categories", [])
                c_subcats = cinfo.get("subcategories", [])
                c_kws = cinfo.get("keywords", [])

                in_cat = (p_cat_name in c_cats) or any(sc.lower() in p_subcat_name.lower() for sc in c_subcats)
                has_kw = any(kw in p_name_words or kw in p_brand_words or kw in p_desc_words for kw in c_kws)

                if in_cat or has_kw:
                    prod_concept_matched = True
                    prod_concept_reason = cinfo.get("reason_template", "").format(category=p_cat_name or p_subcat_name)
                    break

            reasons = []

            # Lexical & Concept Scoring (titles, categories, brands, specs, concepts)
            if exact_phrase_in_name:
                lexical_score = 98.0
                reasons.append(f"Direct match for '{query_phrase}' in product title")
            elif exact_phrase_in_subcat:
                lexical_score = 92.0
                reasons.append(f"Matches category '{p_subcat_name}' for '{query_phrase}'")
            elif name_coverage == 1.0:
                lexical_score = 94.0
                if matched_tokens_brand_model:
                    lexical_score = min(99.0, lexical_score + 4.0)
                reasons.append(f"Product title matches all query keywords ({', '.join(raw_tokens)})")
            elif all_coverage == 1.0:
                lexical_score = 88.0
                reasons.append(f"Catalog matches all terms ({', '.join(raw_tokens)}) across title, category & specs")
            elif prod_concept_matched:
                lexical_score = 88.0
                reasons.append(prod_concept_reason)
            elif name_coverage >= 0.5:
                lexical_score = 65.0 + (name_coverage * 20.0)
                reasons.append(f"Title matches {len(matched_tokens_name)}/{num_tokens} keywords")
            elif all_coverage >= 0.5:
                lexical_score = 50.0 + (all_coverage * 20.0)
                reasons.append(f"Catalog matches {len(all_matched_tokens)}/{num_tokens} terms")
            else:
                lexical_score = 0.0

            # Natural language structured constraint reasons
            if parsed["max_price"] is not None and prod.liquidating_price and prod.liquidating_price <= parsed["max_price"]:
                reasons.append(f"Price ({prod.currency or 'USD'} {prod.liquidating_price}) is within budget (max {parsed['max_price']})")
            if parsed["brand"] and prod.brand_name and parsed["brand"].lower() in prod.brand_name.lower():
                reasons.append(f"Matches requested brand: {prod.brand_name}")
            if parsed["location"]:
                if prod.inventory_location and parsed["location"].lower() in prod.inventory_location.lower():
                    reasons.append(f"Inventory located in requested location: {prod.inventory_location}")
                else:
                    reasons.append(f"Available stock in {prod.inventory_location or 'UAE'} (no local stock in {parsed['location']})")
            if parsed["has_warranty"] and (prod.warranty or prod.warranty_attachment):
                reasons.append("Includes verified warranty coverage")

            # Blend final hybrid score
            if lexical_score >= 80.0:
                final_score = min(99.0, max(lexical_score, lexical_score * 0.95 + vector_sim * 0.05))
            elif lexical_score >= 40.0:
                final_score = lexical_score * 0.75 + vector_sim * 0.25
            else:
                # Contextual vector similarity when no direct lexical keyword match
                if dist < 0.75:
                    final_score = max(30.0, min(70.0, 30.0 + (0.75 - dist) * 150.0))
                    reasons.append(f"Contextual semantic similarity match ({round(final_score)}%)")
                else:
                    final_score = 0.0

            # Bulk intent adjustment ('bulk means lot')
            if parsed.get("is_bulk"):
                if prod.quantity and prod.quantity >= 100:
                    reasons.append(f"Wholesale volume available ({prod.quantity} units) for bulk order")
                else:
                    # Slightly prioritize lots over low-quantity single products
                    final_score = max(0.0, final_score - 8.0)

            if not reasons:
                reasons.append("Ranked by contextual vector similarity")

            first_img = prod.images.first()
            img_url = first_img.url if first_img else (first_img.image_url if hasattr(first_img, 'image_url') else "")

            scored_candidates.append({
                "item_type": "product",
                "is_lot": False,
                "id": prod.id,
                "product_id": prod.product_id or f"PRO-{prod.id:05d}",
                "sku": prod.product_id or f"PRO-{prod.id:05d}",
                "lot_number": "",
                "product_name": prod.product_name,
                "title": prod.product_name,
                "category": prod.category.name if prod.category else "",
                "subcategory": prod.subcategory.name if prod.subcategory else "",
                "brand": prod.brand_name or "",
                "model_no": prod.model_no or "",
                "liquidating_price": float(prod.liquidating_price) if prod.liquidating_price else 0.0,
                "current_price": float(prod.current_price) if prod.current_price else 0.0,
                "currency": prod.currency or "USD",
                "quantity": prod.quantity or 0,
                "inventory_location": prod.inventory_location or "",
                "image": img_url,
                "has_warranty": bool(prod.warranty or prod.warranty_attachment),
                "dist": dist,
                "final_score": round(final_score, 1),
                "reasons": reasons,
                "all_coverage": all_coverage,
                "concept_match": prod_concept_matched,
            })

    # ----------------------------------------------------
    # 2. SEARCH LOTS
    # ----------------------------------------------------
    if include_lots:
        lot_base_qs = LotEmbedding.objects.filter(
            lot__is_active=True,
            lot__enquiry_status__iexact="approved",
            embedding__isnull=False
        ).select_related(
            "lot",
            "lot__vendor"
        ).prefetch_related("lot__products")

        lot_annotated_qs = lot_base_qs.annotate(distance=CosineDistance("embedding", query_vector))
        lot_filtered_qs = lot_annotated_qs

        if parsed["max_price"] is not None:
            lot_filtered_qs = lot_filtered_qs.filter(lot__ask_price_surplus_payout__lte=parsed["max_price"])
        if parsed["min_price"] is not None:
            lot_filtered_qs = lot_filtered_qs.filter(lot__ask_price_surplus_payout__gte=parsed["min_price"])

        # Smart Location Filtering for Lots
        lot_has_local_stock = False
        if parsed["location"]:
            loc_term = parsed["location"]
            loc_qs = lot_filtered_qs.filter(
                Q(lot__inventory_location__icontains=loc_term) |
                Q(lot__vendor__business_location__icontains=loc_term) |
                Q(lot__vendor__country__icontains=loc_term)
            )
            if loc_qs.exists():
                lot_filtered_qs = loc_qs
                lot_has_local_stock = True
            else:
                is_relaxed = True

        if parsed["has_warranty"] is True:
            lot_filtered_qs = lot_filtered_qs.filter(lot__third_party_certificate_available=True)
        if parsed["brand"]:
            lot_filtered_qs = lot_filtered_qs.filter(lot__key_brands_included__icontains=parsed["brand"])

        lot_candidates = list(lot_filtered_qs.order_by("distance")[:50])
        if not lot_candidates:
            lot_candidates = list(lot_annotated_qs.order_by("distance")[:50])
            is_relaxed = True

        for rec in lot_candidates:
            lot = rec.lot
            dist = float(rec.distance) if rec.distance is not None else 1.0
            dot_product = max(0.0, 1.0 - dist)
            vector_sim = dot_product * 100.0

            l_title = (lot.title or "").lower()
            l_num = (lot.lot_number or "").lower()
            l_title_words, l_title_stems = extract_word_set(lot.title)
            l_brands_words, l_brands_stems = extract_word_set(lot.key_brands_included)
            l_cat_name = get_lot_category_name(lot)
            l_cat_words, l_cat_stems = extract_word_set(l_cat_name)
            l_desc_words, l_desc_stems = extract_word_set(lot.description)

            # Check manifest products
            manifest_prods = list(lot.products.values_list("product_name", flat=True)[:40])
            manifest_text = " ".join(manifest_prods).lower()
            manifest_words, manifest_stems = extract_word_set(manifest_text)

            matched_tokens_title = set()
            matched_tokens_brand = set()
            matched_tokens_cat = set()
            matched_tokens_manifest = set()
            matched_tokens_desc = set()

            for tok, stem in zip(raw_tokens, stemmed_tokens):
                if tok in l_title_words or stem in l_title_stems:
                    matched_tokens_title.add(tok)
                if tok in l_brands_words or stem in l_brands_stems:
                    matched_tokens_brand.add(tok)
                if tok in l_cat_words or stem in l_cat_stems:
                    matched_tokens_cat.add(tok)
                if tok in manifest_words or stem in manifest_stems:
                    matched_tokens_manifest.add(tok)
                if tok in l_desc_words or stem in l_desc_stems:
                    matched_tokens_desc.add(tok)

            all_matched_tokens = matched_tokens_title | matched_tokens_brand | matched_tokens_cat | matched_tokens_manifest | matched_tokens_desc
            title_coverage = len(matched_tokens_title) / num_tokens
            all_coverage = len(all_matched_tokens) / num_tokens

            exact_phrase_in_title = (len(query_phrase) > 2 and query_phrase in l_title)

            # Domain Concept Evaluation for Lots
            lot_concept_matched = False
            lot_concept_reason = ""
            for cid in parsed.get("detected_concepts", []):
                cinfo = DOMAIN_CONCEPTS.get(cid, {})
                c_cats = cinfo.get("categories", [])
                c_kws = cinfo.get("keywords", [])

                in_cat = (l_cat_name in c_cats) or any(c.lower() in l_cat_name.lower() for c in c_cats)
                has_kw = any(kw in l_title_words or kw in l_brands_words or kw in manifest_words for kw in c_kws)

                if in_cat or has_kw:
                    lot_concept_matched = True
                    lot_concept_reason = cinfo.get("reason_template", "").format(category=l_cat_name)
                    break

            # Bulk / Lot request prioritization ('bulk means lot')
            user_wants_lots = bool(parsed.get("is_bulk")) or any(w in raw_tokens for w in ("lot", "lots", "wholesale", "bulk", "manifest", "pallet"))

            reasons = []
            if exact_phrase_in_title:
                lexical_score = 98.0
                reasons.append(f"Direct match for '{query_phrase}' in lot title")
            elif title_coverage == 1.0:
                lexical_score = 94.0
                if matched_tokens_brand:
                    lexical_score = min(99.0, lexical_score + 4.0)
                reasons.append(f"Lot title matches all query keywords ({', '.join(raw_tokens)})")
            elif matched_tokens_manifest and len(matched_tokens_manifest) == num_tokens:
                lexical_score = 92.0
                reasons.append(f"Lot manifest includes: {', '.join(manifest_prods[:2])}")
            elif all_coverage == 1.0:
                lexical_score = 88.0
                reasons.append(f"Lot matches all terms ({', '.join(raw_tokens)}) across title, brand & manifest")
            elif lot_concept_matched:
                lexical_score = 90.0
                reasons.append(lot_concept_reason)
            elif title_coverage >= 0.5:
                lexical_score = 65.0 + (title_coverage * 20.0)
                reasons.append(f"Lot title matches {len(matched_tokens_title)}/{num_tokens} keywords")
            elif all_coverage >= 0.5:
                lexical_score = 50.0 + (all_coverage * 20.0)
                reasons.append(f"Lot catalog matches {len(all_matched_tokens)}/{num_tokens} terms")
            else:
                lexical_score = 0.0

            if parsed["max_price"] is not None and lot.ask_price_surplus_payout and lot.ask_price_surplus_payout <= parsed["max_price"]:
                reasons.append(f"Price ({lot.currency or 'USD'} {lot.ask_price_surplus_payout}) is within budget (max {parsed['max_price']})")
            if parsed["brand"] and lot.key_brands_included and parsed["brand"].lower() in lot.key_brands_included.lower():
                reasons.append(f"Includes requested brand: {parsed['brand']}")
            if parsed["location"]:
                if lot.inventory_location and parsed["location"].lower() in lot.inventory_location.lower():
                    reasons.append(f"Inventory located in requested location: {lot.inventory_location}")
                else:
                    reasons.append(f"Available stock in {lot.inventory_location or 'UAE'} (no local stock in {parsed['location']})")
            if parsed["has_warranty"] and lot.third_party_certificate_available:
                reasons.append("Includes 3rd party verified inspection certificate")

            # Prioritize lots for bulk inquiries ('bulk means lot')
            if user_wants_lots and lexical_score >= 50.0:
                lexical_score = min(98.0, lexical_score + 10.0)
                reasons.append("Prioritized wholesale surplus Lot for bulk buyer request")

            if lexical_score >= 80.0:
                final_score = min(99.0, max(lexical_score, lexical_score * 0.95 + vector_sim * 0.05))
            elif lexical_score >= 40.0:
                final_score = lexical_score * 0.75 + vector_sim * 0.25
            else:
                if dist < 0.75:
                    final_score = max(30.0, min(70.0, 30.0 + (0.75 - dist) * 150.0))
                    reasons.append(f"Contextual semantic similarity match ({round(final_score)}%)")
                else:
                    final_score = 0.0

            if not reasons:
                reasons.append("Ranked by contextual vector similarity")

            # Manifest product preview (IDs strictly use 'BLK-XXXXX', never 'PRO-')
            manifest_items = []
            for lp in lot.products.all()[:15]:
                manifest_items.append({
                    "item_id": lp.product_id,
                    "product_name": lp.product_name,
                    "quantity": lp.quantity,
                    "condition": lp.condition,
                })

            scored_candidates.append({
                "item_type": "lot",
                "is_lot": True,
                "id": lot.id,
                "product_id": "",
                "sku": lot.lot_number,
                "lot_number": lot.lot_number,
                "product_name": lot.title,
                "title": lot.title,
                "category": l_cat_name,
                "subcategory": "Wholesale Surplus Lot",
                "brand": lot.key_brands_included or "Various Brands",
                "model_no": f"{lot.number_of_distinct_skus or 0} SKUs",
                "liquidating_price": float(lot.ask_price_surplus_payout) if lot.ask_price_surplus_payout else 0.0,
                "current_price": float(lot.total_est_retail_value_msrp) if lot.total_est_retail_value_msrp else 0.0,
                "currency": lot.currency or "USD",
                "quantity": lot.total_units_quantity or 1,
                "inventory_location": lot.inventory_location or "",
                "image": get_lot_image_url(lot),
                "has_warranty": bool(lot.third_party_certificate_available),
                "dist": dist,
                "final_score": round(final_score, 1),
                "reasons": reasons,
                "all_coverage": all_coverage,
                "concept_match": lot_concept_matched,
                "bulk_priority": user_wants_lots,
                "manifest_items": manifest_items,
            })

    # Sort descending by final score (and prioritize lots when user requested bulk)
    if parsed.get("is_bulk"):
        scored_candidates.sort(key=lambda x: (x.get("is_lot", False), x["final_score"]), reverse=True)
    else:
        scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)

    # Dynamic Relevance Filtering
    top_score = scored_candidates[0]["final_score"] if scored_candidates else 0.0
    min_threshold = threshold if threshold is not None else 50.0

    filtered_records = []
    for it in scored_candidates:
        score = it["final_score"]
        is_concept = it.get("concept_match", False)
        if top_score >= 70.0:
            # Strong matches exist: keep items with >= 50% keyword coverage or concept match or score >= 75
            if is_concept or (it["all_coverage"] >= 0.5 and score >= 60.0) or score >= 75.0:
                filtered_records.append(it)
        elif top_score >= min_threshold:
            # Moderate matches
            if score >= min_threshold and (is_concept or it["all_coverage"] >= 0.5 or it["dist"] < 0.70):
                filtered_records.append(it)
        # If top_score < min_threshold: nothing matches well, return empty!

    filtered_records = filtered_records[:limit]

    formatted_results = []
    for it in filtered_records:
        rec = {
            "id": it["id"],
            "product_id": it["product_id"],
            "sku": it["sku"],
            "lot_number": it["lot_number"],
            "product_name": it["product_name"],
            "title": it["title"],
            "item_type": it["item_type"],
            "is_lot": it["is_lot"],
            "category": it["category"],
            "subcategory": it["subcategory"],
            "brand": it["brand"],
            "model_no": it["model_no"],
            "liquidating_price": it["liquidating_price"],
            "current_price": it["current_price"],
            "currency": it["currency"],
            "quantity": it["quantity"],
            "inventory_location": it["inventory_location"],
            "image": it["image"],
            "has_warranty": it["has_warranty"],
            "similarity_score": it["final_score"],
            "match_reasons": it["reasons"],
        }
        if it.get("is_lot"):
            rec["manifest_items"] = it.get("manifest_items", [])
        formatted_results.append(rec)

    products_only = [it for it in formatted_results if not it.get("is_lot")]
    lots_only = [it for it in formatted_results if it.get("is_lot")]

    return {
        "success": True,
        "query": query_text,
        "parsed_intent": parsed,
        "is_relaxed": is_relaxed,
        "total_results": len(formatted_results),
        "total_products": len(products_only),
        "total_lots": len(lots_only),
        "results": formatted_results,
        "products": products_only,
        "lots": lots_only,
    }
