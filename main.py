from apps import api, oauth, create_app_from_modules


app = create_app_from_modules(api, oauth)


@app.route('/')
def index():
    return 'Hello from Flask!'


if __name__ == '__main__':
    app.run(port=5000)
