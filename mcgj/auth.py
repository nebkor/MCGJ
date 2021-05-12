from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
import logging
import os
from authlib.integrations.flask_client import OAuth
from werkzeug.exceptions import HTTPException
from . import db
from dotenv import load_dotenv

load_dotenv()


bp = Blueprint('auth', __name__)

rc = OAuth(current_app).register(
    'Recurse Center',
    api_base_url='https://www.recurse.com/api/v1/',
    authorize_url='https://www.recurse.com/oauth/authorize',
    access_token_url='https://www.recurse.com/oauth/token',
    client_id=os.getenv('CLIENT_ID'),
    client_secret=os.getenv('CLIENT_SECRET'),
)

token = os.getenv('RC_API_ACCESS_TOKEN')

@bp.route('/login')
def login():
    return 'Login'

@bp.route('/logout')
def logout():
    return 'Logout'

@bp.route('/auth/recurse')
def auth_recurse_redirect():
    "Redirect to the Recurse Center OAuth2 endpoint"
    callback = os.getenv('CLIENT_CALLBACK')
    return rc.authorize_redirect(callback)

@bp.route('/auth/callback', methods=['GET', 'POST'])
def auth_recurse_callback():
    "Process the results of a successful OAuth2 authentication"

    try:
        token = rc.authorize_access_token()
    except HTTPException:
        logging.error(
            'Error %s parsing OAuth2 response: %s',
            request.args.get('error', '(no error code)'),
            request.args.get('error_description', '(no error description'),
        )
        return (jsonify({
            'message': 'Access Denied',
            'error': request.args.get('error', '(no error code)'),
            'error_description': request.args.get('error_description', '(no error description'),
        }), 403)

    me = get_rc_profile()
    logging.info("Logged in: %s", me.get('name', ''))

    return redirect(url_for('index'))


def get_rc_profile():
    "Return the RC API information for the currently logged in user"

    headers = {'Authorization': f'Bearer {token}'}
    url = 'https://www.recurse.com/api/v1/profiles/me'

    r = requests.get(url, headers=headers)
    if r.status_code != requests.codes['ok']:
        r.raise_for_status()

    me = r.json()

    return me
