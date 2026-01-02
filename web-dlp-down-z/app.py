import os
from app import create_app
from dotenv import load_dotenv

load_dotenv()

app = create_app()
app.config["DEBUG"] = os.environ.get("DEBUG")
app.config["USE_RELOADER"] = os.environ.get("USE_RELOADER")

if __name__ == '__main__':
    app.run(
        debug=app.config["DEBUG"],
        use_reloader=app.config["USE_RELOADER"],
        host=os.environ.get("HOST"),
        port=os.environ.get("PORT")
    )
