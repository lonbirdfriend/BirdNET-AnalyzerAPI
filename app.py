from flask import Flask, request, jsonify
import analyze
import tempfile
import os

app = Flask(__name__)

@app.route('/analyze', methods=['POST'])
def analyze_audio():
    # Audio-Datei empfangen und mit BirdNET analysieren
    # Ergebnis als JSON zurückgeben
    pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
