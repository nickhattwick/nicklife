import boto3
import requests

ssm = boto3.client('ssm')

def get_parameter(name):
    #Retrieve parameter from SSM Parameter Store
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response['Parameter']['Value']

def update_parameter(name, value):
    """Update parameter in SSM Parameter Store"""
    ssm.put_parameter(Name=name, Value=value, Type='String', Overwrite=True)

def refresh_credentials(client_id, client_secret, refresh_token):
    """Refresh Fitbit token using refresh_token"""
    encoded_credentials = base64.b64encode(f"{client_id}:{client_secret}".encode('utf-8')).decode('utf-8')
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    response = requests.post('https://api.fitbit.com/oauth2/token', headers=headers, data=data)
    return response.json()

def handle_tokens():
    access_token = get_parameter('FITBIT_ACCESS_TOKEN')
    refresh_token = get_parameter('FITBIT_REFRESH_TOKEN')
    client_id = get_parameter('FITBIT_CLIENT_ID')
    client_secret = get_parameter('FITBIT_CLIENT_SECRET')
    
    # Use access token to make Fitbit API request
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get('https://api.fitbit.com/1/user/-/profile.json', headers=headers)

    if response.status_code == 401:
        refresh_tokens(client_id, client_secret, refresh_token)

    return get_parameter('FITBIT_ACCESS_TOKEN')


def refresh_tokens(client_id, client_secret, refresh_token):
    refreshed_tokens = refresh_credentials(client_id, client_secret, refresh_token)
    update_parameter('FITBIT_ACCESS_TOKEN', refreshed_tokens.get('access_token'))
    update_parameter('FITBIT_REFRESH_TOKEN', refreshed_tokens.get('refresh_token'))