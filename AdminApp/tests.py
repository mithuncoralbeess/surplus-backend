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
            "confirm_password": "supersecretpassword",
        }
        response = self.client.post("/admin/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

        admin = AdminDetails.objects.get(email="super@gmail.com")
        self.assertEqual(admin.account_type, "SuperAdmin")
        self.assertEqual(admin.web_is_active, "live")
        self.assertTrue(":" in admin.pass_word)  # Salted format <hash>:<salt>
        self.assertTrue(admin.check_password("supersecretpassword"))

    def test_standard_admin_registration(self):
        """
        Standard user registration assigns Admin role.
        """
        payload = {
            "username": "adminuser",
            "email": "admin@gmail.com",
            "firstname": "Standard",
            "lastname": "Admin",
            "confirm_password": "password123",
        }
        response = self.client.post("/admin/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        admin = AdminDetails.objects.get(email="admin@gmail.com")
        self.assertEqual(admin.account_type, "Admin")
        self.assertTrue(admin.status)

    def test_duplicate_registration_validation(self):
        """
        Duplicate username/email is rejected with bad request.
        """
        payload = {
            "username": "testuser",
            "email": "test@gmail.com",
            "firstname": "Test",
            "lastname": "User",
            "confirm_password": "password123",
        }
        self.client.post("/admin/register/", payload, format="json")
        response = self.client.post("/admin/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

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
                "confirm_password": "mypassword",
            },
            format="json",
        )

        # Login
        login_response = self.client.post(
            "/admin/login/",
            {"user_email": "super@gmail.com", "user_pass": "mypassword"},
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
                "confirm_password": "oldpassword",
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
                "new_password": "newsuperpassword",
                "confirm_password": "newsuperpassword",
            },
            format="json",
        )
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_res.data["success"])

        # Reload admin from db
        admin.refresh_from_db()
        self.assertEqual(admin.session_version, initial_version + 1)
        self.assertTrue(admin.check_password("newsuperpassword"))
        self.assertFalse(admin.check_password("oldpassword"))

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



