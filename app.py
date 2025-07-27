from flask import Flask, request, jsonify
import tempfile
import os
from birdnet_analyzer.analyze import analyze

app = Flask(__name__)

@app.route('/analyze', methods=['POST'])
def analyze_audio():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file'}), 400
    
    audio_file = request.files['audio']
    
    # Temporäre Datei erstellen
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
        audio_file.save(temp_file.name)
        
        # BirdNET Analysis aufrufen
        results = analyze.analyze_file(temp_file.name)
        
        # Aufräumen
        os.unlink(temp_file.name)
        
        return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
