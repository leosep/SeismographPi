from app import create_app

app = create_app()

if __name__ == '__main__':
    # threaded=True is required: the /events/stream SSE endpoint holds its
    # connection open indefinitely, and Flask's dev server is
    # single-threaded by default. Without this, the open SSE connection
    # would block every other request (including '/' and '/data').
    app.run(debug=True, host='0.0.0.0', threaded=True)
