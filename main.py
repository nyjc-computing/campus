from apps import api

app = api.create_app()


@app.route('/')
def index():
    return 'Hello from Flask!'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
