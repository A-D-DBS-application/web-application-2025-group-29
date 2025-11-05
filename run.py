from flask import Flask
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Run on localhost only and use port 5001 to avoid macOS AirPlay conflict
    # macOS AirPlay Receiver uses port 5000 by default
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    print(f"Starting Flask app on http://127.0.0.1:{port}")
    app.run(debug=True, host='127.0.0.1', port=port)

