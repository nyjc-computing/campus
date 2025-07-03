"""main

This entrypoint is only used for development purposes.
It will be removed in production.
"""
import os

from flask import redirect, url_for

from apps import api, oauth, create_app_from_modules

# Set environment variables for OAuth2 configuration
os.environ['REDIRECT_URI'] = ""

app = create_app_from_modules(api, oauth)


@app.route('/')
def index():
    return redirect(url_for('oauth.google.authorize', target='/home'))

@app.route('/home')
def home():
    # TODO: Implement authentication check
    # TODO: Implement user session management
    return "Welcome to the home page! You are authenticated."


if __name__ == '__main__':
    app.run('127.0.0.1', port=5000)
