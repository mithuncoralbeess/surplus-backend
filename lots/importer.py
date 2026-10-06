import pandas as pd
import math
import re
import json

# Define Field Specifications (All 45 Fixed Fields)
FIELD_SPECIFICATIONS = {
    # --- Mandatory Fields (8) ---
    's_no': {
        'label': 'S.No*',
        'mandatory': True,
        'synonyms': ['s.no*', 's.no', 'sno', 's. no', 'item no', 'item no.', 'line_no', 'line no', '#', 'row', 'sl no', 'sl.no', 'serial no', 'serial number']
    },
    'product_name': {
        'label': 'Product Name*',
        'mandatory': True,
        'synonyms': ['product name*', 'product name', 'product', 'item name', 'title', 'name', 'product title']
    },
    'product_description': {
        'label': 'Product Description*',
        'mandatory': True,
        'synonyms': ['product description*', 'product description', 'description', 'item description', 'details', 'product details', 'item details']
    },
    'product_category': {
        'label': 'Product Category*',
        'mandatory': True,
        'synonyms': ['product category*', 'product category', 'category', 'main category', 'dept', 'department', 'cat']
    },
    'subcategory': {
        'label': 'Subcategory*',
        'mandatory': True,
        'synonyms': ['subcategory*', 'subcategory', 'sub-category', 'sub category', 'subcat', 'sub category name']
    },
    'available_quantity': {
        'label': 'Available Quantity*',
        'mandatory': True,
        'synonyms': ['available quantity*', 'available quantity', 'available qty', 'quantity', 'qty', 'units', 'count', 'total quantity', 'stock qty']
    },
    'moq': {
        'label': 'MOQ*',
        'mandatory': True,
        'synonyms': ['moq*', 'moq', 'minimum order quantity', 'min order qty', 'min order quantity', 'minimum quantity']
    },
    'product_condition': {
        'label': 'Product Condition*',
        'mandatory': True,
        'synonyms': ['product condition*', 'product condition', 'condition', 'state', 'grade', 'item condition']
    },

    # --- Optional Fields (37) ---
    'brand': {
        'label': 'Brand / Manufacturer',
        'mandatory': False,
        'synonyms': ['brand / manufacturer', 'brand', 'manufacturer', 'mfg', 'make', 'brand name']
    },
    'model_part_number': {
        'label': 'Model / Part Number',
        'mandatory': False,
        'synonyms': ['model / part number', 'model', 'part number', 'model no', 'part no', 'model / part no', 'sku', 'mpn', 'part #']
    },
    'original_price': {
        'label': 'Original Price',
        'mandatory': False,
        'synonyms': ['original price', 'msrp', 'retail price', 'original cost', 'unit price', 'list price']
    },
    'asking_price': {
        'label': 'Asking Price',
        'mandatory': False,
        'synonyms': ['asking price', 'target price', 'offer price', 'price', 'selling price', 'ext price', 'extended value', 'our price']
    },
    'price_negotiable': {
        'label': 'Price Negotiable?',
        'mandatory': False,
        'synonyms': ['price negotiable?', 'price negotiable', 'negotiable', 'is negotiable', 'negotiable?']
    },
    'country_of_origin': {
        'label': 'Country of Origin',
        'mandatory': False,
        'synonyms': ['country of origin', 'origin', 'made in', 'coo', 'country']
    },
    'year_of_manufacture': {
        'label': 'Year of Manufacture',
        'mandatory': False,
        'synonyms': ['year of manufacture', 'year', 'mfg year', 'manufacture year', 'yom', 'production year']
    },
    'datasheet_certificate_link': {
        'label': 'Datasheet / Certificate Link',
        'mandatory': False,
        'synonyms': ['datasheet / certificate link', 'datasheet link', 'certificate link', 'datasheet', 'certificate', 'doc link', 'url', 'link']
    },
    'quantity_per_box': {
        'label': 'Quantity per Box / Carton',
        'mandatory': False,
        'synonyms': ['quantity per box / carton', 'quantity per box', 'qty per box', 'qty/box', 'units per box', 'pack size', 'pcs per box']
    },
    'number_of_boxes': {
        'label': 'Number of Boxes / Cartons',
        'mandatory': False,
        'synonyms': ['number of boxes / cartons', 'number of boxes', 'no of boxes', 'box count', 'carton count', 'cartons', 'boxes']
    },
    'packaging_type': {
        'label': 'Packaging Type',
        'mandatory': False,
        'synonyms': ['packaging type', 'package type', 'packaging', 'box type', 'crate', 'pallet']
    },
    'packaging_condition': {
        'label': 'Packaging Condition',
        'mandatory': False,
        'synonyms': ['packaging condition', 'box condition', 'package condition']
    },
    'net_weight_per_unit': {
        'label': 'Net Weight per Unit',
        'mandatory': False,
        'synonyms': ['net weight per unit', 'net weight', 'unit net weight', 'net wt']
    },
    'gross_weight_per_unit': {
        'label': 'Gross Weight per Unit',
        'mandatory': False,
        'synonyms': ['gross weight per unit', 'gross weight', 'unit gross weight', 'gross wt']
    },
    'length': {
        'label': 'Length',
        'mandatory': False,
        'synonyms': ['length', 'len', 'l']
    },
    'width': {
        'label': 'Width',
        'mandatory': False,
        'synonyms': ['width', 'w']
    },
    'height': {
        'label': 'Height',
        'mandatory': False,
        'synonyms': ['height', 'h']
    },
    'measurement_unit': {
        'label': 'Measurement Unit',
        'mandatory': False,
        'synonyms': ['measurement unit', 'dimension unit', 'unit of measure', 'uom', 'dim unit']
    },
    'total_weight': {
        'label': 'Total Weight',
        'mandatory': False,
        'synonyms': ['total weight', 'total wt', 'overall weight', 'weight', 'wt']
    },
    'pallet_count': {
        'label': 'Pallet Count',
        'mandatory': False,
        'synonyms': ['pallet count', 'number of pallets', 'pallets', 'pallet qty']
    },
    'lot_bundle_size': {
        'label': 'Lot / Bundle Size',
        'mandatory': False,
        'synonyms': ['lot / bundle size', 'lot size', 'bundle size', 'lot qty']
    },
    'stock_age': {
        'label': 'Stock Age',
        'mandatory': False,
        'synonyms': ['stock age', 'age of stock', 'inventory age', 'shelf age']
    },
    'tested_and_verified': {
        'label': 'Tested and verified',
        'mandatory': False,
        'synonyms': ['tested and verified', 'tested & verified', 'tested', 'verified', 'is tested']
    },
    'functional_status': {
        'label': 'Functional Status',
        'mandatory': False,
        'synonyms': ['functional status', 'working status', 'functionality', 'operational status']
    },
    'visible_damage': {
        'label': 'Visible Damage?',
        'mandatory': False,
        'synonyms': ['visible damage?', 'visible damage', 'damage', 'damaged']
    },
    'missing_parts': {
        'label': 'Missing Parts?',
        'mandatory': False,
        'synonyms': ['missing parts?', 'missing parts', 'incomplete']
    },
    'warranty_available': {
        'label': 'Warranty Available?',
        'mandatory': False,
        'synonyms': ['warranty available?', 'warranty available', 'warranty', 'guarantee']
    },
    'inspection_available': {
        'label': 'Inspection Available?',
        'mandatory': False,
        'synonyms': ['inspection available?', 'inspection available', 'inspection', 'open for inspection']
    },
    'safety_certificate_available': {
        'label': 'Safety Certificate Available?',
        'mandatory': False,
        'synonyms': ['safety certificate available?', 'safety certificate available', 'safety certificate', 'certificate available']
    },
    'certificate_type': {
        'label': 'Certificate Type',
        'mandatory': False,
        'synonyms': ['certificate type', 'cert type', 'certification']
    },
    'regulatory_approval': {
        'label': 'Regulatory Approval',
        'mandatory': False,
        'synonyms': ['regulatory approval', 'compliance', 'approvals', 'iso / ce']
    },
    'hazardous_material': {
        'label': 'Hazardous Material?',
        'mandatory': False,
        'synonyms': ['hazardous material?', 'hazardous material', 'hazmat', 'hazardous']
    },
    'special_handling_required': {
        'label': 'Special Handling Required?',
        'mandatory': False,
        'synonyms': ['special handling required?', 'special handling required', 'special handling']
    },
    'recyclable': {
        'label': 'Recyclable?',
        'mandatory': False,
        'synonyms': ['recyclable?', 'recyclable', 'eco friendly']
    },
    'estimated_product_life_remaining': {
        'label': 'Estimated Product Life Remaining',
        'mandatory': False,
        'synonyms': ['estimated product life remaining', 'remaining life', 'life remaining', 'useful life']
    },
    'seller_custom_field_1': {
        'label': 'Seller Custom Field 1',
        'mandatory': False,
        'synonyms': ['seller custom field 1', 'custom field 1', 'custom 1']
    },
    'seller_custom_field_2': {
        'label': 'Seller Custom Field 2',
        'mandatory': False,
        'synonyms': ['seller custom field 2', 'custom field 2', 'custom 2']
    }
}


def parse_spreadsheet(file_obj, manual_mapping=None):
    """
    Parses a spreadsheet (.xlsx or .csv) in-memory, auto-maps all 45 standard fields,
    validates mandatory fields without skipping any rows, cleans data types,
    and returns full items payload for datasets of any size (100, 1000, 5000+ rows).
    """
    filename = getattr(file_obj, 'name', 'file.xlsx').lower()

    try:
        if filename.endswith('.csv'):
            df_raw = pd.read_csv(file_obj, header=None, nrows=25)
            header_row_idx = _find_header_row(df_raw)
            file_obj.seek(0)
            df = pd.read_csv(file_obj, header=header_row_idx)
        elif filename.endswith('.xlsx') or filename.endswith('.xls'):
            file_obj.seek(0)
            target_sheet_name = None
            try:
                xl = pd.ExcelFile(file_obj)
                sheet_names = xl.sheet_names

                # Target sheet selection algorithm: prefer 'Inventory' sheet
                for sname in sheet_names:
                    s_lower = str(sname).strip().lower()
                    if s_lower in ['inventory', 'inventory items', 'products', 'product list', 'stock', 'manifest', 'data']:
                        target_sheet_name = sname
                        break
                    elif 'inventory' in s_lower or 'product' in s_lower or 'stock' in s_lower:
                        target_sheet_name = sname
                        break

                if target_sheet_name is None and len(sheet_names) > 1:
                    first_s_lower = str(sheet_names[0]).strip().lower()
                    if any(kw in first_s_lower for kw in ['directory', 'reference', 'instruction', 'taxonomy', 'guide', 'readme', 'help']):
                        target_sheet_name = sheet_names[1]

                if target_sheet_name is None:
                    target_sheet_name = 0
            except Exception:
                target_sheet_name = 0

            file_obj.seek(0)
            df_raw = pd.read_excel(file_obj, sheet_name=target_sheet_name, header=None, nrows=25)
            header_row_idx = _find_header_row(df_raw)
            file_obj.seek(0)
            df = pd.read_excel(file_obj, sheet_name=target_sheet_name, header=header_row_idx)
        else:
            raise ValueError("Unsupported file format. Please upload .csv or .xlsx")
    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")

    raw_columns = df.columns.tolist()

    mapping = {}

    # Manual mapping override if supplied
    if manual_mapping:
        if isinstance(manual_mapping, str):
            try:
                manual_mapping = json.loads(manual_mapping)
            except json.JSONDecodeError:
                manual_mapping = {}
        for internal_col, sheet_col in manual_mapping.items():
            if sheet_col in raw_columns:
                mapping[internal_col] = sheet_col

    # Auto-map fields against synonyms
    for internal_col, spec in FIELD_SPECIFICATIONS.items():
        if internal_col in mapping:
            continue

        synonyms = spec['synonyms']
        for sheet_col in raw_columns:
            if not isinstance(sheet_col, str):
                continue

            sheet_col_clean = re.sub(r'\s+', ' ', sheet_col).strip().lower()

            # 1. Exact match
            if sheet_col_clean in synonyms or sheet_col_clean == internal_col:
                mapping[internal_col] = sheet_col
                break

            # 2. Word boundary match
            matched = False
            for syn in synonyms:
                pattern = r'\b' + re.escape(syn) + r'\b'
                if re.search(pattern, sheet_col_clean):
                    mapping[internal_col] = sheet_col
                    matched = True
                    break
            if matched:
                break

    # Header Validation: Check which mandatory fields are missing from sheet mapping
    missing_mandatory_headers = []
    header_errors = []
    for internal_col, spec in FIELD_SPECIFICATIONS.items():
        if spec['mandatory'] and internal_col not in mapping:
            missing_mandatory_headers.append({
                'key': internal_col,
                'label': spec['label']
            })
            header_errors.append(f"Header Error: Mandatory column '{spec['label']}' is missing from the Excel sheet.")

    # Filter out completely blank rows
    df = df.dropna(how='all')

    parsed_items = []
    row_errors = []

    for index, row in df.iterrows():
        row_num = len(parsed_items) + 1  # 1-indexed count of parsed product items

        # Check for explicit summary / footer / instruction rows (e.g., "Grand Total", "Summary", Taxonomy guidelines)
        first_val = str(row.iloc[0]).strip().lower() if len(row) > 0 and pd.notna(row.iloc[0]) else ""
        if first_val in ['grand total', 'summary', 'totals']:
            continue
        if first_val == 'total':
            second_val = str(row.iloc[1]).strip().lower() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
            if not second_val or second_val in ['units', 'value', 'items', '']:
                continue

        # Filter out spreadsheet template instruction & header rows
        row_str_full = " ".join([str(v).lower() for v in row.values if pd.notna(v)])
        instruction_keywords = [
            'reference directory', 'classification taxonomy', 'select a valid product category',
            'total categories', 'ensure consistent reporting', 'master classification',
            'inventory tab', 'mapped subcategory', 'taxonomy for all inventory'
        ]
        if any(kw in row_str_full for kw in instruction_keywords):
            continue

        item = {}
        missing_row_fields = []

        for internal_col, spec in FIELD_SPECIFICATIONS.items():
            sheet_col = mapping.get(internal_col)
            val = None
            if sheet_col and sheet_col in df.columns:
                val = row[sheet_col]
                if pd.isna(val):
                    val = None
                elif hasattr(val, 'item'):
                    val = val.item()

            # String cleanup
            if isinstance(val, str):
                val = val.strip()
                if val == "":
                    val = None

            # Type conversion for numeric fields
            if internal_col in ['available_quantity', 'moq', 'original_price', 'asking_price',
                                'quantity_per_box', 'number_of_boxes', 'net_weight_per_unit',
                                'gross_weight_per_unit', 'length', 'width', 'height', 'total_weight',
                                'pallet_count', 's_no', 'year_of_manufacture']:
                if val is not None:
                    val = _clean_numeric(val)

            # Check mandatory vs optional field validation (Mandatory fields only)
            if spec['mandatory']:
                is_empty = (val is None or val == "") or (internal_col in ['available_quantity', 'moq'] and val == 0)
                if is_empty:
                    missing_row_fields.append(spec['label'])
                    item[internal_col] = None
                else:
                    item[internal_col] = val
            else:
                if val is None or val == "":
                    item[internal_col] = "NIL"
                else:
                    item[internal_col] = val

        # Calculate total asking value for row safely
        avail_qty = item.get('available_quantity') if isinstance(item.get('available_quantity'), (int, float)) else 0
        ask_price = item.get('asking_price') if isinstance(item.get('asking_price'), (int, float)) else (item.get('original_price') if isinstance(item.get('original_price'), (int, float)) else 0.0)
        item['calculated_total_value'] = round(avail_qty * ask_price, 2)

        # Format S.No cleanly (convert float like 1.0 to 1, or fallback to sequential index)
        if item.get('s_no') is not None and item.get('s_no') != 0:
            try:
                s_val = float(item['s_no'])
                item['s_no'] = int(s_val) if s_val.is_integer() else s_val
            except (ValueError, TypeError):
                item['s_no'] = row_num
        else:
            item['s_no'] = row_num

        # Convert whole float numbers to integers for count fields
        for int_key in ['available_quantity', 'moq', 'quantity_per_box', 'number_of_boxes', 'pallet_count', 'year_of_manufacture']:
            if item.get(int_key) is not None:
                try:
                    f_val = float(item[int_key])
                    if f_val.is_integer():
                        item[int_key] = int(f_val)
                except (ValueError, TypeError):
                    pass

        # Skip completely blank or placeholder product rows
        p_name_val = str(item.get('product_name') or '').strip().lower()
        p_desc_val = str(item.get('product_description') or '').strip().lower()
        p_brand_val = str(item.get('brand') or '').strip().lower()
        p_model_val = str(item.get('model_part_number') or '').strip().lower()
        empty_placeholders = {'', '-', 'nil', 'none', 'null', 'nan', 'n/a'}
        if (p_name_val in empty_placeholders) and (p_desc_val in empty_placeholders) and (p_brand_val in empty_placeholders) and (p_model_val in empty_placeholders):
            continue

        if missing_row_fields:
            row_errors.append({
                'row': row_num,
                'missing_fields': missing_row_fields,
                'message': f"Row {row_num}: Mandatory data missing for field(s): {', '.join(missing_row_fields)}"
            })

        parsed_items.append(item)

    # Compute Summary Stats across ALL items
    total_items = len(parsed_items)
    total_units = sum(item.get('available_quantity') or 0 for item in parsed_items)
    total_asking_value = sum(item.get('calculated_total_value') or 0.0 for item in parsed_items)

    summary = {
        'total_items': total_items,
        'total_units': total_units,
        'total_retail_value': total_asking_value,
        'total_asking_value': total_asking_value,
        'valid_items_count': total_items - len(row_errors),
        'invalid_items_count': len(row_errors),
    }

    is_valid = len(missing_mandatory_headers) == 0 and len(row_errors) == 0

    return {
        'is_valid': is_valid,
        'header_errors': header_errors,
        'missing_mandatory_columns': missing_mandatory_headers,
        'row_errors': row_errors,
        'detected_columns': raw_columns,
        'mapping': mapping,
        'summary': summary,
        'preview_items': parsed_items,
        'all_items': parsed_items
    }


def _find_header_row(df_raw):
    """
    Scans the top rows to find the actual table header row using a smart scoring algorithm.
    Header terms matching known column names are heavily weighted so data rows never steal the header index.
    """
    all_known_synonyms = set()
    for spec in FIELD_SPECIFICATIONS.values():
        for syn in spec['synonyms']:
            all_known_synonyms.add(syn.lower())

    best_idx = 0
    max_score = -1

    for idx, row in df_raw.iterrows():
        non_null_vals = [str(v).strip().lower() for v in row.values if pd.notna(v) and str(v).strip()]
        if not non_null_vals:
            continue

        header_matches = 0
        for val in non_null_vals:
            val_clean = re.sub(r'\s+', ' ', val).strip()
            if val_clean in all_known_synonyms or any(syn in val_clean for syn in all_known_synonyms if len(syn) > 2):
                header_matches += 1

        # Give 100 points per matched header keyword + non-null count
        score = (header_matches * 100) + len(non_null_vals)
        if score > max_score:
            max_score = score
            best_idx = idx

    return best_idx


def _clean_numeric(val):
    if isinstance(val, (int, float)):
        if math.isnan(val):
            return 0.0
        return val
    if isinstance(val, str):
        clean_str = re.sub(r'[$,\s]', '', val)
        try:
            val_num = float(clean_str)
            if math.isnan(val_num):
                return 0.0
            return val_num
        except ValueError:
            return 0.0
    return 0.0
