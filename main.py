"""main

This entrypoint is only used for development purposes.
It will be removed in production.
"""

from flask import redirect, url_for

from apps import api, create_app_from_modules, oauth

app = create_app_from_modules(api, oauth)


@app.route('/')
def index():
    return "Campus API running", 200

@app.route('/login')
def login():
    return redirect(url_for('oauth.google.authorize', target='/home'))

@app.route('/home')
def home():
    # TODO: Implement authentication check
    # TODO: Implement user session management
    return "Welcome to the home page! You are authenticated."


if __name__ == '__main__':
    app.run('127.0.0.1', port=5000)
