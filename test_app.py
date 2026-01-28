import unittest

from app import app, db, Order, LineItem, User
from flask import url_for
from datetime import datetime

class OrderTrackerTestCase(unittest.TestCase):
    def setUp(self):
        # Set up test client and in-memory test DB
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['LOGIN_DISABLED'] = True  # Disable login for testing
        self.client = app.test_client()
        
        with app.app_context():
            db.create_all()
            # Create a test user
            user = User(username='testuser')
            user.set_password('testpass123')
            db.session.add(user)
            db.session.commit()
            
    def tearDown(self):
        # Get rid of all the tables after the test
        with app.app_context():
            db.drop_all()

    def login(self):
        """Helper to log in the test user."""
        return self.client.post('/login', data={
            'username': 'testuser',
            'password': 'testpass123'
        }, follow_redirects=True)
            
    def test_home_page_redirects_when_not_logged_in(self):
        # Disable LOGIN_DISABLED temporarily
        app.config['LOGIN_DISABLED'] = False
        res = self.client.get('/')
        self.assertEqual(res.status_code, 302)  # Redirect to login
        app.config['LOGIN_DISABLED'] = True
        
    def test_home_page_loads_when_logged_in(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Order Tracker', res.data)
        
    def test_add_order(self):
        # Simulate adding a new order
        res = self.client.post('/add', data={
            'vendor': "Test Vendor",
            'status': 'Pending',
            'tracking_number': '12345',
            'product[]': ['Widget A'],
            'quantity[]': ['3']
        }, follow_redirects=True)
        
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Test Vendor', res.data)
        
        # Confirm order is in the DB
        with app.app_context():
            order = Order.query.first()
            self.assertIsNotNone(order)
            self.assertEqual(order.vendor, 'Test Vendor')
            self.assertEqual(order.items[0].product, 'Widget A')
            
    def test_view_orders(self):
        # Add directly to the db
        with app.app_context():
            order = Order(vendor='Vendor X', status='Pending', tracking_number='abc')
            db.session.add(order)
            db.session.commit()
            
        res = self.client.get('/orders')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Vendor X', res.data)

    def test_status_validation(self):
        # Test that invalid status defaults to Pending
        res = self.client.post('/add', data={
            'vendor': "Test Vendor",
            'status': 'InvalidStatus',
            'tracking_number': '',
            'product[]': [],
            'quantity[]': []
        }, follow_redirects=True)
        
        with app.app_context():
            order = Order.query.first()
            self.assertEqual(order.status, 'Pending')

    def test_setup_creates_user(self):
        with app.app_context():
            # Delete existing user for this test
            User.query.delete()
            db.session.commit()
            
        res = self.client.post('/setup', data={
            'username': 'newadmin',
            'password': 'securepass123',
            'confirm_password': 'securepass123'
        }, follow_redirects=True)
        
        self.assertEqual(res.status_code, 200)
        
        with app.app_context():
            user = User.query.filter_by(username='newadmin').first()
            self.assertIsNotNone(user)
            self.assertTrue(user.check_password('securepass123'))

    def test_setup_blocked_when_user_exists(self):
        # User already exists from setUp
        res = self.client.get('/setup', follow_redirects=True)
        self.assertIn(b'Setup already completed', res.data)
        
if __name__ == '__main__':
    unittest.main()
