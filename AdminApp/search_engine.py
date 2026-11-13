"""
Enterprise Semantic Search Engine & Intent Parser for Surplus Platform.
Provides:
1. Location-based keyword matching & extraction (Dubai, UAE, Saudi Arabia, KSA, India, etc.).
2. 18 Domain Synonym Clusters with bidirectional expansion.
3. Singular/plural inflection, typo tolerance normalization, and British/American spelling alternatives.
4. Deterministic query intent extraction with category inference and ranking helpers.
"""

import re
from typing import Dict, List, Set, Optional, Tuple, Any

# ==============================================================================
# 1. TARGET LOCATION MARKETS & GEOGRAPHIC NORMALIZATION
# ==============================================================================

LOCATION_MARKETS: Dict[str, Dict[str, Any]] = {
    "dubai": {
        "market": "UAE",
        "country_names": ["United Arab Emirates", "UAE", "U.A.E."],
        "cities": ["Dubai", "Jebel Ali", "Al Quoz", "Jafza", "Deira", "Bur Dubai"],
        "aliases": ["dubai", "dxb"],
    },
    "uae": {
        "market": "UAE",
        "country_names": ["United Arab Emirates", "UAE", "U.A.E."],
        "cities": [
            "Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah",
            "Umm Al Quwain", "Jebel Ali", "Al Quoz", "Kizad", "Jafza", "Mussafah"
        ],
        "aliases": ["uae", "u.a.e.", "united arab emirates", "emirates"],
    },
    "united arab emirates": {
        "market": "UAE",
        "country_names": ["United Arab Emirates", "UAE", "U.A.E."],
        "cities": [
            "Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah",
            "Umm Al Quwain", "Jebel Ali", "Al Quoz", "Kizad", "Jafza", "Mussafah"
        ],
        "aliases": ["united arab emirates", "uae", "u.a.e.", "emirates"],
    },
    "saudi arabia": {
        "market": "Saudi Arabia",
        "country_names": ["Saudi Arabia", "KSA", "K.S.A."],
        "cities": ["Riyadh", "Jeddah", "Dammam", "Khobar", "Jubail", "Mecca", "Medina", "Yanbu"],
        "aliases": ["saudi arabia", "saudi", "ksa", "k.s.a."],
    },
    "saudi": {
        "market": "Saudi Arabia",
        "country_names": ["Saudi Arabia", "KSA", "K.S.A."],
        "cities": ["Riyadh", "Jeddah", "Dammam", "Khobar", "Jubail", "Mecca", "Medina", "Yanbu"],
        "aliases": ["saudi", "saudi arabia", "ksa", "k.s.a."],
    },
    "ksa": {
        "market": "Saudi Arabia",
        "country_names": ["Saudi Arabia", "KSA", "K.S.A."],
        "cities": ["Riyadh", "Jeddah", "Dammam", "Khobar", "Jubail", "Mecca", "Medina", "Yanbu"],
        "aliases": ["ksa", "k.s.a.", "saudi arabia", "saudi"],
    },
    "india": {
        "market": "India",
        "country_names": ["India", "IND", "Bharat"],
        "cities": [
            "Mumbai", "Delhi", "Bengaluru", "Bangalore", "Pune", "Hyderabad", "Chennai",
            "Ahmedabad", "Surat", "Kolkata", "Gujarat", "Maharashtra", "Karnataka",
            "Tamil Nadu", "Telangana", "Kerala", "Noida", "Gurugram", "Gurgaon"
        ],
        "aliases": ["india", "indian", "bharat", "ind"],
    },
    "indian": {
        "market": "India",
        "country_names": ["India", "IND", "Bharat"],
        "cities": [
            "Mumbai", "Delhi", "Bengaluru", "Bangalore", "Pune", "Hyderabad", "Chennai",
            "Ahmedabad", "Surat", "Kolkata", "Gujarat", "Maharashtra", "Karnataka",
            "Tamil Nadu", "Telangana", "Kerala", "Noida", "Gurugram", "Gurgaon"
        ],
        "aliases": ["indian", "india", "bharat", "ind"],
    },
}

# Ordered from longest phrase to shortest for regex matching
LOCATION_MATCH_ORDER = sorted(LOCATION_MARKETS.keys(), key=lambda x: len(x), reverse=True)


# ==============================================================================
# 2. SPELLING ALTERNATIVES & EQUIVALENCES
# ==============================================================================

SPELLING_ALTERNATIVES: Dict[str, Set[str]] = {
    "tyre": {"tire", "tyres", "tires"},
    "tire": {"tyre", "tires", "tyres"},
    "t-shirt": {"tshirt", "tee", "t-shirts", "tshirts", "tees"},
    "tshirt": {"t-shirt", "tee", "t-shirts", "tshirts", "tees"},
    "moulding": {"molding", "mouldings", "moldings"},
    "molding": {"moulding", "moldings", "mouldings"},
    "centre": {"center", "centres", "centers"},
    "center": {"centre", "centers", "centres"},
    "aluminium": {"aluminum"},
    "aluminum": {"aluminium"},
    "decor": {"décor", "decoration"},
    "décor": {"decor", "decoration"},
    "wifi": {"wi-fi", "wireless"},
    "wi-fi": {"wifi", "wireless"},
    "orthopaedic": {"orthopedic"},
    "orthopedic": {"orthopaedic"},
    "anaesthesia": {"anesthesia"},
    "anesthesia": {"anaesthesia"},
    "pvc": {"polyvinyl", "plastic pipe"},
    "led": {"leds", "lighting"},
    "leds": {"led", "lighting"},
    "ups": {"uninterruptible power supply", "backup power"},
    "ppe": {"safety equipment", "protective equipment", "safety gear"},
}


# ==============================================================================
# 3. 18 DOMAIN SYNONYM CLUSTERS
# ==============================================================================

RAW_DOMAIN_CLUSTERS: Dict[str, Dict[str, Any]] = {
    "apparel_fashion": {
        "category_name": "Apparel, Footwear & Accessories",
        "keywords": [
            "apparel", "clothing", "garments", "fashion", "fashion wear", "menswear",
            "womenswear", "kidswear", "children's clothing", "uniforms", "workwear",
            "safety clothing", "sportswear", "activewear", "casual wear", "formal wear",
            "ethnic wear", "jackets", "coats", "shirts", "t-shirts", "tshirts", "trousers",
            "jeans", "dresses", "skirts", "sweaters", "hoodies", "socks", "undergarments",
            "footwear", "shoes", "sneakers", "trainers", "boots", "sandals", "slippers",
            "heels", "sports shoes", "safety shoes", "leather shoes", "bags", "luggage",
            "handbags", "backpacks", "school bags", "travel bags", "suitcases", "trolley bags",
            "wallets", "purses", "belts", "caps", "hats", "scarves", "sunglasses",
            "fashion accessories", "clothing accessories", "mixed apparel lots", "bulk clothing",
            "wholesale garments", "surplus clothing", "excess fashion inventory",
            "liquidation apparel", "branded clothing lots", "retail clothing stock"
        ]
    },
    "automotive": {
        "category_name": "Automotive & Fleet Parts",
        "keywords": [
            "automotive", "automobile", "automobiles", "vehicle equipment", "motor vehicle parts",
            "car parts", "auto parts", "automotive spare parts", "vehicle spare parts",
            "aftermarket parts", "OEM parts", "engine components", "engine parts",
            "transmission parts", "gearbox parts", "brake pads", "brake discs", "brake rotors",
            "suspension parts", "steering components", "filters", "air filters", "oil filters",
            "fuel filters", "radiators", "alternators", "starters", "batteries", "car batteries",
            "automotive batteries", "tyres", "tires", "wheels", "rims", "lubricants",
            "engine oil", "motor oil", "gear oil", "hydraulic oil", "brake fluid", "coolant",
            "antifreeze", "grease", "industrial grease", "automotive fluids", "car accessories",
            "vehicle accessories", "workshop equipment", "garage equipment", "automotive tools",
            "automotive electrical parts", "commercial vehicle parts", "truck parts",
            "motorcycle parts", "mixed automotive lots", "bulk auto parts", "surplus auto parts"
        ]
    },
    "books_stationery": {
        "category_name": "Books, Stationery & Office Supplies",
        "keywords": [
            "books", "textbooks", "educational books", "academic books", "reference books",
            "novels", "fiction books", "non-fiction books", "children's books", "school books",
            "study materials", "stationery", "office supplies", "office stationery", "pens",
            "pencils", "markers", "highlighters", "notebooks", "notepads", "diaries", "journals",
            "paper products", "printer paper", "copier paper", "envelopes", "files", "folders",
            "binders", "document holders", "labels", "sticky notes", "staplers", "paper clips",
            "punches", "desk accessories", "office accessories", "art supplies", "craft supplies",
            "school supplies", "educational supplies", "printing materials", "printing consumables",
            "ink cartridges", "toner cartridges", "printer supplies", "office equipment",
            "shredders", "calculators", "mixed office lots", "bulk stationery", "wholesale books",
            "surplus stationery"
        ]
    },
    "construction_hardware": {
        "category_name": "Construction, Building Materials & Hardware",
        "keywords": [
            "construction materials", "building materials", "construction supplies", "hardware",
            "industrial hardware", "builders hardware", "MRO", "maintenance repair operations",
            "maintenance supplies", "repair supplies", "building supplies", "raw materials",
            "cement", "concrete products", "bricks", "blocks", "tiles", "flooring materials",
            "roofing materials", "insulation materials", "timber", "plywood", "drywall",
            "gypsum boards", "pipes", "plumbing materials", "plumbing fittings", "valves", "taps",
            "adhesives", "sealants", "silicone sealants", "industrial adhesives",
            "construction chemicals", "waterproofing materials", "paints", "coatings", "solvents",
            "fasteners", "bolts", "nuts", "screws", "washers", "anchors", "nails", "hinges",
            "locks", "handles", "metal fittings", "steel fittings", "aluminium fittings",
            "HVAC equipment", "air conditioning equipment", "ventilation systems", "air filters",
            "ducting", "pumps", "power tools", "hand tools", "measuring tools", "welding equipment",
            "workshop supplies", "safety equipment", "PPE", "protective equipment",
            "industrial consumables", "surplus building materials", "wholesale hardware"
        ]
    },
    "consumer_electronics_servers": {
        "category_name": "Consumer Electronics & Enterprise Hardware",
        "keywords": [
            "consumer electronics", "electronic appliances", "servers", "server equipment",
            "rack servers", "tower servers", "blade servers", "enterprise servers",
            "data centre equipment", "workstations", "desktop workstations", "professional workstations",
            "computer hardware", "IT hardware", "computer systems", "business computers",
            "refurbished computers", "used computers", "surplus IT equipment", "bulk electronics"
        ]
    },
    "electrical_lighting": {
        "category_name": "Electricals, Lighting & Power Systems",
        "keywords": [
            "electrical equipment", "electrical supplies", "electrical components", "electrical products",
            "electrical accessories", "industrial electrical equipment", "lighting equipment",
            "lighting fixtures", "LED lighting", "LED bulbs", "LED panels", "LED strips",
            "street lights", "flood lights", "high bay lights", "commercial lighting",
            "industrial lighting", "indoor lighting", "outdoor lighting", "batteries",
            "rechargeable batteries", "lithium batteries", "power supplies", "UPS systems",
            "uninterruptible power supplies", "inverters", "voltage stabilizers", "transformers",
            "generators", "diesel generators", "backup generators", "backup power systems",
            "cables", "electrical cables", "power cables", "data cables", "wires", "copper wires",
            "cable assemblies", "cable connectors", "switches", "electrical switches", "sockets",
            "plugs", "circuit breakers", "MCB", "MCCB", "distribution boards", "control panels",
            "electrical panels", "relays", "fuses", "terminals", "wiring accessories",
            "cable management", "cable trays", "electrical fittings", "electrical spare parts",
            "electrical parts", "electrical components", "cable accessories", "wire accessories",
            "connectors", "terminals", "cable glands", "junction boxes", "conduits",
            "electrical enclosures", "electronic components"
        ]
    },
    "mobile_phones": {
        "category_name": "Mobile Phones & Consumer Devices",
        "keywords": [
            "mobile phones", "smartphones", "cell phones", "Android phones", "iPhones",
            "tablets", "iPads", "mobile devices", "refurbished mobile phones", "used smartphones",
            "feature phones", "mobile accessories", "phone chargers", "screen protectors",
            "phone cases", "electronics", "consumer devices", "surplus mobile stock", "bulk mobile phones"
        ]
    },
    "electronics_ict": {
        "category_name": "Electronics, ICT & Telecom Equipment",
        "keywords": [
            "electronics and ICT", "ICT equipment", "information technology equipment",
            "IT equipment", "communication equipment", "telecom equipment", "networking equipment",
            "network hardware", "routers", "switches", "network switches", "modems",
            "wireless access points", "Wi-Fi equipment", "servers", "storage devices", "data storage",
            "hard drives", "SSD drives", "RAM", "memory modules", "processors", "CPUs", "GPUs",
            "graphics cards", "motherboards", "computer components", "computer accessories",
            "laptops", "notebook computers", "desktop computers", "monitors", "displays",
            "keyboards", "mice", "printers", "scanners", "projectors", "photocopiers",
            "audio equipment", "audio visual equipment", "audiovisual equipment", "AV equipment",
            "speakers", "headphones", "microphones", "amplifiers", "televisions", "digital displays",
            "video conferencing equipment", "cameras", "digital cameras", "CCTV cameras",
            "surveillance cameras", "camera lenses", "camera accessories", "chargers", "adapters",
            "cables", "electronic accessories", "electronic spare parts", "electronic components",
            "refurbished IT equipment", "used IT equipment", "bulk electronics", "surplus electronics"
        ]
    },
    "furniture": {
        "category_name": "Furniture & Interior Fixtures",
        "keywords": [
            "furniture", "office furniture", "commercial furniture", "home furniture",
            "hospitality furniture", "hotel furniture", "restaurant furniture", "school furniture",
            "institutional furniture", "industrial furniture", "chairs", "office chairs",
            "executive chairs", "visitor chairs", "desks", "office desks", "workstations",
            "conference tables", "dining tables", "meeting tables", "cabinets", "storage cabinets",
            "filing cabinets", "shelves", "shelving units", "racks", "sofas", "couches", "beds",
            "mattresses", "wardrobes", "drawers", "bookcases", "reception furniture",
            "modular furniture", "ergonomic furniture", "outdoor furniture", "garden furniture",
            "furniture fixtures", "furniture fittings", "interior décor", "home decor",
            "decorative items", "lighting fixtures", "partitions", "blinds", "curtains",
            "floor coverings", "carpets", "rugs", "wall décor", "display fixtures", "retail fixtures",
            "shop fittings", "commercial fixtures", "mixed furniture lots", "bulk furniture",
            "surplus furniture"
        ]
    },
    "general_mixed_lots": {
        "category_name": "Wholesale Lots & Inventory Liquidation",
        "keywords": [
            "general mixed lots", "mixed inventory", "mixed merchandise", "mixed products",
            "assorted goods", "assorted products", "assorted inventory", "general merchandise",
            "wholesale mixed lots", "bulk mixed lots", "liquidation stock", "clearance stock",
            "surplus stock", "excess inventory", "overstock products", "dead stock",
            "warehouse clearance", "business liquidation", "retail liquidation", "wholesale liquidation",
            "closeout inventory", "discontinued products", "returned goods", "customer returns",
            "shelf pulls", "open box products", "refurbished stock", "used inventory",
            "unclaimed stock", "pallet lots", "bulk pallets", "assorted pallets", "wholesale pallets",
            "mixed pallets", "stock lots", "bulk goods"
        ]
    },
    "hospitality_catering": {
        "category_name": "Hospitality & Commercial Kitchen Supplies",
        "keywords": [
            "hospitality supplies", "hotel supplies", "restaurant supplies", "catering supplies",
            "commercial kitchen supplies", "food service equipment", "commercial kitchen equipment",
            "catering equipment", "kitchen machinery", "cooking equipment", "ovens",
            "commercial ovens", "microwave ovens", "industrial ovens", "cookers", "stoves",
            "fryers", "grills", "griddles", "food preparation equipment", "food processors",
            "mixers", "blenders", "commercial mixers", "dishwashers", "commercial dishwashers",
            "ice machines", "ice makers", "coffee machines", "espresso machines", "beverage equipment",
            "water dispensers", "commercial refrigeration", "commercial refrigerators",
            "industrial refrigerators", "freezers", "display chillers", "cold storage equipment",
            "refrigeration units", "cold rooms", "cleaning equipment", "housekeeping equipment",
            "laundry equipment", "hotel amenities", "hotel furniture", "buffet equipment",
            "serveware", "tableware", "chinaware", "glassware", "cutlery", "kitchen utensils",
            "cookware", "pots", "pans", "food storage containers", "trolleys", "food warming equipment",
            "banquet equipment", "bar equipment", "POS hardware", "restaurant furniture",
            "hotel linen", "commercial blenders", "commercial slicers", "bulk hospitality equipment",
            "surplus restaurant equipment"
        ]
    },
    "household_cleaning": {
        "category_name": "Household Items & Cleaning Supplies",
        "keywords": [
            "household items", "home appliances", "kitchen appliances", "small kitchen appliances",
            "domestic appliances", "white goods", "refrigerators", "washing machines", "dryers",
            "dishwashers", "vacuum cleaners", "floor care equipment", "air purifiers",
            "humidifiers", "dehumidifiers", "heaters", "room heaters", "fans", "ceiling fans",
            "standing fans", "irons", "steam irons", "garment steamers", "microwaves", "toasters",
            "kettles", "blenders", "juicers", "mixers", "air fryers", "food makers",
            "coffee makers", "kitchenware", "cookware", "bakeware", "dinnerware", "tableware",
            "cutlery", "glassware", "plasticware", "storage containers", "kitchen organizers",
            "home decor", "home furnishings", "bed linen", "bedsheets", "blankets", "duvets",
            "pillows", "curtains", "towels", "bath mats", "bathroom accessories",
            "cleaning supplies", "cleaning equipment", "mops", "brooms", "buckets",
            "cleaning chemicals", "detergents", "surface cleaners", "waste bins", "storage boxes",
            "organization products", "laundry baskets", "ironing boards", "surplus home goods",
            "bulk appliances", "liquidated household inventory"
        ]
    },
    "industrial_machinery": {
        "category_name": "Industrial Machinery & Equipment",
        "keywords": [
            "industrial machinery", "machinery", "industrial equipment", "heavy machinery",
            "manufacturing machinery", "production equipment", "factory equipment",
            "processing equipment", "packaging machinery", "CNC machines", "CNC routers",
            "lathes", "milling machines", "drilling machines", "metalworking machinery",
            "woodworking machinery", "injection moulding machines", "extruders", "presses",
            "stamping machines", "sheet metal machinery", "laser cutting machines", "plasma cutters",
            "bending machines", "compressors", "industrial air compressors", "generators",
            "industrial generators", "diesel generators", "pumps", "industrial pumps",
            "hydraulic equipment", "hydraulic power units", "hydraulic cylinders", "pneumatic equipment",
            "motors", "electric motors", "gear motors", "gearboxes", "speed reducers",
            "transmission systems", "industrial conveyors", "conveyor belts",
            "material handling equipment", "lifting equipment", "cranes", "overhead cranes",
            "hoists", "winches", "forklifts", "reach trucks", "pallet trucks", "stackers",
            "order pickers", "racking systems", "industrial shelving", "pallet racking",
            "storage racks", "robotic equipment", "industrial robots", "automation equipment",
            "PLCs", "industrial sensors", "control systems", "welding machinery", "MIG welders",
            "TIG welders", "welding robots", "cutting machinery", "boilers", "industrial boilers",
            "chillers", "industrial chillers", "heat exchangers", "cooling towers", "furnaces",
            "industrial ovens", "test equipment", "measurement equipment", "quality control equipment",
            "recycling equipment", "shredders", "granulators", "balers", "workshop equipment",
            "industrial maintenance tools", "surplus machinery", "used industrial equipment",
            "decommissioned machinery", "factory liquidation equipment", "bulk industrial assets"
        ]
    },
    "medical_laboratory": {
        "category_name": "Medical, Healthcare & Laboratory Equipment",
        "keywords": [
            "medical equipment", "healthcare equipment", "hospital equipment", "clinical equipment",
            "diagnostic equipment", "patient monitors", "vital signs monitors", "ECG machines",
            "ultrasound machines", "X-ray equipment", "MRI accessories", "CT scanner components",
            "defibrillators", "infusion pumps", "syringe pumps", "ventilators",
            "oxygen concentrators", "anaesthesia machines", "surgical equipment",
            "surgical instruments", "operating tables", "surgical lights", "electrosurgical units",
            "autoclaves", "sterilizers", "endoscopy equipment", "ophthalmic equipment",
            "dental equipment", "dental chairs", "dental instruments", "laboratory equipment",
            "lab instruments", "microscopes", "centrifuges", "spectrophotometers", "incubators",
            "lab freezers", "biosafety cabinets", "analytical equipment", "testing equipment",
            "mobility equipment", "wheelchairs", "hospital beds", "medical furniture",
            "examination tables", "rehabilitation equipment", "orthopaedic supplies",
            "medical consumables", "PPE", "medical disposables", "gloves", "masks", "syringes",
            "diagnostic kits", "surplus medical devices", "refurbished healthcare equipment",
            "excess hospital inventory", "liquidated medical stock"
        ]
    },
    "oil_gas": {
        "category_name": "Oil & Gas, Energy Equipment",
        "keywords": [
            "oil and gas equipment", "petroleum equipment", "drilling equipment", "exploration equipment",
            "oilfield equipment", "offshore equipment", "refinery equipment", "pipeline equipment",
            "drill pipes", "casing pipes", "tubing", "drill bits", "wellhead equipment",
            "Christmas trees", "blowout preventers", "BOP", "mud pumps", "shale shakers",
            "valves", "ball valves", "gate valves", "check valves", "globe valves",
            "butterfly valves", "needle valves", "control valves", "safety relief valves",
            "high pressure valves", "flanges", "weld neck flanges", "blind flanges", "pipe fittings",
            "elbows", "tees", "reducers", "couplings", "pipes", "seamless pipes",
            "carbon steel pipes", "stainless steel pipes", "line pipe", "OCTG", "instrumentation",
            "pressure gauges", "temperature gauges", "flow meters", "level transmitters",
            "control systems", "SCADA systems", "pumps", "centrifugal pumps",
            "positive displacement pumps", "chemical injection pumps", "compressors", "gas compressors",
            "reciprocating compressors", "screw compressors", "turbines", "gas turbines",
            "steam turbines", "heat exchangers", "shell and tube heat exchangers", "pressure vessels",
            "separator vessels", "storage tanks", "fuel tanks", "chemical tanks", "filtration systems",
            "gas scrubbers", "flare systems", "metering skids", "pigging equipment", "separators",
            "loading arms", "marine hoses", "hoses", "high pressure hoses", "mooring equipment",
            "safety equipment", "H2S detection systems", "fire and gas systems",
            "explosion proof equipment", "ATEX equipment", "hazardous area equipment",
            "electrical equipment for hazardous areas", "rig spares", "surplus oilfield supplies",
            "decommissioned oil and gas equipment", "excess refinery inventory", "liquidated petroleum assets"
        ]
    },
    "packaging": {
        "category_name": "Packaging Materials & Equipment",
        "keywords": [
            "packaging materials", "packing supplies", "industrial packaging", "packaging equipment",
            "packaging machinery", "corrugated boxes", "cardboard boxes", "shipping boxes",
            "carton boxes", "cartons", "mailers", "padded envelopes", "bubble mailers",
            "pallet boxes", "packaging tape", "adhesive tape", "sealing tape", "custom printed tape",
            "stretch film", "pallet wrap", "shrink wrap", "cling film", "shrink film",
            "bubble wrap", "foam packaging", "air pillows", "void fill", "packing paper",
            "strapping", "plastic strapping", "steel strapping", "strapping seals", "poly bags",
            "polythene bags", "plastic bags", "ziplock bags", "garbage bags", "bulk bags",
            "FIBC bags", "woven bags", "paper bags", "kraft bags", "shopping bags", "shipping sacks",
            "containers", "plastic containers", "metal containers", "drums", "plastic drums",
            "steel drums", "IBC totes", "intermediate bulk containers", "bottles", "plastic bottles",
            "glass bottles", "jars", "cans", "tins", "closures", "caps", "lids", "pumps",
            "trigger sprayers", "labels", "barcode labels", "thermal labels", "adhesive labels",
            "tags", "protective packaging", "edge protectors", "corner boards", "packaging machinery",
            "carton sealers", "case sealers", "tape machines", "stretch wrapping machines",
            "pallet wrappers", "shrink wrap machines", "heat sealers", "vacuum packaging machines",
            "strapping machines", "banding machines", "filling machines", "liquid filling machines",
            "bottle filling machines", "capping machines", "labeling machines", "coding machines",
            "inkjet coders", "checkweighers", "metal detectors", "bagging machines",
            "form fill seal machines", "blister packaging machines", "palletizers", "packaging tools",
            "tape dispensers", "strapping tensioners", "heat guns", "surplus packaging materials",
            "wholesale boxes", "bulk packing supplies", "liquidated packaging inventory"
        ]
    },
    "renewable_solar": {
        "category_name": "Renewable Energy & Solar Equipment",
        "keywords": [
            "renewable energy equipment", "green energy products", "solar equipment",
            "solar energy systems", "solar products", "photovoltaic equipment", "PV equipment",
            "solar panels", "solar modules", "monocrystalline solar panels", "polycrystalline panels",
            "bifacial solar panels", "thin-film solar panels", "Tier 1 solar panels", "solar inverters",
            "grid-tie inverters", "off-grid inverters", "hybrid inverters", "string inverters",
            "central inverters", "microinverters", "solar charge controllers", "MPPT charge controllers",
            "PWM charge controllers", "solar batteries", "energy storage systems", "ESS",
            "lithium iron phosphate batteries", "LiFePO4 batteries", "lithium-ion storage",
            "deep cycle batteries", "gel batteries", "tubular batteries", "solar mounting structures",
            "rooftop mounting systems", "ground mount structures", "solar tracking systems",
            "solar cables", "photovoltaic cables", "solar connectors", "MC4 connectors",
            "combiner boxes", "DC disconnect switches", "solar junction boxes", "solar lighting",
            "solar street lights", "solar flood lights", "solar garden lights", "solar pumps",
            "solar water pumping systems", "solar water heaters", "thermal solar systems",
            "wind energy equipment", "wind turbines", "small wind turbines", "wind turbine generators",
            "wind turbine blades", "wind controllers", "wind inverters", "hybrid wind-solar systems",
            "hydro turbines", "micro hydro equipment", "portable power stations", "solar generators",
            "backup power storage", "off-grid power kits", "clean energy accessories",
            "surplus solar stock", "bulk solar modules", "liquidated renewable energy inventory"
        ]
    },
    "toys_sports": {
        "category_name": "Toys, Games & Sports Equipment",
        "keywords": [
            "toys", "children's toys", "baby toys", "toddler toys", "educational toys",
            "learning toys", "STEM toys", "action figures", "dolls", "doll accessories",
            "playsets", "plush toys", "stuffed animals", "board games", "card games",
            "tabletop games", "puzzles", "jigsaw puzzles", "building blocks", "construction toys",
            "vehicle toys", "toy cars", "remote control toys", "RC cars", "RC helicopters",
            "drones", "toy tracks", "outdoor toys", "ride-on toys", "scooters", "tricycles",
            "balance bikes", "play tents", "playhouses", "sand toys", "water toys", "pool toys",
            "inflatable toys", "creative toys", "art and craft toys", "musical toys",
            "role play toys", "dress-up costumes", "pretend play sets", "electronic toys",
            "interactive toys", "gaming accessories", "sports equipment", "sporting goods",
            "athletic equipment", "fitness equipment", "gym equipment", "exercise equipment",
            "cardio equipment", "treadmills", "exercise bikes", "elliptical trainers",
            "rowing machines", "strength equipment", "weight benches", "dumbbells", "barbells",
            "weight plates", "kettlebells", "resistance bands", "yoga equipment", "yoga mats",
            "yoga blocks", "Pilates equipment", "team sports equipment", "footballs", "soccer balls",
            "basketballs", "volleyballs", "rugby balls", "baseballs", "cricket equipment",
            "cricket bats", "cricket balls", "protective gear", "tennis rackets", "tennis balls",
            "badminton rackets", "shuttlecocks", "squash rackets", "table tennis equipment",
            "ping pong tables", "golf equipment", "golf clubs", "golf balls", "golf bags",
            "boxing equipment", "boxing gloves", "punching bags", "martial arts gear",
            "water sports equipment", "swimming gear", "goggles", "snorkelling equipment",
            "diving gear", "surfboards", "paddleboards", "kayaks", "life jackets",
            "cycling equipment", "bicycles", "mountain bikes", "road bikes", "cycling helmets",
            "cycling accessories", "skateboards", "roller skates", "inline skates",
            "protective pads", "helmets", "sports apparel", "sportswear", "athletic footwear",
            "sports bags", "outdoor recreation equipment", "camping gear", "tents",
            "sleeping bags", "camping furniture", "hiking equipment", "trekking poles",
            "backpacks", "sports accessories", "stopwatches", "whistles", "pumps", "bulk toys",
            "surplus sporting goods", "liquidation toys", "excess sports inventory"
        ]
    }
}


# Precompute inverted keyword-to-cluster and keyword-to-category index
KEYWORD_TO_CLUSTER: Dict[str, str] = {}
KEYWORD_TO_CATEGORY: Dict[str, str] = {}
CLUSTER_KEYWORDS: Dict[str, Set[str]] = {}

for cluster_key, data in RAW_DOMAIN_CLUSTERS.items():
    cat_name = data["category_name"]
    kw_set: Set[str] = set()
    for kw in data["keywords"]:
        clean_kw = kw.strip().lower()
        if not clean_kw:
            continue
        kw_set.add(clean_kw)
        KEYWORD_TO_CLUSTER[clean_kw] = cluster_key
        KEYWORD_TO_CATEGORY[clean_kw] = cat_name
    CLUSTER_KEYWORDS[cluster_key] = kw_set


# ==============================================================================
# 4. INFLECTION & STEMMING HELPERS
# ==============================================================================

def get_word_variants(word: str) -> Set[str]:
    """
    Returns singular/plural variants and spelling alternatives for a given token.
    """
    w = word.strip().lower()
    if len(w) < 3:
        return {w}

    variants: Set[str] = {w}

    # Direct spelling alternatives
    if w in SPELLING_ALTERNATIVES:
        variants.update(SPELLING_ALTERNATIVES[w])

    # Plural to singular rules
    if w.endswith("ies") and len(w) > 4:
        variants.add(w[:-3] + "y")
    elif w.endswith("ves") and len(w) > 4:
        variants.add(w[:-3] + "f")
        variants.add(w[:-3] + "fe")
    elif (w.endswith("ses") or w.endswith("shes") or w.endswith("ches") or w.endswith("xes") or w.endswith("zes")) and len(w) > 4:
        variants.add(w[:-2])
    elif w.endswith("oes") and len(w) >= 4:
        variants.add(w[:-1])  # shoes -> shoe, tomatoes -> tomato
    elif w.endswith("es") and len(w) > 4:
        variants.add(w[:-2])
        variants.add(w[:-1])
    elif w.endswith("s") and not w.endswith("ss") and len(w) >= 4:
        variants.add(w[:-1])

    # Singular to plural rules
    if w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
        variants.add(w[:-1] + "ies")
    elif w.endswith(("s", "sh", "ch", "x", "z")):
        variants.add(w + "es")
    elif not w.endswith("s"):
        variants.add(w + "s")

    # Add spelling variants for any derived forms
    for v in list(variants):
        if v in SPELLING_ALTERNATIVES:
            variants.update(SPELLING_ALTERNATIVES[v])

    # Discard any over-truncated stems (e.g. "sho" from "shoes") that cause false positives
    clean_variants = set()
    for v in variants:
        if len(v) >= 4 or v == w:
            clean_variants.add(v)

    return clean_variants


# ==============================================================================
# 5. SEARCH INTENT EXTRACTION
# ==============================================================================

STOP_WORDS: Set[str] = {
    "show", "me", "find", "get", "look", "looking", "for", "i", "need", "want", "can", "you",
    "please", "give", "display", "search", "list", "all", "any", "some", "a", "an", "the",
    "with", "without", "having", "available", "located", "where", "which", "are", "is",
    "that", "under", "below", "less", "than", "above", "over", "more", "price", "priced",
    "budget", "cost", "costing", "in", "at", "from", "between", "to", "and", "or", "of"
}

BULK_LOT_PHRASES: List[str] = [
    r'\bin\s+bulk\b', r'\bbulk\b', r'\bwholesale\s+lots?\b', r'\bwholesale\b',
    r'\bin\s+lots?\b', r'\blots?\b', r'\bpallets?\b', r'\bmanifest\b',
    r'\bcontainer\s+loads?\b', r'\bbulk\s+quantity\b', r'\blarge\s+quantity\b',
    r'\bliquidation\b', r'\bclearance\b', r'\boverstock\b', r'\bexcess\s+inventory\b'
]


# Words that are generic descriptors across all industrial/commercial categories
GENERIC_MODIFIERS: Set[str] = {
    "equipment", "supplies", "materials", "products", "goods", "accessories",
    "parts", "spares", "items", "systems", "components", "units", "lots",
    "bulk", "wholesale", "surplus", "inventory", "stock", "liquidation"
}


def extract_search_intent(query_str: str) -> Dict[str, Any]:
    """
    Extracts semantic search intent from a buyer query:
    - Detected Location Market (Dubai, UAE, Saudi Arabia, India, etc.)
    - Country filters & city aliases
    - Cleaned product query string (stripped of location and stop words)
    - Normalized tokens & singular/plural variants
    - Matched synonym domain clusters & catalog categories
    - Bulk / wholesale lot intent
    """
    raw_query = (query_str or "").strip()
    q_lower = raw_query.lower()

    intent: Dict[str, Any] = {
        "raw_query": raw_query,
        "location_detected": None,
        "market": None,
        "target_countries": [],
        "target_cities": [],
        "cleaned_query": raw_query,
        "is_lot": False,
        "tokens": [],
        "token_variants": [],
        "matched_clusters": [],
        "inferred_categories": [],
        "expanded_terms": [],
    }

    if not raw_query:
        return intent

    # 1. Bulk / Lot Intent
    for bp in BULK_LOT_PHRASES:
        if re.search(bp, q_lower):
            intent["is_lot"] = True
            break

    # 2. Extract Location Keyword Matching
    cleaned_location_text = q_lower
    for loc_key in LOCATION_MATCH_ORDER:
        pattern = r'\b' + re.escape(loc_key) + r'\b'
        if re.search(pattern, cleaned_location_text):
            loc_data = LOCATION_MARKETS[loc_key]
            intent["location_detected"] = loc_key.title()
            intent["market"] = loc_data["market"]
            intent["target_countries"] = loc_data["country_names"]
            intent["target_cities"] = loc_data["cities"]

            # Remove location name from text
            cleaned_location_text = re.sub(
                r'(?:available\s+in|located\s+in|in|from|at)?\s*' + pattern,
                ' ', cleaned_location_text
            )
            break

    # 3. Clean Text & Extract Tokens
    cleaned_tokens_raw = re.sub(r'[^a-zA-Z0-9\-\s]', ' ', cleaned_location_text)
    raw_tokens = [t.strip().lower() for t in cleaned_tokens_raw.split() if t.strip()]

    # Filter out stop words and short tokens
    product_tokens: List[str] = []
    for t in raw_tokens:
        clean_t = t.strip("-")
        if clean_t and clean_t not in STOP_WORDS and len(clean_t) >= 2:
            product_tokens.append(clean_t)

    intent["tokens"] = product_tokens
    intent["cleaned_query"] = " ".join(product_tokens) if product_tokens else raw_query

    # 4. Generate Inflections & Variants for all product tokens
    all_variants: Set[str] = set()
    for t in product_tokens:
        all_variants.update(get_word_variants(t))
    intent["token_variants"] = sorted(list(all_variants))

    # 5. Synonym Cluster & Category Matching
    # Phase A: Exact multi-word phrase matching (highest precision)
    full_cleaned_phrase = " ".join(product_tokens)
    matched_clusters: Set[str] = set()
    inferred_categories: Set[str] = set()
    expanded_terms: Set[str] = set(all_variants)

    # Check for direct keyword matches
    for cluster_key, kw_set in CLUSTER_KEYWORDS.items():
        cat_name = RAW_DOMAIN_CLUSTERS[cluster_key]["category_name"]
        for kw in kw_set:
            if kw == full_cleaned_phrase or (len(kw) > 4 and kw in full_cleaned_phrase):
                matched_clusters.add(cluster_key)
                inferred_categories.add(cat_name)
                break

    # Phase B: Specific non-generic token matching
    specific_variants = {v for v in all_variants if v not in GENERIC_MODIFIERS}
    if specific_variants:
        for cluster_key, kw_set in CLUSTER_KEYWORDS.items():
            cat_name = RAW_DOMAIN_CLUSTERS[cluster_key]["category_name"]
            for v in specific_variants:
                if v in kw_set or any(v == part for kw in kw_set for part in kw.split()):
                    matched_clusters.add(cluster_key)
                    inferred_categories.add(cat_name)
                    break
    elif not matched_clusters:
        # Fallback if query only had generic terms (e.g. "wholesale lots")
        for cluster_key, kw_set in CLUSTER_KEYWORDS.items():
            cat_name = RAW_DOMAIN_CLUSTERS[cluster_key]["category_name"]
            for v in all_variants:
                if v in kw_set:
                    matched_clusters.add(cluster_key)
                    inferred_categories.add(cat_name)
                    break

    # Collect expanded terms from matched clusters
    for cluster_key in matched_clusters:
        kw_list = list(CLUSTER_KEYWORDS[cluster_key])
        for kw in kw_list[:15]:
            expanded_terms.add(kw)

    intent["matched_clusters"] = sorted(list(matched_clusters))
    intent["inferred_categories"] = sorted(list(inferred_categories))
    intent["expanded_terms"] = sorted(list(expanded_terms))

    return intent
