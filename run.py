import os
from dotenv import load_dotenv
from app import create_app

load_dotenv()

app = create_app()

if __name__ == "__main__":
    host = os.getenv("TAILSCALE_IP", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    # Bind to Tailscale IP only — never 0.0.0.0
    app.run(host=host, port=port, debug=True)
