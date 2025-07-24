from app import create_app

app = create_app()
app.config["DEBUG"] = True
app.config["USE_RELOADER"] = True

if __name__ == '__main__':
    app.run(
        debug=app.config["DEBUG"],
        use_reloader=app.config["USE_RELOADER"],
        host='0.0.0.0',
        port=8080
    )
