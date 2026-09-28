from django.core.management.base import BaseCommand
from django.utils.text import slugify
from AdminApp.models import MainCategory, SubCategory

CATEGORIES_DATA = {
    "Electronics & ICT": [
        "Computers and laptops",
        "Mobile phones and tablets",
        "Servers and networking equipment",
        "Printers and scanners",
        "Audio-visual equipment",
        "Cameras and accessories",
        "Telecommunication equipment",
        "Cables, chargers, and accessories",
        "Electronic components",
        "Software and licenses",
    ],
    "Electrical & Lighting": [
        "Electrical equipment",
        "Switches and sockets",
        "Cables and wires",
        "Lighting fixtures",
        "LED products",
        "Batteries and power supplies",
        "Solar and renewable-energy equipment",
        "Generators and backup-power equipment",
    ],
    "Industrial Machinery & Equipment": [
        "Manufacturing machinery",
        "Processing equipment",
        "Compressors and pumps",
        "Motors and gearboxes",
        "Material-handling equipment",
        "Warehouse equipment",
        "Packaging machinery",
        "Agricultural and construction equipment",
        "Tools and workshop equipment",
    ],
    "Automotive": [
        "Auto parts",
        "Vehicle accessories",
        "Tyres and batteries",
        "Workshop equipment",
        "Lubricants, Oils, Greases & Fluids",
    ],
    "Construction, Hardware & MRO": [
        "Building materials",
        "Plumbing materials",
        "HVAC equipment",
        "Fasteners and fittings",
        "Hand tools",
        "Power tools",
        "Maintenance, repair, and operations supplies",
        "Lubricants, Oils, Greases & Fluids",
        "Safety Equipment & PPE",
    ],
    "Furniture & Interiors": [
        "Office furniture",
        "Home furniture",
        "Commercial furniture",
        "Shelving and storage",
        "Fixtures and fittings",
        "Interior décor",
        "Outdoor furniture",
    ],
    "Apparel, Footwear & Accessories": [
        "Clothing",
        "Uniforms and workwear",
        "Footwear",
        "Bags and luggage",
        "Fashion accessories",
        "Textiles and fabrics",
        "Personal protective clothing",
    ],
    "Books, Stationery & Office Supplies": [
        "Books",
        "Stationery",
        "Office supplies",
        "Printing materials",
        "School supplies",
        "Promotional products",
    ],
    "Toys, Hobbies & Sports": [
        "Toys",
        "Games and puzzles",
        "Educational toys",
        "Hobby products",
        "Sports equipment",
        "Fitness equipment",
        "Outdoor and recreational products",
    ],
    "Hospitality, Catering & Commercial Supplies": [
        "Restaurant equipment",
        "Catering equipment",
        "Kitchen equipment",
        "Hotel supplies",
        "Commercial refrigeration",
        "Cleaning equipment",
    ],
    "Medical, Laboratory & Scientific Equipment": [
        "Medical equipment",
        "Laboratory equipment",
        "Diagnostic equipment",
        "Dental equipment",
        "Healthcare furniture",
        "Non-pharmaceutical medical supplies",
    ],
    "Packaging & Industrial Consumables": [
        "Packaging materials",
        "Boxes and cartons",
        "Plastic packaging",
        "Labels and printing materials",
        "Industrial consumables",
        "Adhesives and sealants",
    ],
    "Renewable Energy & Environmental Equipment": [
        "Solar panels",
        "Inverters",
        "Batteries",
        "Solar mounting systems",
        "Water-treatment equipment",
        "Waste-management equipment",
        "Energy-efficiency equipment",
    ],
    "Household & Cleaning Items": [
        "Household pest control products",
        "Kitchen rolls and paper towels",
        "Toilet paper and tissues",
        "Cleaning chemicals",
        "Disposable household items",
    ],
    "Other Non-FMCG Products": [
        "Products that do not fit the listed categories",
        "Mixed lots",
        "Unclassified inventory",
        "General merchandise",
    ],
}

class Command(BaseCommand):
    help = "Remove existing categories and seed new Main Categories and Subcategories into the database"

    def handle(self, *args, **options):
        # Clear existing subcategories and main categories
        deleted_subs, _ = SubCategory.objects.all().delete()
        deleted_mains, _ = MainCategory.objects.all().delete()
        self.stdout.write(f"Cleared {deleted_subs} SubCategories and {deleted_mains} MainCategories.")

        total_mains = 0
        total_subs = 0

        for main_name, subs in CATEGORIES_DATA.items():
            main_slug = slugify(main_name)
            main_cat = MainCategory.objects.create(
                name=main_name,
                slug=main_slug,
                description=f"All products and lots under {main_name}",
                is_active=True,
            )
            total_mains += 1

            for sub_name in subs:
                sub_slug = slugify(f"{main_name}-{sub_name}")
                SubCategory.objects.create(
                    main_category=main_cat,
                    name=sub_name,
                    slug=sub_slug,
                    description=f"{sub_name} under {main_name}",
                    is_active=True,
                )
                total_subs += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded {total_mains} Main Categories and {total_subs} SubCategories!"
            )
        )
