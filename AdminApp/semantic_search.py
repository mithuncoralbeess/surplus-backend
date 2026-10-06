import re
import math
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from django.db.models import Q
from django.conf import settings
from pgvector.django import CosineDistance

from .models import Product, ProductEmbedding, MainCategory, SubCategory

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

# Known locations & states (India, UAE, US, global hubs)
KNOWN_LOCATIONS = [
    "maharashtra", "mumbai", "pune", "delhi", "bengaluru", "bangalore", "karnataka",
    "hyderabad", "telangana", "chennai", "tamil nadu", "gujarat", "ahmedabad", "surat",
    "kolkata", "west bengal", "dubai", "abu dhabi", "sharjah", "uae", "california",
    "texas", "new york", "london", "singapore", "germany"
]


class NaturalLanguageQueryParser:
    """
    Parses conversational user queries into structured constraints and semantic search terms.
    Example: 'Show me 2U rackmount servers under $500 available in Maharashtra'
    -> semantic_terms: '2U rackmount servers'
    -> max_price: 500.0
    -> currency: 'USD'
    -> location: 'Maharashtra'
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
        }

        # 1. Extract Price Constraints & Currency
        # Currency detection
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

        # Max price (under $500, below 500, less than 500, max 500, up to 500)
        max_price_match = re.search(
            r'(?:under|below|less\s+than|max|maximum|up\s+to|within|budget\s+of)\s*(?:[$₹€£]|usd|inr|aed|eur|rs\.?)?\s*([\d,]+(?:\.\d+)?)',
            q_lower
        )
        if max_price_match:
            try:
                extracted["max_price"] = float(max_price_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # Min price (above $100, over 100, more than 100, min 100, starting from 100)
        min_price_match = re.search(
            r'(?:above|over|more\s+than|min|minimum|starting\s+from|greater\s+than)\s*(?:[$₹€£]|usd|inr|aed|eur|rs\.?)?\s*([\d,]+(?:\.\d+)?)',
            q_lower
        )
        if min_price_match:
            try:
                extracted["min_price"] = float(min_price_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # If no explicit "under/above" was matched, check standalone price like "$500" or "under 500"
        if extracted["max_price"] is None and extracted["min_price"] is None:
            standalone_price = re.search(r'[$₹€£]\s*([\d,]+(?:\.\d+)?)', q_lower)
            if standalone_price:
                try:
                    # Treat standalone price as upper target threshold
                    extracted["max_price"] = float(standalone_price.group(1).replace(",", ""))
                except ValueError:
                    pass

        # 2. Extract Location
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
                cand = loc_match.group(1).strip()
                if cand not in STOP_WORDS and len(cand) > 3:
                    extracted["location"] = cand.title()

        # 3. Extract Warranty Constraint
        if re.search(r'\b(?:with\s+warranty|has\s+warranty|under\s+warranty|warranty\s+included)\b', q_lower):
            extracted["has_warranty"] = True
        elif re.search(r'\b(?:no\s+warranty|without\s+warranty)\b', q_lower):
            extracted["has_warranty"] = False

        # 4. Extract Brand
        for b in KNOWN_BRANDS:
            if re.search(r'\b' + re.escape(b) + r'\b', q_lower):
                extracted["brand"] = b.upper() if len(b) <= 3 else b.title()
                break

        # 5. Extract Condition
        if "brand new" in q_lower or "factory new" in q_lower:
            extracted["condition"] = "Brand New"
        elif "surplus" in q_lower:
            extracted["condition"] = "Surplus"
        elif "refurbished" in q_lower:
            extracted["condition"] = "Refurbished"
        elif "used" in q_lower or "second hand" in q_lower:
            extracted["condition"] = "Used"

        # 6. Extract Semantic Keywords for Vector Search
        cleaned = q_lower
        # Remove price phrases
        cleaned = re.sub(r'(?:under|below|less\s+than|max|maximum|up\s+to|within|budget\s+of|above|over|more\s+than|min|starting\s+from)\s*(?:[$₹€£]|usd|inr|aed|eur|rs\.?)?\s*[\d,]+(?:\.\d+)?', ' ', cleaned)
        cleaned = re.sub(r'[$₹€£]\s*[\d,]+(?:\.\d+)?', ' ', cleaned)
        # Remove location phrase
        if extracted["location"]:
            cleaned = re.sub(r'(?:available\s+in|located\s+in|in|from|at)?\s*' + re.escape(extracted["location"].lower()), ' ', cleaned)
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
            "industrial": 300, "machinery": 310, "generator": 320, "transformer": 330,
            "electrical": 400, "circuit": 410, "breaker": 420, "cable": 430, "switch": 440,
            "warranty": 500, "certified": 510, "surplus": 520, "new": 530, "refurbished": 540,
            "dell": 600, "hp": 610, "cisco": 620, "siemens": 630, "schneider": 640
        }

        for word in words:
            # Word hashing across primary partition
            h = int(hashlib.sha256(word.encode('utf-8')).hexdigest(), 16)
            idx = h % EMBEDDING_DIMENSION
            weight = 1.8 if word not in STOP_WORDS else 0.4
            vec[idx] += weight

            # Check domain clusters
            for cluster_term, offset in cluster_offsets.items():
                if cluster_term in word:
                    vec[(offset + (h % 30)) % EMBEDDING_DIMENSION] += 2.5

            # Subword character 3-grams
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    trigram = word[i:i+3]
                    th = int(hashlib.md5(trigram.encode('utf-8')).hexdigest(), 16)
                    vec[th % EMBEDDING_DIMENSION] += 0.35

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


def semantic_product_search(
    query_text: str,
    limit: int = 12,
    threshold: Optional[float] = None
) -> Dict[str, Any]:
    """
    Executes a Conversational Semantic Search using pgvector in Neon DB.
    Parses natural language queries (e.g. 'Show me 2U rackmount servers under $500 in Maharashtra'),
    calculates cosine similarity over vector embeddings, and applies hybrid structured ranking.
    """
    parsed = NaturalLanguageQueryParser.parse(query_text)
    search_keywords = parsed.get("semantic_keywords") or query_text

    # Generate query vector
    query_vector = SemanticEmbedder.get_embedding(search_keywords)

    # Base queryset: only approved and active products
    base_qs = ProductEmbedding.objects.filter(
        product__is_active=True,
        product__enquiry_status__iexact="APPROVED",
        embedding__isnull=False
    ).select_related(
        "product",
        "product__category",
        "product__subcategory",
        "product__vendor"
    ).prefetch_related("product__images")

    # Annotate with cosine distance from query vector
    annotated_qs = base_qs.annotate(distance=CosineDistance("embedding", query_vector))

    # Apply Structured Filters if parsed from natural language query
    filtered_qs = annotated_qs

    if parsed["max_price"] is not None:
        filtered_qs = filtered_qs.filter(product__liquidating_price__lte=parsed["max_price"])

    if parsed["min_price"] is not None:
        filtered_qs = filtered_qs.filter(product__liquidating_price__gte=parsed["min_price"])

    if parsed["location"]:
        loc_term = parsed["location"]
        filtered_qs = filtered_qs.filter(
            Q(product__inventory_location__icontains=loc_term) |
            Q(product__vendor__business_location__icontains=loc_term)
        )

    if parsed["has_warranty"] is True:
        filtered_qs = filtered_qs.filter(
            Q(product__warranty__isnull=False) & ~Q(product__warranty="") |
            Q(product__warranty_attachment__isnull=False) & ~Q(product__warranty_attachment="")
        )

    if parsed["brand"]:
        filtered_qs = filtered_qs.filter(product__brand_name__icontains=parsed["brand"])

    # Check if filtered results are sufficient
    results_records = list(filtered_qs.order_by("distance")[:limit])

    # If strict filtering yielded zero results, gracefully fall back to top vector matches
    # so the buyer always gets the most semantically relevant inventory
    is_relaxed = False
    if not results_records:
        results_records = list(annotated_qs.order_by("distance")[:limit])
        is_relaxed = True

    formatted_results = []
    for rec in results_records:
        prod = rec.product
        dist = float(rec.distance) if rec.distance is not None else 1.0
        # Convert cosine distance to 0..100 similarity percentage
        similarity_score = max(0.0, min(100.0, round((1.0 - (dist / 2.0)) * 100, 1)))

        # Generate intelligent match reasons for the user
        reasons = []
        if similarity_score >= 65:
            reasons.append(f"Semantic match ({similarity_score}%) for '{search_keywords}'")
        if parsed["max_price"] is not None and prod.liquidating_price and prod.liquidating_price <= parsed["max_price"]:
            reasons.append(f"Price ({prod.currency or 'USD'} {prod.liquidating_price}) is within budget (max {parsed['max_price']})")
        if parsed["location"] and prod.inventory_location and parsed["location"].lower() in prod.inventory_location.lower():
            reasons.append(f"Located in requested region: {prod.inventory_location}")
        if parsed["has_warranty"] and (prod.warranty or prod.warranty_attachment):
            reasons.append("Includes verified warranty coverage")
        if parsed["brand"] and prod.brand_name and parsed["brand"].lower() in prod.brand_name.lower():
            reasons.append(f"Matches brand: {prod.brand_name}")

        if not reasons:
            reasons.append("Ranked by contextual vector similarity")

        first_img = prod.images.first()
        img_url = first_img.url if first_img else ""

        formatted_results.append({
            "id": prod.id,
            "product_id": prod.product_id or f"PRO-{prod.id:05d}",
            "product_name": prod.product_name,
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
            "similarity_score": similarity_score,
            "match_reasons": reasons,
        })

    return {
        "success": True,
        "query": query_text,
        "parsed_intent": parsed,
        "is_relaxed": is_relaxed,
        "total_results": len(formatted_results),
        "results": formatted_results
    }
