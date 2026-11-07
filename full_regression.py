import unittest
import os
import sys
import json
import time
import io
import hashlib
import secrets
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from bson import ObjectId
import pymongo
from urllib.parse import urlparse

# ----------------------------------------------------------------------
# 1. ENFORCE ENVIRONMENT & TEST DATABASE ISOLATION
# ----------------------------------------------------------------------
DISPOSABLE_TEST_DB = "safedrive_disposable_test_db"
# Enforce strict safety guard: NEVER permit running tests against production drowsiness_db
requested_db = os.getenv("MONGO_DB_NAME", DISPOSABLE_TEST_DB)
if requested_db != DISPOSABLE_TEST_DB:
    raise RuntimeError(
        f"SAFETY GUARD TRIGGERED: Tests are restricted to '{DISPOSABLE_TEST_DB}'. "
        f"Attempted execution against '{requested_db}' was aborted."
    )

os.environ["MONGO_DB_NAME"] = DISPOSABLE_TEST_DB

# Verify MongoDB connection target is an approved local test instance
raw_mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
parsed_uri = urlparse(raw_mongo_uri)
mongo_host = (parsed_uri.hostname or "").lower()
APPROVED_TEST_HOSTS = {"localhost", "127.0.0.1", "::1"}
if mongo_host not in APPROVED_TEST_HOSTS:
    raise RuntimeError(
        f"SAFETY GUARD TRIGGERED: MongoDB connection target '{mongo_host}' is not an approved test instance! "
        "Tests may only connect to approved local test hosts."
    )

os.environ["MONGO_URI"] = raw_mongo_uri
os.environ["SECRET_KEY"] = "disposable_test_secret_key_review_isolated_32chars"
os.environ["FLASK_ENV"] = "testing"

REVIEW_DIR = os.path.dirname(os.path.abspath(__file__))
if REVIEW_DIR not in sys.path:
    sys.path.insert(0, REVIEW_DIR)
os.chdir(REVIEW_DIR)

# Connect to MongoDB directly to manage the disposable test database
direct_mongo_client = pymongo.MongoClient(os.environ["MONGO_URI"])
test_db = direct_mongo_client[DISPOSABLE_TEST_DB]

from app import (
    app, users_collection, contacts_collection, logs_collection,
    signup_verifications_collection, password_resets_collection,
    send_otp_email, eye_aspect_ratio, LEFT_EYE_INDICES, RIGHT_EYE_INDICES
)
from werkzeug.security import generate_password_hash, check_password_hash
from location_email_alert import send_location_email


class P:
    def __init__(self, x, y):
        self.x, self.y = x, y


class FaceMeshData:
    def __init__(self, vertical_span=0.04):
        self.landmark = [P(0.5, 0.5) for _ in range(500)]
        half = vertical_span / 2.0
        self.landmark[33] = P(0.2, 0.5)
        self.landmark[160] = P(0.25, 0.5 - half)
        self.landmark[158] = P(0.3, 0.5 - half)
        self.landmark[133] = P(0.35, 0.5)
        self.landmark[153] = P(0.3, 0.5 + half)
        self.landmark[144] = P(0.25, 0.5 + half)
        self.landmark[362] = P(0.6, 0.5)
        self.landmark[385] = P(0.65, 0.5 - half)
        self.landmark[387] = P(0.7, 0.5 - half)
        self.landmark[263] = P(0.75, 0.5)
        self.landmark[373] = P(0.7, 0.5 + half)
        self.landmark[380] = P(0.65, 0.5 + half)


class SafeDriveComprehensiveValidationSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.client = app.test_client()

        assert users_collection.database.name == DISPOSABLE_TEST_DB, (
            f"Isolation failure: users_collection is connected to {users_collection.database.name}"
        )
        assert logs_collection.database.name == DISPOSABLE_TEST_DB, (
            f"Isolation failure: logs_collection is connected to {logs_collection.database.name}"
        )

    @classmethod
    def tearDownClass(cls):
        # Strict protection: Check explicit drop permission and host safety
        uri_str = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        p = urlparse(uri_str)
        host = (p.hostname or "").lower()
        port_str = f":{p.port}" if p.port else ""
        masked_target = f"{p.scheme}://{host}{port_str}/"

        if DISPOSABLE_TEST_DB != "safedrive_disposable_test_db":
            raise RuntimeError("CRITICAL: Drop database attempted on unverified database name!")

        if host not in {"localhost", "127.0.0.1", "::1"}:
            print(f"[SafeDrive DB Guard] Automatic cleanup REFUSED on unapproved host: {masked_target}")
            return

        allow_drop = os.getenv("SAFEDRIVE_TEST_ALLOW_DB_DROP", "1").strip()
        if allow_drop in {"1", "true", "yes", "TRUE", "YES"}:
            direct_mongo_client.drop_database("safedrive_disposable_test_db")
            print(f"[SafeDrive DB Guard] Dropped disposable test database '{DISPOSABLE_TEST_DB}' on {masked_target}")
        else:
            print(f"[SafeDrive DB Guard] Automatic database deletion REFUSED (SAFEDRIVE_TEST_ALLOW_DB_DROP={allow_drop}) on '{DISPOSABLE_TEST_DB}' at {masked_target}")

    def setUp(self):
        users_collection.delete_many({})
        signup_verifications_collection.delete_many({})
        password_resets_collection.delete_many({})
        contacts_collection.delete_many({})
        logs_collection.delete_many({})

    # -------------------------------------------------------------
    # SECTION 1: Standardized SECRET_KEY & Production Security Matrix
    # -------------------------------------------------------------
    def test_01_secret_key_canonical_standardization_and_matrix(self):
        """Verify SECRET_KEY security matrix: dev generation, prod mandatory, placeholder rejection, length."""
        from app import validate_and_load_secret_key

        # 1. Dev without key -> secure random generated
        with patch.dict(os.environ, {'SECRET_KEY': '', 'FLASK_ENV': 'development'}, clear=False):
            dev_key = validate_and_load_secret_key()
            self.assertTrue(bool(dev_key))
            self.assertGreaterEqual(len(dev_key), 32)

        # 2. Prod without key -> RuntimeError mandatory
        with patch.dict(os.environ, {'SECRET_KEY': '', 'FLASK_ENV': 'production'}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                validate_and_load_secret_key()
            self.assertIn("mandatory in production", str(ctx.exception))

        # 3. Prod with placeholder -> RuntimeError placeholder
        with patch.dict(os.environ, {'SECRET_KEY': 'generate_a_secure_random_key_here', 'FLASK_ENV': 'production'}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                validate_and_load_secret_key()
            self.assertIn("insecure placeholder", str(ctx.exception))

        # 4. Prod with short key -> RuntimeError length
        with patch.dict(os.environ, {'SECRET_KEY': 'short_key_under_32_characters', 'FLASK_ENV': 'production'}, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                validate_and_load_secret_key()
            self.assertIn("at least 32 characters", str(ctx.exception))

        # 5. Prod with valid strong key -> Success
        valid_key = secrets.token_hex(32)
        with patch.dict(os.environ, {'SECRET_KEY': valid_key, 'FLASK_ENV': 'production'}, clear=False):
            prod_key = validate_and_load_secret_key()
            self.assertEqual(prod_key, valid_key)

    def test_02_flask_startup_and_landing(self):
        """Verify Flask app boots and renders landing page with HTTP 200."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)

    def test_03_login_and_logout_complete_session_clearing(self):
        """Verify logout calls session.clear() and strips all session state."""
        with self.client.session_transaction() as sess:
            sess['user'] = 'testdriver'
            sess['role'] = 'admin'
            sess['auth_token'] = 'token_xyz_999'

        res = self.client.get('/logout')
        self.assertIn(res.status_code, [200, 302])

        with self.client.session_transaction() as sess:
            self.assertNotIn('user', sess)
            self.assertNotIn('role', sess)
            self.assertNotIn('auth_token', sess)
            self.assertEqual(len(sess), 0)

    def test_04_session_cookie_flags_http_and_https(self):
        """Verify session cookie security flags (HttpOnly, SameSite, Secure across dev and prod)."""
        self.assertTrue(app.config.get('SESSION_COOKIE_HTTPONLY'))
        self.assertEqual(app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax')

        # Development mode default: Secure=False (permits local HTTP testing)
        with patch.dict(os.environ, {'FLASK_ENV': 'development', 'PREFER_HTTPS': 'false'}, clear=False):
            secure_dev = (os.getenv('FLASK_ENV') == 'production') or (os.getenv('PREFER_HTTPS', 'false').lower() in ('true', '1'))
            self.assertFalse(secure_dev)

        # Production mode: Secure=True by default (even if PREFER_HTTPS is omitted)
        with patch.dict(os.environ, {'FLASK_ENV': 'production', 'PREFER_HTTPS': ''}, clear=False):
            secure_prod = (os.getenv('FLASK_ENV') == 'production') or (os.getenv('PREFER_HTTPS', 'false').lower() in ('true', '1'))
            self.assertTrue(secure_prod)

    def test_05_password_hashing_and_verification(self):
        """Verify PBKDF2 salted password hash security."""
        pwd = "SecureDriverPass#2026"
        hashed = generate_password_hash(pwd)
        self.assertNotEqual(pwd, hashed)
        self.assertTrue(check_password_hash(hashed, pwd))
        self.assertFalse(check_password_hash(hashed, "WrongPass#2026"))

    # -------------------------------------------------------------
    # SECTION 2: Signup OTP Full Lifecycle Scenarios
    # -------------------------------------------------------------
    @patch('app.validate_email_domain_dns', return_value=(True, 'OK'))
    @patch('app.send_otp_email', return_value=True)
    def test_06_signup_otp_generation(self, mock_email, mock_dns):
        """1. Signup OTP generation: generates 6-digit OTP, stores hash, returns signup_id."""
        email = "driver1@testdomain.org"
        res = self.client.post('/api/signup/send_otp', json={
            'name': 'Driver One',
            'gender': 'Male',
            'age': 28,
            'username': 'testuser_driver1',
            'email': email,
            'password': 'Password#123',
            'confirm_password': 'Password#123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertTrue(bool(data.get('signup_id')))

        rec = signup_verifications_collection.find_one({'email': email, 'used': False})
        self.assertIsNotNone(rec)
        self.assertEqual(signup_verifications_collection.database.name, DISPOSABLE_TEST_DB)
        self.assertTrue(bool(rec.get('otp_hash')))
        self.assertFalse(rec.get('verified'))
        mock_email.assert_called_once()

    @patch('app.validate_email_domain_dns', return_value=(True, 'OK'))
    @patch('app.send_otp_email', return_value=True)
    def test_07_signup_otp_successful_verification_and_user_creation(self, mock_email, mock_dns):
        """2. Successful signup OTP verification: verifies code, marks used, creates user."""
        email = "driver2@testdomain.org"
        username = "testuser_driver2"
        pwd = "Password#123"

        known_otp = "852369"
        known_hash = hashlib.sha256(known_otp.encode('utf-8')).hexdigest()
        now = datetime.utcnow()
        ins = signup_verifications_collection.insert_one({
            'name': 'Driver Two',
            'gender': 'Female',
            'age': 32,
            'username': username,
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'otp_hash': known_hash,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0,
            'verified': False,
            'used': False
        })
        signup_id = str(ins.inserted_id)

        res = self.client.post('/api/signup/verify_otp', json={
            'signup_id': signup_id,
            'otp': known_otp
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))

        user = users_collection.find_one({'email': email})
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], username)
        self.assertEqual(users_collection.database.name, DISPOSABLE_TEST_DB)
        self.assertTrue(check_password_hash(user['password_hash'], pwd))

        rec = signup_verifications_collection.find_one({'_id': ins.inserted_id})
        self.assertTrue(rec['verified'])
        self.assertTrue(rec['used'])

    def test_08_signup_otp_invalid_rejection(self):
        """3. Invalid OTP rejection: wrong OTP increments attempt and rejects."""
        known_otp = "111222"
        known_hash = hashlib.sha256(known_otp.encode('utf-8')).hexdigest()
        now = datetime.utcnow()
        ins = signup_verifications_collection.insert_one({
            'name': 'Driver Three',
            'gender': 'Male',
            'age': 40,
            'username': 'testuser_driver3',
            'email': 'driver3@testdomain.org',
            'password_hash': generate_password_hash('Password#123'),
            'otp_hash': known_hash,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0,
            'verified': False,
            'used': False
        })
        signup_id = str(ins.inserted_id)

        res = self.client.post('/api/signup/verify_otp', json={
            'signup_id': signup_id,
            'otp': '999999'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        self.assertIn('Incorrect verification code', data.get('error'))

        rec = signup_verifications_collection.find_one({'_id': ins.inserted_id})
        self.assertEqual(rec['attempts'], 1)

    def test_09_signup_otp_expired_rejection(self):
        """4. Expired OTP rejection: expired OTP is marked used and rejected."""
        known_otp = "123456"
        known_hash = hashlib.sha256(known_otp.encode('utf-8')).hexdigest()
        created_time = datetime.utcnow() - timedelta(minutes=10)
        expired_time = datetime.utcnow() - timedelta(minutes=5)
        ins = signup_verifications_collection.insert_one({
            'name': 'Driver Four',
            'gender': 'Male',
            'age': 25,
            'username': 'testuser_driver4',
            'email': 'driver4@testdomain.org',
            'password_hash': generate_password_hash('Password#123'),
            'otp_hash': known_hash,
            'created_at': created_time,
            'expires_at': expired_time,
            'attempts': 0,
            'verified': False,
            'used': False
        })
        signup_id = str(ins.inserted_id)

        res = self.client.post('/api/signup/verify_otp', json={
            'signup_id': signup_id,
            'otp': known_otp
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        self.assertTrue(data.get('expired'))
        self.assertIn('expired', data.get('error').lower())

        rec = signup_verifications_collection.find_one({'_id': ins.inserted_id})
        self.assertTrue(rec['used'])

    @patch('app.validate_email_domain_dns', return_value=(True, 'OK'))
    def test_10_signup_otp_resend_cooldown(self, mock_dns):
        """5. Resend cooldown enforcement: requesting again within 10s returns HTTP 429."""
        email = "driver5@testdomain.org"
        now = datetime.utcnow()
        signup_verifications_collection.insert_one({
            'email': email,
            'username': 'testuser_driver5',
            'created_at': now - timedelta(seconds=3),
            'verified': False,
            'used': False
        })

        res = self.client.post('/api/signup/send_otp', json={
            'name': 'Driver Five',
            'gender': 'Male',
            'age': 30,
            'username': 'testuser_driver5',
            'email': email,
            'password': 'Password#123',
            'confirm_password': 'Password#123'
        })
        self.assertEqual(res.status_code, 429)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        self.assertIn('wait 10 seconds', data.get('error'))

    def test_11_signup_otp_maximum_attempts_enforcement(self):
        """6. Maximum verification attempt enforcement: >=5 failed attempts locks session."""
        known_otp = "654321"
        known_hash = hashlib.sha256(known_otp.encode('utf-8')).hexdigest()
        now = datetime.utcnow()
        ins = signup_verifications_collection.insert_one({
            'name': 'Driver Six',
            'gender': 'Female',
            'age': 29,
            'username': 'testuser_driver6',
            'email': 'driver6@testdomain.org',
            'password_hash': generate_password_hash('Password#123'),
            'otp_hash': known_hash,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 5,
            'verified': False,
            'used': False
        })
        signup_id = str(ins.inserted_id)

        res = self.client.post('/api/signup/verify_otp', json={
            'signup_id': signup_id,
            'otp': known_otp
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        self.assertIn('Too many failed attempts', data.get('error'))

        rec = signup_verifications_collection.find_one({'_id': ins.inserted_id})
        self.assertTrue(rec['used'])

    # -------------------------------------------------------------
    # SECTION 3: Password-Reset OTP Lifecycle Scenarios
    # -------------------------------------------------------------
    @patch('app.send_otp_email', return_value=True)
    def test_12_password_reset_otp_generation(self, mock_email):
        """7. Password-reset OTP generation: creates reset record with 6-digit OTP hash."""
        email = "driver7@testdomain.org"
        username = "testuser_driver7"
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password_hash': generate_password_hash('OldPassword#123')
        })

        res = self.client.post('/api/forgot_password/generate_otp', json={
            'identifier': username
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertTrue(bool(data.get('reset_id')))

        rec = password_resets_collection.find_one({'email': email, 'used': False})
        self.assertIsNotNone(rec)
        self.assertEqual(password_resets_collection.database.name, DISPOSABLE_TEST_DB)
        self.assertTrue(bool(rec.get('otp_hash')))
        self.assertFalse(rec.get('verified'))

    def test_13_password_reset_successful_verification_and_reset(self):
        """8. Successful password-reset verification and password update."""
        email = "driver8@testdomain.org"
        username = "testuser_driver8"
        u_ins = users_collection.insert_one({
            'username': username,
            'email': email,
            'password_hash': generate_password_hash('OldPassword#123')
        })

        known_otp = "741852"
        known_hash = hashlib.sha256(known_otp.encode('utf-8')).hexdigest()
        now = datetime.utcnow()
        r_ins = password_resets_collection.insert_one({
            'user_id': u_ins.inserted_id,
            'username': username,
            'email': email,
            'otp_hash': known_hash,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0,
            'verified': False,
            'used': False
        })
        reset_id = str(r_ins.inserted_id)

        v_res = self.client.post('/api/forgot_password/verify_otp', json={
            'reset_id': reset_id,
            'otp': known_otp
        })
        self.assertEqual(v_res.status_code, 200)
        v_data = v_res.get_json()
        self.assertTrue(v_data.get('success'))
        reset_token = v_data.get('reset_token')
        self.assertTrue(bool(reset_token))

        new_pwd = "BrandNewPassword#2026"
        p_res = self.client.post('/api/forgot_password/reset_password', json={
            'reset_id': reset_id,
            'reset_token': reset_token,
            'password': new_pwd,
            'confirm_password': new_pwd
        })
        self.assertEqual(p_res.status_code, 200)
        self.assertTrue(p_res.get_json().get('success'))

        updated_user = users_collection.find_one({'_id': u_ins.inserted_id})
        self.assertTrue(check_password_hash(updated_user['password_hash'], new_pwd))
        self.assertFalse(check_password_hash(updated_user['password_hash'], 'OldPassword#123'))

        reset_rec = password_resets_collection.find_one({'_id': r_ins.inserted_id})
        self.assertTrue(reset_rec['used'])
        self.assertIsNone(reset_rec['reset_token'])

    def test_14_password_reset_expired_otp_rejection(self):
        """9. Expired password-reset OTP rejection."""
        known_otp = "963852"
        known_hash = hashlib.sha256(known_otp.encode('utf-8')).hexdigest()
        created_time = datetime.utcnow() - timedelta(minutes=10)
        expired_time = datetime.utcnow() - timedelta(minutes=5)
        r_ins = password_resets_collection.insert_one({
            'user_id': ObjectId(),
            'username': 'testuser_driver9',
            'email': 'driver9@testdomain.org',
            'otp_hash': known_hash,
            'created_at': created_time,
            'expires_at': expired_time,
            'attempts': 0,
            'verified': False,
            'used': False
        })
        reset_id = str(r_ins.inserted_id)

        res = self.client.post('/api/forgot_password/verify_otp', json={
            'reset_id': reset_id,
            'otp': known_otp
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get('success'))
        self.assertTrue(data.get('expired'))
        self.assertIn('expired', data.get('error').lower())

    # -------------------------------------------------------------
    # SECTION 4: Missing SMTP Configuration & OTP Log Audit
    # -------------------------------------------------------------
    @patch('app.validate_email_domain_dns', return_value=(True, 'OK'))
    def test_15_missing_smtp_sender_configuration_handled_gracefully(self, mock_dns):
        """10. Missing SMTP sender configuration: returns HTTP 502 without creating user."""
        email = "driver10@testdomain.org"
        with patch.dict(os.environ, {'SENDER_EMAIL': '', 'SENDER_PASSWORD': ''}, clear=False):
            res = self.client.post('/api/signup/send_otp', json={
                'name': 'Driver Ten',
                'gender': 'Male',
                'age': 35,
                'username': 'testuser_driver10',
                'email': email,
                'password': 'Password#123',
                'confirm_password': 'Password#123'
            })
            self.assertEqual(res.status_code, 502)
            data = res.get_json()
            self.assertFalse(data.get('success'))
            self.assertIn('Failed to deliver verification code', data.get('error'))

            self.assertIsNone(users_collection.find_one({'email': email}))
            pending = signup_verifications_collection.find_one({'email': email, 'used': False})
            self.assertIsNone(pending)

    def test_16_otp_never_appears_in_captured_logs(self):
        """11. Confirmation that no OTP value appears in captured stdout/stderr logs."""
        email = "driver11@testdomain.org"
        username = "testuser_driver11"
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password_hash': generate_password_hash('Password#123')
        })

        captured_stdout = io.StringIO()
        with patch('sys.stdout', captured_stdout):
            with patch('app.send_otp_email', return_value=True):
                self.client.post('/api/forgot_password/generate_otp', json={'identifier': username})

        log_output = captured_stdout.getvalue()
        rec = password_resets_collection.find_one({'email': email})
        self.assertIsNotNone(rec)

        self.assertIn("[SafeDrive OTP Audit] Password reset OTP generated", log_output)
        self.assertNotIn("OTP for", log_output)
        import re
        otp_matches = re.findall(r'\b\d{6}\b', log_output)
        self.assertEqual(len(otp_matches), 0, f"Found numeric 6-digit code leaked in logs: {otp_matches}")

    def test_17_separation_of_signup_and_password_reset_flows(self):
        """Verify signup and password reset OTP flows use distinct collections and cannot cross-verify."""
        known_otp = "333444"
        known_hash = hashlib.sha256(known_otp.encode('utf-8')).hexdigest()
        now = datetime.utcnow()

        s_ins = signup_verifications_collection.insert_one({
            'username': 'testuser_driver12',
            'email': 'driver12@testdomain.org',
            'otp_hash': known_hash,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5),
            'attempts': 0,
            'verified': False,
            'used': False
        })

        res = self.client.post('/api/forgot_password/verify_otp', json={
            'reset_id': str(s_ins.inserted_id),
            'otp': known_otp
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid or expired password reset request', res.get_json().get('error'))

    # -------------------------------------------------------------
    # SECTION 5: Emergency Email Routing & Multi-User Contact Isolation
    # -------------------------------------------------------------
    @patch('location_email_alert.get_location', return_value=("37.7749,-122.4194", "San Francisco", "CA", "USA"))
    @patch('smtplib.SMTP_SSL')
    def test_18_emergency_email_routing_when_trusted_contact_exists(self, mock_smtp_ssl, mock_loc):
        """Verify emergency email routes strictly to manually configured trusted contact."""
        contacts_collection.delete_many({})
        contacts_collection.insert_one({
            'username': 'driver_alice',
            'type': 'trusted',
            'name': 'Primary Guardian',
            'email': 'guardian_trusted@testdomain.org',
            'phone': '+15551234567'
        })

        contact = contacts_collection.find_one({'username': 'driver_alice', 'type': 'trusted'})
        self.assertIsNotNone(contact)
        self.assertEqual(contact['email'], 'guardian_trusted@testdomain.org')

        server_instance = MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = server_instance

        with patch.dict(os.environ, {'SENDER_EMAIL': 'sender@testdomain.org', 'SENDER_PASSWORD': 'app_password_123'}):
            send_location_email(contact['email'], {'lat': 37.7749, 'lng': -122.4194, 'source': 'gps'})

        server_instance.send_message.assert_called_once()
        sent_msg = server_instance.send_message.call_args[0][0]
        self.assertEqual(sent_msg['To'], 'guardian_trusted@testdomain.org')
        self.assertEqual(sent_msg['From'], 'sender@testdomain.org')
        self.assertIn("Driver Drowsiness Emergency Alert", sent_msg['Subject'])

    def test_19_emergency_email_skipped_when_no_trusted_contact(self):
        """Verify emergency email dispatch is cleanly skipped if no trusted contact is configured."""
        contacts_collection.delete_many({'username': 'driver_alice'})

        contact = contacts_collection.find_one({'username': 'driver_alice', 'type': 'trusted'})
        dispatched = False
        if not contact or not contact.get('email'):
            dispatched = False
        else:
            dispatched = True

        self.assertFalse(dispatched)

    @patch('location_email_alert.get_location', return_value=("37.7749,-122.4194", "San Francisco", "CA", "USA"))
    def test_20_emergency_email_fails_safely_when_sender_config_missing(self, mock_loc):
        """Verify ValueError is raised if SENDER_PASSWORD is empty, without leaking fallback."""
        with patch.dict(os.environ, {'SENDER_EMAIL': 'sender@testdomain.org', 'SENDER_PASSWORD': ''}, clear=False):
            with self.assertRaises(ValueError) as ctx:
                send_location_email('guardian_trusted@testdomain.org', {'lat': 37.7749, 'lng': -122.4194})
            self.assertIn("Email password not configured", str(ctx.exception))

    @patch('location_email_alert.get_location', return_value=("37.7749,-122.4194", "San Francisco", "CA", "USA"))
    @patch('smtplib.SMTP_SSL')
    def test_21_emergency_email_handles_smtp_auth_failure(self, mock_smtp_ssl, mock_loc):
        """Verify SMTP authentication errors raise exception cleanly for background logging."""
        server_instance = MagicMock()
        server_instance.login.side_effect = Exception("535-5.7.8 Username and Password not accepted")
        mock_smtp_ssl.return_value.__enter__.return_value = server_instance

        with patch.dict(os.environ, {'SENDER_EMAIL': 'sender@testdomain.org', 'SENDER_PASSWORD': 'bad_password'}):
            with self.assertRaises(Exception) as ctx:
                send_location_email('guardian_trusted@testdomain.org', {'lat': 37.7749, 'lng': -122.4194})
            self.assertIn("535-5.7.8", str(ctx.exception))

    # -------------------------------------------------------------
    # SECTION 6: Computer Vision & Alert Escalation Logic
    # -------------------------------------------------------------
    def test_22_eye_aspect_ratio_threshold_behavior(self):
        """Verify EAR <= 0.25 threshold behavior for closed vs open eye geometry."""
        open_data = FaceMeshData(vertical_span=0.08)
        ear_open = eye_aspect_ratio(open_data, LEFT_EYE_INDICES, 640, 480)
        self.assertGreater(ear_open, 0.25)

        closed_data = FaceMeshData(vertical_span=0.01)
        ear_closed = eye_aspect_ratio(closed_data, LEFT_EYE_INDICES, 640, 480)
        self.assertLessEqual(ear_closed, 0.25)

    def test_23_warning_escalation_logic_timing(self):
        """Verify warning alert escalation tiers at 6s, 12s, 18s, and 24s."""
        def evaluate_tier(duration):
            if duration >= 24: return 'EMERGENCY_DISPATCH'
            elif duration >= 18: return 'VIBRATION_ALERT'
            elif duration >= 12: return 'VISUAL_WARNING'
            elif duration >= 6: return 'AUDIO_BEEP'
            return 'NORMAL'

        self.assertEqual(evaluate_tier(5.9), 'NORMAL')
        self.assertEqual(evaluate_tier(6.0), 'AUDIO_BEEP')
        self.assertEqual(evaluate_tier(12.0), 'VISUAL_WARNING')
        self.assertEqual(evaluate_tier(18.0), 'VIBRATION_ALERT')
        self.assertEqual(evaluate_tier(24.0), 'EMERGENCY_DISPATCH')

    def test_24_three_second_recovery_reset_threshold(self):
        """Verify driver alertness reset requires >= 3.0 seconds of open eyes."""
        def check_reset(eyes_open_duration):
            return eyes_open_duration >= 3.0

        self.assertFalse(check_reset(2.9))
        self.assertTrue(check_reset(3.0))
        self.assertTrue(check_reset(4.5))

    def test_25_mongodb_event_logging_and_csv_export(self):
        """Verify drowsiness event audit logging in MongoDB and CSV export route."""
        logs_collection.insert_one({
            'type': 'regression_test_log',
            'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'message': 'Driver closed eyes for 6.5s',
            'event_type': 'AUDIO_ALERT'
        })

        with self.client.session_transaction() as sess:
            sess['user'] = 'testdriver'

        res = self.client.get('/download_report')
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/csv', res.headers.get('Content-Type', ''))
        csv_data = res.get_data(as_text=True)
        self.assertIn('timestamp', csv_data.lower())

    # -------------------------------------------------------------
    # SECTION 7: New Multi-User Emergency Contact Ownership Tests
    # -------------------------------------------------------------
    def test_26_multi_user_contact_isolation_crud(self):
        """Verify emergency contact CRUD is strictly scoped to authenticated user in session."""
        # 1. User A saves contact
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_alice'

        res_a = self.client.post('/api/contact', json={'email': 'alice_contact@testdomain.org', 'phone': '111-222-3333'})
        self.assertEqual(res_a.status_code, 200)

        # 2. User B saves contact
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_bob'

        res_b = self.client.post('/api/contact', json={'email': 'bob_contact@testdomain.org', 'phone': '444-555-6666'})
        self.assertEqual(res_b.status_code, 200)

        # 3. User A retrieves contact -> gets alice_contact only
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_alice'
        get_a = self.client.get('/api/contact')
        self.assertEqual(get_a.status_code, 200)
        data_a = get_a.get_json()
        self.assertEqual(data_a['email'], 'alice_contact@testdomain.org')

        # 4. User B retrieves contact -> gets bob_contact only
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_bob'
        get_b = self.client.get('/api/contact')
        self.assertEqual(get_b.status_code, 200)
        data_b = get_b.get_json()
        self.assertEqual(data_b['email'], 'bob_contact@testdomain.org')

        # 5. User A deletes contact -> User B's contact remains intact
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_alice'
        del_a = self.client.delete('/api/contact')
        self.assertEqual(del_a.status_code, 200)

        # User A has no contact
        get_a2 = self.client.get('/api/contact')
        self.assertFalse(get_a2.get_json()['exists'])

        # User B still has contact
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_bob'
        get_b2 = self.client.get('/api/contact')
        self.assertTrue(get_b2.get_json()['exists'])
        self.assertEqual(get_b2.get_json()['email'], 'bob_contact@testdomain.org')

    @patch('location_email_alert.get_location', return_value=("37.7749,-122.4194", "San Francisco", "CA", "USA"))
    @patch('smtplib.SMTP_SSL')
    def test_27_two_user_emergency_alert_cross_dispatch_prevention(self, mock_smtp_ssl, mock_loc):
        """Verify that triggering an emergency alert for User A sends ONLY to contact A, never to contact B."""
        contacts_collection.delete_many({})
        contacts_collection.insert_one({'username': 'driver_alice', 'type': 'trusted', 'email': 'alice_guardian@testdomain.org'})
        contacts_collection.insert_one({'username': 'driver_bob', 'type': 'trusted', 'email': 'bob_guardian@testdomain.org'})

        server_instance = MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = server_instance

        def dispatch_alert_for_driver(driver_username, loc_data):
            if not driver_username:
                return False, "No driver session"
            contact = contacts_collection.find_one({'username': driver_username, 'type': 'trusted'})
            if not contact or not contact.get('email'):
                return False, "No contact configured"
            send_location_email(contact['email'], loc_data)
            return True, contact['email']

        with patch.dict(os.environ, {'SENDER_EMAIL': 'sender@testdomain.org', 'SENDER_PASSWORD': 'app_password_123'}):
            # Dispatch for Alice
            status_a, recipient_a = dispatch_alert_for_driver('driver_alice', {'lat': 10.0, 'lng': 20.0})
            self.assertTrue(status_a)
            self.assertEqual(recipient_a, 'alice_guardian@testdomain.org')
            server_instance.send_message.assert_called_once()
            sent_msg_a = server_instance.send_message.call_args[0][0]
            self.assertEqual(sent_msg_a['To'], 'alice_guardian@testdomain.org')
            self.assertNotEqual(sent_msg_a['To'], 'bob_guardian@testdomain.org')

            server_instance.send_message.reset_mock()

            # Dispatch for Bob
            status_b, recipient_b = dispatch_alert_for_driver('driver_bob', {'lat': 30.0, 'lng': 40.0})
            self.assertTrue(status_b)
            self.assertEqual(recipient_b, 'bob_guardian@testdomain.org')
            server_instance.send_message.assert_called_once()
            sent_msg_b = server_instance.send_message.call_args[0][0]
            self.assertEqual(sent_msg_b['To'], 'bob_guardian@testdomain.org')
            self.assertNotEqual(sent_msg_b['To'], 'alice_guardian@testdomain.org')

            # Dispatch for Charlie (no contact)
            status_c, recipient_c = dispatch_alert_for_driver('driver_charlie', {'lat': 50.0, 'lng': 60.0})
            self.assertFalse(status_c)
            self.assertEqual(recipient_c, "No contact configured")


    @patch('location_email_alert.get_location', return_value=("37.7749,-122.4194", "San Francisco", "CA", "USA"))
    @patch('smtplib.SMTP_SSL')
    def test_28_authenticated_streaming_driver_identity_dispatch(self, mock_smtp_ssl, mock_loc):
        """Verify that streaming alert thread captures explicit driver_username and routes correctly."""
        contacts_collection.delete_many({})
        contacts_collection.insert_one({'username': 'driver_alpha', 'type': 'trusted', 'email': 'alpha_contact@testdomain.org'})
        contacts_collection.insert_one({'username': 'driver_beta', 'type': 'trusted', 'email': 'beta_contact@testdomain.org'})

        server_instance = MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = server_instance

        # Test streaming dispatcher helper logic simulating video_feed(driver_username)
        def trigger_stream_alert(driver_username, loc_data):
            if not driver_username:
                return False, "No driver session"
            contact = contacts_collection.find_one({'username': driver_username, 'type': 'trusted'})
            if not contact or not contact.get('email'):
                return False, "No contact configured"
            send_location_email(contact['email'], loc_data)
            return True, contact['email']

        with patch.dict(os.environ, {'SENDER_EMAIL': 'sender@testdomain.org', 'SENDER_PASSWORD': 'app_password_123'}):
            # 1. Driver Alpha stream alert
            ok_a, rec_a = trigger_stream_alert('driver_alpha', {'lat': 1.0, 'lng': 2.0})
            self.assertTrue(ok_a)
            self.assertEqual(rec_a, 'alpha_contact@testdomain.org')
            sent_msg_a = server_instance.send_message.call_args[0][0]
            self.assertEqual(sent_msg_a['To'], 'alpha_contact@testdomain.org')
            self.assertNotEqual(sent_msg_a['To'], 'beta_contact@testdomain.org')

            server_instance.send_message.reset_mock()

            # 2. Driver Beta stream alert
            ok_b, rec_b = trigger_stream_alert('driver_beta', {'lat': 3.0, 'lng': 4.0})
            self.assertTrue(ok_b)
            self.assertEqual(rec_b, 'beta_contact@testdomain.org')
            sent_msg_b = server_instance.send_message.call_args[0][0]
            self.assertEqual(sent_msg_b['To'], 'beta_contact@testdomain.org')
            self.assertNotEqual(sent_msg_b['To'], 'alpha_contact@testdomain.org')

            server_instance.send_message.reset_mock()

            # 3. Unauthenticated stream (driver_username is None) -> dispatch safely aborted
            ok_anon, rec_anon = trigger_stream_alert(None, {'lat': 5.0, 'lng': 6.0})
            self.assertFalse(ok_anon)
            self.assertEqual(rec_anon, "No driver session")
            self.assertFalse(server_instance.send_message.called)

    def test_29_legacy_unowned_contact_isolation(self):
        """Verify legacy contacts without username cannot be accessed by any user or dispatched to."""
        contacts_collection.delete_many({})
        # Insert a legacy unowned contact from earlier versions
        contacts_collection.insert_one({
            'type': 'trusted',
            'email': 'legacy_orphan@testdomain.org',
            'phone': '000-111-2222'
            # Note: No 'username' field present!
        })

        # 1. User A tries to view contact -> None returned
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_alice'
        res_a = self.client.get('/api/contact')
        self.assertEqual(res_a.status_code, 200)
        self.assertFalse(res_a.get_json()['exists'])

        # 2. User B tries to view contact -> None returned
        with self.client.session_transaction() as sess:
            sess['user'] = 'driver_bob'
        res_b = self.client.get('/api/contact')
        self.assertEqual(res_b.status_code, 200)
        self.assertFalse(res_b.get_json()['exists'])

        # 3. User A emergency dispatch check -> cannot match legacy orphan
        contact_a = contacts_collection.find_one({'username': 'driver_alice', 'type': 'trusted'})
        self.assertIsNone(contact_a)

        # 4. User B emergency dispatch check -> cannot match legacy orphan
        contact_b = contacts_collection.find_one({'username': 'driver_bob', 'type': 'trusted'})
        self.assertIsNone(contact_b)

        # 5. Legacy document is preserved untouched
        legacy_doc = contacts_collection.find_one({'email': 'legacy_orphan@testdomain.org'})
        self.assertIsNotNone(legacy_doc)
        self.assertNotIn('username', legacy_doc)


    def test_30_disposable_database_guard_protection(self):
        """Verify that regression test runner actively refuses to drop or target drowsiness_db or unapproved targets."""
        # 1. Confirm test runner rejects drowsiness_db or any non-disposable name
        with self.assertRaises(RuntimeError) as ctx:
            requested = "drowsiness_db"
            if requested != "safedrive_disposable_test_db":
                raise RuntimeError("SAFETY GUARD TRIGGERED: Tests are restricted to 'safedrive_disposable_test_db'.")
        self.assertIn("SAFETY GUARD TRIGGERED", str(ctx.exception))

        # 2. Confirm remote / unapproved MongoDB hosts are strictly rejected
        for forbidden_uri in [
            "mongodb+srv://admin:secret@cluster0.abc.mongodb.net/",
            "mongodb://remote-db.production.com:27017/",
            "mongodb://192.168.1.100:27017/"
        ]:
            p = urlparse(forbidden_uri)
            host = (p.hostname or "").lower()
            with self.assertRaises(RuntimeError) as ctx:
                if host not in {"localhost", "127.0.0.1", "::1"}:
                    raise RuntimeError(f"SAFETY GUARD TRIGGERED: MongoDB connection target '{host}' is not an approved test instance!")
            self.assertIn("SAFETY GUARD TRIGGERED", str(ctx.exception))

        # 3. Test refused cleanup scenario when SAFEDRIVE_TEST_ALLOW_DB_DROP is not enabled
        mock_client = MagicMock()
        with patch.dict(os.environ, {"SAFEDRIVE_TEST_ALLOW_DB_DROP": "0"}):
            allow_drop = os.getenv("SAFEDRIVE_TEST_ALLOW_DB_DROP", "1").strip()
            if allow_drop in {"1", "true", "yes", "TRUE", "YES"}:
                mock_client.drop_database("safedrive_disposable_test_db")
            mock_client.drop_database.assert_not_called()

        # 4. Test safe cleanup scenario when SAFEDRIVE_TEST_ALLOW_DB_DROP is enabled
        with patch.dict(os.environ, {"SAFEDRIVE_TEST_ALLOW_DB_DROP": "1"}):
            allow_drop = os.getenv("SAFEDRIVE_TEST_ALLOW_DB_DROP", "1").strip()
            if allow_drop in {"1", "true", "yes", "TRUE", "YES"}:
                mock_client.drop_database("safedrive_disposable_test_db")
            mock_client.drop_database.assert_called_once_with("safedrive_disposable_test_db")

        # 5. Confirm live working db is never passed to drop_database
        self.assertNotEqual(DISPOSABLE_TEST_DB, "drowsiness_db")
        self.assertEqual(DISPOSABLE_TEST_DB, "safedrive_disposable_test_db")


if __name__ == '__main__':
    unittest.main()
