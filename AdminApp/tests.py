from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import AdminDetails, AdminPasswordResetOTP


class AdminAppAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_super_admin_registration(self):
        """
        Registering with super@gmail.com assigns SuperAdmin role and live web state.
        """
        payload = {
            "username": "superadmin",
            "email": "super@gmail.com",
            "firstname": "Super",
            "lastname": "User",
            "confirm_password": "SuperSecret@2026!",
        }
        response = self.client.post("/admin/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

        admin = AdminDetails.objects.get(email="super@gmail.com")
        self.assertEqual(admin.account_type, "SuperAdmin")
        self.assertEqual(admin.web_is_active, "live")
        self.assertTrue(admin.pass_word.startswith("pbkdf2_"))  # Django PBKDF2 hash
        self.assertTrue(admin.check_password("SuperSecret@2026!"))

    def test_standard_admin_registration(self):
        """
        Standard user registration assigns Admin role, full_name, and sets status=False (requires SuperAdmin approval).
        """
        payload = {
            "full_name": "Standard Admin",
            "email": "admin@gmail.com",
            "confirm_password": "AdminPass@2026!",
        }
        response = self.client.post("/admin/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["pending_approval"])

        admin = AdminDetails.objects.get(email="admin@gmail.com")
        self.assertEqual(admin.account_type, "Admin")
        self.assertEqual(admin.full_name, "Standard Admin")
        self.assertFalse(admin.status)  # Pending SuperAdmin approval

    def test_admin_signup_and_superadmin_approval_flow(self):
        """
        Tests the complete self-signup -> pending block -> SuperAdmin approval -> successful login workflow.
        """
        # 1. Access signup page (HTML)
        signup_page_res = self.client.get("/admin/signup/")
        self.assertEqual(signup_page_res.status_code, status.HTTP_200_OK)

        # 2. Self-signup with full_name, email, password, confirm_password
        signup_payload = {
            "full_name": "Alex Mercer",
            "email": "alex.mercer@surplus.com",
            "password": "SecurePassword@999",
            "confirm_password": "SecurePassword@999",
        }
        signup_res = self.client.post("/admin/signup/", signup_payload, format="json")
        self.assertEqual(signup_res.status_code, status.HTTP_201_CREATED)
        res_data = getattr(signup_res, "data", None) or signup_res.json()
        self.assertTrue(res_data["pending_approval"])

        new_admin = AdminDetails.objects.get(email="alex.mercer@surplus.com")
        self.assertFalse(new_admin.status)
        self.assertEqual(new_admin.full_name, "Alex Mercer")

        # 3. Attempting to log in while pending approval MUST be blocked with 403 Forbidden
        login_res_blocked = self.client.post(
            "/admin/login/",
            {"user_email": "alex.mercer@surplus.com", "user_pass": "SecurePassword@999"},
            format="json",
        )
        self.assertEqual(login_res_blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("pending SuperAdmin approval", login_res_blocked.data["message"])

        # 4. SuperAdmin logs in and approves new_admin
        superadmin = AdminDetails.objects.create(
            username="super_master",
            email="super@gmail.com",
            account_type="SuperAdmin",
            status=True,
            session_version=1,
        )
        session = self.client.session
        session["adminid"] = superadmin.id
        session["session_version"] = 1
        session.save()

        # Check manage admins page
        manage_page_res = self.client.get("/admin/admins/")
        self.assertEqual(manage_page_res.status_code, status.HTTP_200_OK)

        # SuperAdmin calls approval API
        approval_res = self.client.post(
            f"/admin/api/admins/{new_admin.id}/status/",
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(approval_res.status_code, status.HTTP_200_OK)
        self.assertTrue(approval_res.data["new_status"])

        new_admin.refresh_from_db()
        self.assertTrue(new_admin.status)

        # Clear SuperAdmin session to test new_admin login
        session = self.client.session
        session.flush()

        # 5. Now approved admin can log in successfully!
        login_res_success = self.client.post(
            "/admin/login/",
            {"user_email": "alex.mercer@surplus.com", "user_pass": "SecurePassword@999"},
            format="json",
        )
        self.assertEqual(login_res_success.status_code, status.HTTP_200_OK)
        self.assertTrue(login_res_success.data["success"])

    def test_duplicate_registration_validation(self):
        """
        Duplicate username/email is rejected with bad request.
        """
        payload = {
            "username": "testuser",
            "email": "test@gmail.com",
            "firstname": "Test",
            "lastname": "User",
            "confirm_password": "DuplicateTestPass@2026!",
        }
        self.client.post("/admin/register/", payload, format="json")
        response = self.client.post("/admin/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

    def test_admin_notification_system_endpoints(self):
        """
        Tests the admin notification lifecycle: creation, listing, marking read, and deleting.
        """
        from .models import AdminNotification
        from .services import create_admin_notification

        superadmin = AdminDetails.objects.create(
            username="super_notif_tester",
            email="super@gmail.com",
            account_type="SuperAdmin",
            status=True,
            session_version=1,
        )
        session = self.client.session
        session["adminid"] = superadmin.id
        session["session_version"] = 1
        session.save()

        # 1. Create notifications
        notif1 = create_admin_notification(
            title="System Alert 1",
            message="Test alert message",
            notification_type="SYSTEM",
            for_superadmins_only=True,
        )
        notif2 = create_admin_notification(
            title="Registration Notice",
            message="Someone registered",
            notification_type="ADMIN_REGISTRATION",
            for_superadmins_only=True,
        )

        # 2. List notifications via API
        list_res = self.client.get("/admin/api/notifications/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertTrue(list_res.data["success"])
        self.assertGreaterEqual(list_res.data["unread_count"], 2)

        # 3. View notification center HTML page
        page_res = self.client.get("/admin/notifications/")
        self.assertEqual(page_res.status_code, status.HTTP_200_OK)

        # 4. Mark notif1 as read
        read_res = self.client.post(f"/admin/api/notifications/{notif1.id}/read/")
        self.assertEqual(read_res.status_code, status.HTTP_200_OK)
        notif1.refresh_from_db()
        self.assertTrue(notif1.is_read)

        # 5. Mark all as read
        read_all_res = self.client.post("/admin/api/notifications/read-all/")
        self.assertEqual(read_all_res.status_code, status.HTTP_200_OK)
        self.assertEqual(read_all_res.data["unread_count"], 0)
        notif2.refresh_from_db()
        self.assertTrue(notif2.is_read)

        # 6. Delete notification
        del_res = self.client.post(f"/admin/api/notifications/{notif1.id}/delete/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(AdminNotification.objects.filter(id=notif1.id).exists())

    def test_admin_login_and_session_setup(self):
        """
        Admin login sets session and returns role-based routing.
        """
        # Register SuperAdmin
        self.client.post(
            "/admin/register/",
            {
                "username": "superadmin",
                "email": "super@gmail.com",
                "confirm_password": "SuperLogin@2026!",
            },
            format="json",
        )

        # Login
        login_response = self.client.post(
            "/admin/login/",
            {"user_email": "super@gmail.com", "user_pass": "SuperLogin@2026!"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertTrue(login_response.data["success"])
        self.assertEqual(login_response.data["redirect_route"], "adminDashBoard")

        # Session profile check
        me_response = self.client.get("/admin/me/")
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["admin"]["email"], "super@gmail.com")

    def test_super_admin_password_reset_and_otp_verification(self):
        """
        Password reset generates OTP, validates within window, and increments session_version.
        """
        self.client.post(
            "/admin/register/",
            {
                "username": "superadmin",
                "email": "super@gmail.com",
                "confirm_password": "OldPassword@2026!",
            },
            format="json",
        )

        admin = AdminDetails.objects.get(email="super@gmail.com")
        initial_version = admin.session_version

        # Request Password Reset OTP
        reset_res = self.client.post(
            "/admin/password-reset/",
            {"email": "super@gmail.com"},
            format="json",
        )
        self.assertEqual(reset_res.status_code, status.HTTP_200_OK)

        otp_record = AdminPasswordResetOTP.objects.get(email="super@gmail.com", is_used=False)
        self.assertEqual(len(otp_record.otp), 6)

        # Verify OTP and set new password
        verify_res = self.client.post(
            "/admin/verify-otp/",
            {
                "email": "super@gmail.com",
                "otp": otp_record.otp,
                "new_password": "NewSuperPassword@2026!",
                "confirm_password": "NewSuperPassword@2026!",
            },
            format="json",
        )
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_res.data["success"])

        # Reload admin from db
        admin.refresh_from_db()
        self.assertEqual(admin.session_version, initial_version + 1)
        self.assertTrue(admin.check_password("NewSuperPassword@2026!"))
        self.assertFalse(admin.check_password("OldPassword@2026!"))

    def test_admin_password_policy_enforcement(self):
        """
        Tests that passwords violating the password policy are rejected with 400 Bad Request,
        while compliant passwords succeed.
        """
        # 1. Too short (< 8 chars)
        res = self.client.post("/admin/register/", {
            "email": "user1@example.com",
            "full_name": "Test User",
            "confirm_password": "Sh1!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("at least 8 characters", str(res.data))

        # 2. Missing uppercase
        res = self.client.post("/admin/register/", {
            "email": "user2@example.com",
            "full_name": "Test User",
            "confirm_password": "lowercase123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("uppercase letter", str(res.data))

        # 3. Missing lowercase
        res = self.client.post("/admin/register/", {
            "email": "user3@example.com",
            "full_name": "Test User",
            "confirm_password": "UPPERCASE123!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lowercase letter", str(res.data))

        # 4. Missing number
        res = self.client.post("/admin/register/", {
            "email": "user4@example.com",
            "full_name": "Test User",
            "confirm_password": "NoNumbersHere!@",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("digit" in str(res.data).lower() or "number" in str(res.data).lower())

        # 5. Missing special character
        res = self.client.post("/admin/register/", {
            "email": "user5@example.com",
            "full_name": "Test User",
            "confirm_password": "NoSpecialChar123",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("special character", str(res.data).lower())

        # 6. Compliant password succeeds
        res = self.client.post("/admin/register/", {
            "email": "user6@example.com",
            "full_name": "Test User",
            "confirm_password": "ValidPassword@2026!",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data["success"])

    def test_lot_batch_id_lookup_and_pending_view(self):
        """
        Tests that Lot model supports batch_id lookup property and /admin/enquiries/lots/pending/ renders cleanly.
        """
        from .models import Lot
        lot = Lot.objects.create(
            title="Test Industrial Lot",
            enquiry_status="pending"
        )
        self.assertTrue(lot.lot_number.startswith("LOT-"))
        self.assertEqual(lot.batch_id, lot.lot_number)

        # Login as SuperAdmin
        admin = AdminDetails.objects.create(
            username="supertest",
            email="super@gmail.com",
            account_type="SuperAdmin",
            status=True,
            session_version=1,
        )
        session = self.client.session
        session["adminid"] = admin.id
        session["session_version"] = 1
        session.save()

        response = self.client.get("/admin/enquiries/lots/pending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, lot.lot_number)

    def test_excel_header_and_mandatory_data_validation(self):
        """
        Tests header validation and row data validation for mandatory fields.
        """
        import io
        import pandas as pd
        from lots.importer import parse_spreadsheet

        # Case 1: Missing Mandatory Header (e.g. missing 'Subcategory*')
        invalid_header_df = pd.DataFrame([{
            'S.No*': 1,
            'Product Name*': 'Test Widget',
            'Product Description*': 'Widget Description',
            'Product Category*': 'Electronics',
            'Available Quantity*': 100,
        }])
        buf_inv_h = io.BytesIO()
        invalid_header_df.to_excel(buf_inv_h, sheet_name='Inventory', index=False)
        buf_inv_h.name = 'test.xlsx'
        buf_inv_h.seek(0)
        res_inv_h = parse_spreadsheet(buf_inv_h)
        self.assertFalse(res_inv_h['is_valid'])
        self.assertTrue(len(res_inv_h['missing_mandatory_columns']) > 0)
        self.assertTrue(any(c['key'] == 'subcategory' for c in res_inv_h['missing_mandatory_columns']))

        # Case 2: Missing Mandatory Data in Row (e.g. empty Product Description*)
        invalid_row_df = pd.DataFrame([{
            'S.No*': 1,
            'Product Name*': 'Test Widget',
            'Product Description*': '',
            'Product Category*': 'Electronics',
            'Subcategory*': 'Gadgets',
            'Available Quantity*': 100,
        }])
        buf_inv_r = io.BytesIO()
        invalid_row_df.to_excel(buf_inv_r, sheet_name='Inventory', index=False)
        buf_inv_r.name = 'test.xlsx'
        buf_inv_r.seek(0)
        res_inv_r = parse_spreadsheet(buf_inv_r)
        self.assertFalse(res_inv_r['is_valid'])
        self.assertTrue(len(res_inv_r['row_errors']) > 0)
        self.assertIn("Product Description*", res_inv_r['row_errors'][0]['message'])

        # Case 3: Fully Valid Excel File
        valid_df = pd.DataFrame([{
            'S.No*': 1,
            'Product Name*': 'Valid Widget',
            'Product Description*': 'Valid Description',
            'Product Category*': 'Industrial',
            'Subcategory*': 'Tools',
            'Available Quantity*': 50,
        }])
        buf_valid = io.BytesIO()
        valid_df.to_excel(buf_valid, sheet_name='Inventory', index=False)
        buf_valid.name = 'test.xlsx'
        buf_valid.seek(0)
        res_valid = parse_spreadsheet(buf_valid)
        self.assertTrue(res_valid['is_valid'])
        self.assertEqual(len(res_valid['missing_mandatory_columns']), 0)
        self.assertEqual(len(res_valid['row_errors']), 0)

        # Case 4: Missing 'Inventory' tab in Excel file
        missing_tab_df = pd.DataFrame([{'Product Name*': 'Widget'}])
        buf_missing_tab = io.BytesIO()
        missing_tab_df.to_excel(buf_missing_tab, sheet_name='Sheet1', index=False)
        buf_missing_tab.name = 'test.xlsx'
        buf_missing_tab.seek(0)
        with self.assertRaises(ValueError) as ctx:
            parse_spreadsheet(buf_missing_tab)
        self.assertIn("must contain an 'Inventory' tab", str(ctx.exception))

        # Case 5: Unrelated other format sheet
        other_format_df = pd.DataFrame([{
            'EmpID': 101,
            'Department': 'HR',
            'Salary': 60000
        }])
        buf_other = io.BytesIO()
        other_format_df.to_excel(buf_other, sheet_name='Inventory', index=False)
        buf_other.name = 'test.xlsx'
        buf_other.seek(0)
        res_other = parse_spreadsheet(buf_other)
        self.assertFalse(res_other['is_valid'])
        self.assertTrue(any('Invalid Sheet Structure' in err for err in res_other['header_errors']))

    def test_save_lot_products_api(self):
        """
        Tests save_lot_products_api endpoint saves extracted products into LotProduct model records.
        """
        from .models import Lot, LotProduct
        lot = Lot.objects.create(title="Unsaved Lot", enquiry_status="pending")
        
        # Login
        admin = AdminDetails.objects.create(
            username="supertest2",
            email="super2@gmail.com",
            account_type="SuperAdmin",
            status=True,
            session_version=1,
        )
        session = self.client.session
        session["adminid"] = admin.id
        session["session_version"] = 1
        session.save()

        products_payload = [
            {"s_no": 1, "product_name": "Widget A", "available_quantity": 20, "product_condition": "New"},
            {"s_no": 2, "product_name": "Widget B", "available_quantity": 10, "product_condition": "Used"},
        ]

        response = self.client.post(
            f"/admin/api/enquiries/lots/{lot.id}/save-products/",
            {"products": products_payload},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["saved_count"], 2)

        lot_products = LotProduct.objects.filter(lot=lot)
        self.assertEqual(lot_products.count(), 2)

    def test_seller_enquiry_edit_api_pricing_and_fields(self):
        """
        Verify seller_enquiry_edit_api:
        - Only liquidation price and msrp are editable in pricing
        - Price is auto-calculated as liquidation_price * 1.10
        - If liquidation discount is below 60% of MSRP, a warning is returned
        - All fields properly update the Product model in DB and raw_data
        """
        from .models import Product, MainCategory, SubCategory
        from decimal import Decimal

        admin = AdminDetails.objects.create(
            username="admin_edit_tester",
            email="tester_edit@gmail.com",
            account_type="SuperAdmin",
            status=True,
            session_version=1,
        )
        session = self.client.session
        session["adminid"] = admin.id
        session["session_version"] = 1
        session.save()

        main_cat = MainCategory.objects.create(name="Electronics")
        sub_cat = SubCategory.objects.create(name="Laptops", main_category=main_cat)

        prod = Product.objects.create(
            product_name="Original Name",
            liquidating_price=Decimal("100.00"),
            msrp=Decimal("200.00"),
            currency="USD",
            quantity=5
        )

        # 1. Edit with liquidation price = 50, msrp = 100 (which is 50% < 60% of MSRP -> triggers warning)
        # Attempt to pass a custom "price" of 999 to test that it is ignored
        payload = {
            "title": "Updated Laptop Name",
            "brand": "Dell",
            "model_no": "XPS-15",
            "subcategory_id": sub_cat.id,
            "liquidating_price": "50.00",
            "price": "999.00",  # Must NOT overwrite auto-calculated price!
            "msrp": "100.00",
            "stock_quantity": 12,
            "condition": "Like New",
            "currency": "USD",
            "inventory_location": "Dubai Warehouse",
            "is_available_for_offers": True,
            "is_featured": True
        }

        res = self.client.post(f"/admin/api/enquiries/seller/{prod.id}/edit/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertTrue(data["success"])
        # Price must be 50 * 1.10 = 55.00
        self.assertEqual(data["price"], 55.0)
        self.assertEqual(data["liquidating_price"], 50.0)
        # Warning because discount 50% < 60% policy target
        self.assertIsNotNone(data["warning"])
        self.assertIn("below the recommended 60%", data["warning"])

        # Reload from DB
        prod.refresh_from_db()
        self.assertEqual(prod.product_name, "Updated Laptop Name")
        self.assertEqual(prod.brand_name, "Dell")
        self.assertEqual(prod.model_no, "XPS-15")
        self.assertEqual(prod.subcategory, sub_cat)
        self.assertEqual(prod.quantity, 12)
        self.assertEqual(prod.liquidating_price, Decimal("50.00"))
        self.assertEqual(prod.msrp, Decimal("100.00"))
        self.assertEqual(prod.current_price, Decimal("55.00"))
        self.assertEqual(prod.condition, "Like New")
        self.assertTrue(prod.is_available_for_offers)
        self.assertTrue(prod.is_featured)
        self.assertEqual(prod.raw_data.get("price"), "55.00")
        self.assertEqual(prod.raw_data.get("liquidating_price"), "50.00")

    def test_lot_enquiry_edit_api_pricing_and_fields(self):
        """
        Verify lot_enquiry_edit_api:
        - Only liquidation price and msrp are editable in pricing
        - Price is auto-calculated as liquidation_price * 1.10
        - If liquidation discount is below 60% of MSRP, a warning is returned
        - All fields properly update the Lot model in DB and raw_data
        """
        from .models import Lot, MainCategory, SubCategory
        from decimal import Decimal

        admin = AdminDetails.objects.create(
            username="admin_lot_tester",
            email="tester_lot@gmail.com",
            account_type="SuperAdmin",
            status=True,
            session_version=1,
        )
        session = self.client.session
        session["adminid"] = admin.id
        session["session_version"] = 1
        session.save()

        main_cat = MainCategory.objects.create(name="Networking")
        sub_cat = SubCategory.objects.create(name="Switches", main_category=main_cat)

        lot = Lot.objects.create(
            title="Old Switch Lot",
            total_est_retail_value_msrp=Decimal("1000.00"),
            ask_price_surplus_payout=Decimal("500.00"),
            currency="USD"
        )

        # Edit with liquidation price = 500, msrp = 1000 (discount 50% < 60% policy target -> triggers warning)
        # Attempt to pass custom price of 9999 to test that it is ignored
        payload = {
            "title": "Cisco Catalyst Batch",
            "subcategory_id": sub_cat.id,
            "liquidation_price": "500.00",
            "price": "9999.00",  # Must be ignored
            "msrp": "1000.00",
            "currency": "USD",
            "condition": "Surplus",
            "distinct_skus": "15",
            "total_units": "150",
            "inventory_location": "Riyadh Logistics Center"
        }

        res = self.client.post(f"/admin/api/enquiries/lots/{lot.id}/edit/", payload, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertTrue(data["success"])
        # Price must be 500 * 1.10 = 550.00
        self.assertEqual(data["price"], 550.0)
        self.assertEqual(data["liquidation_price"], 500.0)
        # Warning because discount 50% < 60% policy target
        self.assertIsNotNone(data["warning"])
        self.assertIn("below the recommended 60%", data["warning"])

        # Reload from DB
        lot.refresh_from_db()
        self.assertEqual(lot.title, "Cisco Catalyst Batch")
        self.assertEqual(lot.ask_price_surplus_payout, Decimal("400.00"))
        self.assertEqual(lot.total_est_retail_value_msrp, Decimal("1000.00"))
        self.assertEqual(lot.condition, "Surplus")
        self.assertEqual(lot.number_of_distinct_skus, 15)
        self.assertEqual(lot.total_units_quantity, 150)
        self.assertEqual(lot.raw_data.get("price"), 440.0)
        self.assertEqual(lot.raw_data.get("liquidation_price"), 400.0)
        self.assertEqual(lot.raw_data.get("category"), "Switches")



