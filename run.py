from app import create_app
import os

# Maak de Flask app aan via de factory
app = create_app()

# Alleen lokaal debuggen als je run.py direct uitvoert
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting Flask app on http://127.0.0.1:{port}")
    app.run(debug=True, host="0.0.0.0", port=port)
# Dit bestand wordt gebruikt om de Flask app te starten.