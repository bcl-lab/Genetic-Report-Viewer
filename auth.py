from flask import redirect, request
from urllib import urlencode
from functools import wraps
import requests
from config import AUTH_BASE,CLIENT_ID, REDIRECT_URI, API_BASE, SCOPES


class OAuthError(Exception):
    pass


def api_call_for_test(api_endpoint):
    '''
    helper function that makes API call
    '''
    access_token = request.cookies['access_token']
    auth_header = {'Authorization': 'Bearer %s'% access_token}
    return requests.get('%s%s'% (API_BASE, api_endpoint), headers=auth_header)


def get_access_token(auth_code):
    '''
    exchange `code` with `access token`
    '''
    exchange_data = {
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'grant_type': 'authorization_code'
    }
    resp = requests.post(AUTH_BASE+'/token', data=exchange_data)
    if resp.status_code != 200:
        raise OAuthError
    else:
        return resp.json()['access_token']


def has_access():
    '''
    check if application has access to API
    '''
    if 'access_token' not in request.cookies:
        return False
    # we are being lazy here and don't keep a status of our access token,
    # so we just make a simple API call to see if it expires yet
    access_resource = SCOPES[0].split('/')[-1].split('.')[0]
    test_call = api_call_for_test('/%s?_count=1' % access_resource)
    return test_call.status_code != 403


def require_oauth(view):
    @wraps(view)
    def authorized_view(*args, **kwargs):
        # check is we have access to the api, if not, we redirect to the API's auth page
        if has_access():
            return view(*args, **kwargs)
        else:
            redirect_args = {
                'scope': ' '.join(SCOPES),
                'client_id': CLIENT_ID,
                'redirect_uri': REDIRECT_URI,
                'response_type': 'code'}
            return redirect('%s/authorize?%s'% (AUTH_BASE, urlencode(redirect_args)))

    return authorized_view


