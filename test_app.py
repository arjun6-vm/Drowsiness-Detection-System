import pytest
from app import app, users

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_signup_login_logout(client):
    # Test signup
    response = client.post('/signup', data={
        'username': 'testuser',
        'password': 'testpass',
        'confirm_password': 'testpass',
        'favorite_car': 'Tesla',
        'favorite_person': 'Alice'
    }, follow_redirects=True)
    assert b'Login' in response.data

    # Test login with correct credentials
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass'
    }, follow_redirects=True)
    assert b'Driver Safety System' in response.data or b'Live Video Feed' in response.data

    # Test login with incorrect credentials
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'wrongpass'
    })
    assert b'Invalid credentials' in response.data

    # Test logout
    response = client.get('/logout', follow_redirects=True)
    assert b'Login' in response.data

def test_forgot_password(client):
    # Add user to in-memory users dict
    users['forgotuser'] = {
        'password': 'forgotpass',
        'favorite_car': 'BMW',
        'favorite_person': 'Bob'
    }

    # Correct answers
    response = client.post('/forgot_password', data={
        'username': 'forgotuser',
        'favorite_car': 'BMW',
        'favorite_person': 'Bob'
    })
    assert b'Your password is' in response.data

    # Incorrect answers
    response = client.post('/forgot_password', data={
        'username': 'forgotuser',
        'favorite_car': 'Audi',
        'favorite_person': 'Bob'
    })
    assert b'Incorrect answers' in response.data

    # Unknown username
    response = client.post('/forgot_password', data={
        'username': 'unknownuser',
        'favorite_car': 'Audi',
        'favorite_person': 'Bob'
    })
    assert b'Username not found' in response.data

def test_protected_routes(client):
    # Access index without login should redirect to login
    response = client.get('/', follow_redirects=True)
    assert b'Login' in response.data

    # Access video_feed without login should redirect to login
    response = client.get('/video_feed', follow_redirects=True)
    assert b'Login' in response.data

def test_report_download(client):
    # Login first
    users['reportuser'] = {
        'password': 'reportpass',
        'favorite_car': 'Audi',
        'favorite_person': 'Eve'
    }
    client.post('/login', data={
        'username': 'reportuser',
        'password': 'reportpass'
    })

    # Download report
    response = client.get('/download_report')
    assert response.status_code == 200
    assert response.mimetype == 'text/csv'
