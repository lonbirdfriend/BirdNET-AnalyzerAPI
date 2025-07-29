import os
import threading
import time
import tempfile
import requests
import json
import subprocess
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import signal
import sys

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Erstelle Upload-Ordner wenn nicht vorhanden
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static', exist_ok=True)

# Global variable für BirdNET Server Process
birdnet_server = None
BIRDNET_HOST = '127.0.0.1'
BIRDNET_PORT = 8080

def start_birdnet_server():
    """Startet den BirdNET Analyzer Server im Hintergrund"""
    global birdnet_server
    try:
        # Starte BirdNET Server
        birdnet_server = subprocess.Popen([
            'python', '-m', 'birdnet_analyzer.server',
            '--host', BIRDNET_HOST,
            '--port', str(BIRDNET_PORT),
            '--spath', app.config['UPLOAD_FOLDER'],
            '--locale', 'de'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Warte bis Server bereit ist
        for i in range(30):  # 30 Sekunden timeout
            try:
                response = requests.get(f'http://{BIRDNET_HOST}:{BIRDNET_PORT}', timeout=1)
                if response.status_code == 200:
                    print(f"BirdNET Server erfolgreich gestartet auf {BIRDNET_HOST}:{BIRDNET_PORT}")
                    return True
            except:
                time.sleep(1)
        
        print("BirdNET Server konnte nicht gestartet werden")
        return False
        
    except Exception as e:
        print(f"Fehler beim Starten des BirdNET Servers: {e}")
        return False

def stop_birdnet_server():
    """Stoppt den BirdNET Server"""
    global birdnet_server
    if birdnet_server:
        birdnet_server.terminate()
        birdnet_server.wait()
        birdnet_server = None

def signal_handler(sig, frame):
    """Handler für sauberes Beenden"""
    print("Beende BirdNET Server...")
    stop_birdnet_server()
    sys.exit(0)

# Signal Handler registrieren
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

@app.route('/')
def index():
    """Hauptseite mit Audio-Recorder"""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_audio():
    """Analysiert hochgeladene Audiodatei mit BirdNET"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'Keine Audiodatei gefunden'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'Keine Datei ausgewählt'}), 400
        
        # Standortdaten aus dem Request
        lat = request.form.get('lat', -1)
        lon = request.form.get('lon', -1)
        
        # Temporäre Datei speichern
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file.save(temp_file.name)
            temp_filename = temp_file.name
        
        try:
            # Metadata für BirdNET vorbereiten
            metadata = {
                'lat': float(lat) if lat != '-1' else -1,
                'lon': float(lon) if lon != '-1' else -1,
                'week': -1,  # Ganzjährig
                'sensitivity': 1.0,
                'overlap': 0,
                'sf_thresh': 0.03
            }
            
            # Audio-Datei lesen
            with open(temp_filename, 'rb') as f:
                audio_data = f.read()
            
            # Request an BirdNET Server senden
            files = {'audio': ('recording.wav', audio_data, 'audio/wav')}
            data = {'meta': json.dumps(metadata)}
            
            response = requests.post(
                f'http://{BIRDNET_HOST}:{BIRDNET_PORT}',
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('msg') == 'success':
                    # Ergebnisse formatieren
                    birds = []
                    for bird_data in result.get('results', []):
                        species_name = bird_data[0]
                        confidence = bird_data[1]
                        
                        # Deutschen und wissenschaftlichen Namen trennen
                        if '_' in species_name:
                            scientific, common = species_name.split('_', 1)
                        else:
                            scientific = species_name
                            common = species_name
                        
                        birds.append({
                            'scientific_name': scientific,
                            'common_name': common,
                            'confidence': round(confidence * 100, 1)
                        })
                    
                    return jsonify({
                        'success': True,
                        'birds': birds,
                        'location_used': lat != '-1' and lon != '-1'
                    })
                else:
                    return jsonify({'error': f'BirdNET Fehler: {result.get("msg", "Unbekannter Fehler")}'}), 500
            else:
                return jsonify({'error': f'Server Fehler: {response.status_code}'}), 500
                
        finally:
            # Temporäre Datei löschen
            try:
                os.unlink(temp_filename)
            except:
                pass
                
    except Exception as e:
        print(f"Fehler bei der Analyse: {e}")
        return jsonify({'error': f'Analyse-Fehler: {str(e)}'}), 500

@app.route('/health')
def health():
    """Health Check Endpoint für Render"""
    try:
        # Prüfe ob BirdNET Server läuft
        response = requests.get(f'http://{BIRDNET_HOST}:{BIRDNET_PORT}', timeout=2)
        return jsonify({'status': 'healthy', 'birdnet_server': 'running'})
    except:
        return jsonify({'status': 'unhealthy', 'birdnet_server': 'not running'}), 503

@app.route('/static/<filename>')
def static_files(filename):
    """Statische Dateien servieren"""
    return send_from_directory('static', filename)

def create_static_files():
    """Erstellt notwendige statische Dateien"""
    
    # JavaScript für Audio-Recording
    recorder_js = """
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
    }

    async initialize() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.mediaRecorder.ondataavailable = (event) => {
                this.audioChunks.push(event.data);
            };

            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.convertAndUpload(audioBlob);
                this.audioChunks = [];
            };

            return true;
        } catch (error) {
            console.error('Fehler beim Zugriff auf Mikrofon:', error);
            return false;
        }
    }

    startRecording() {
        if (this.mediaRecorder && !this.isRecording) {
            this.audioChunks = [];
            this.mediaRecorder.start();
            this.isRecording = true;
            return true;
        }
        return false;
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            return true;
        }
        return false;
    }

    async convertAndUpload(audioBlob) {
        try {
            // Konvertiere zu WAV
            const arrayBuffer = await audioBlob.arrayBuffer();
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            
            const wavBlob = this.audioBufferToWav(audioBuffer);
            await this.uploadAudio(wavBlob);
            
        } catch (error) {
            console.error('Fehler bei der Konvertierung:', error);
            showError('Fehler bei der Audio-Verarbeitung');
        }
    }

    audioBufferToWav(buffer) {
        const numChannels = buffer.numberOfChannels;
        const sampleRate = buffer.sampleRate;
        const format = 1; // PCM
        const bitDepth = 16;

        const result = new ArrayBuffer(44 + buffer.length * numChannels * 2);
        const view = new DataView(result);

        // WAV Header schreiben
        const writeString = (offset, string) => {
            for (let i = 0; i < string.length; i++) {
                view.setUint8(offset + i, string.charCodeAt(i));
            }
        };

        let offset = 0;
        writeString(offset, 'RIFF'); offset += 4;
        view.setUint32(offset, 36 + buffer.length * numChannels * 2, true); offset += 4;
        writeString(offset, 'WAVE'); offset += 4;
        writeString(offset, 'fmt '); offset += 4;
        view.setUint32(offset, 16, true); offset += 4;
        view.setUint16(offset, format, true); offset += 2;
        view.setUint16(offset, numChannels, true); offset += 2;
        view.setUint32(offset, sampleRate, true); offset += 4;
        view.setUint32(offset, sampleRate * numChannels * bitDepth / 8, true); offset += 4;
        view.setUint16(offset, numChannels * bitDepth / 8, true); offset += 2;
        view.setUint16(offset, bitDepth, true); offset += 2;
        writeString(offset, 'data'); offset += 4;
        view.setUint32(offset, buffer.length * numChannels * 2, true); offset += 4;

        // Audio-Daten schreiben
        const channels = [];
        for (let i = 0; i < numChannels; i++) {
            channels.push(buffer.getChannelData(i));
        }

        let sampleIndex = 0;
        while (sampleIndex < buffer.length) {
            for (let channel = 0; channel < numChannels; channel++) {
                const sample = Math.max(-1, Math.min(1, channels[channel][sampleIndex]));
                view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
                offset += 2;
            }
            sampleIndex++;
        }

        return new Blob([result], { type: 'audio/wav' });
    }

    async uploadAudio(audioBlob) {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.wav');
        
        // Standortdaten hinzufügen falls verfügbar
        const location = await getCurrentLocation();
        formData.append('lat', location.lat);
        formData.append('lon', location.lon);

        showLoading(true);

        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            
            if (result.success) {
                displayResults(result.birds, result.location_used);
            } else {
                showError(result.error || 'Unbekannter Fehler');
            }
        } catch (error) {
            console.error('Upload-Fehler:', error);
            showError('Fehler beim Hochladen der Audiodatei');
        } finally {
            showLoading(false);
        }
    }
}

async function getCurrentLocation() {
    return new Promise((resolve) => {
        if ('geolocation' in navigator) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    resolve({
                        lat: position.coords.latitude,
                        lon: position.coords.longitude
                    });
                },
                () => {
                    resolve({ lat: -1, lon: -1 });
                },
                { timeout: 5000 }
            );
        } else {
            resolve({ lat: -1, lon: -1 });
        }
    });
}

function showLoading(show) {
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    
    if (show) {
        loading.style.display = 'block';
        results.style.display = 'none';
    } else {
        loading.style.display = 'none';
    }
}

function showError(message) {
    const results = document.getElementById('results');
    results.innerHTML = `<div class="error">❌ ${message}</div>`;
    results.style.display = 'block';
}

function displayResults(birds, locationUsed) {
    const results = document.getElementById('results');
    
    if (!birds || birds.length === 0) {
        results.innerHTML = '<div class="no-results">🔍 Keine Vögel erkannt</div>';
    } else {
        let html = '<h3>🐦 Erkannte Vögel:</h3>';
        
        if (locationUsed) {
            html += '<div class="location-info">📍 Standortdaten wurden für bessere Genauigkeit verwendet</div>';
        }
        
        html += '<div class="bird-list">';
        birds.forEach(bird => {
            const confidenceColor = bird.confidence > 70 ? '#4CAF50' : bird.confidence > 40 ? '#FF9800' : '#f44336';
            html += `
                <div class="bird-item">
                    <div class="bird-name">
                        <strong>${bird.common_name}</strong>
                        <div class="scientific-name">${bird.scientific_name}</div>
                    </div>
                    <div class="confidence" style="color: ${confidenceColor}">
                        ${bird.confidence}%
                    </div>
                </div>
            `;
        });
        html += '</div>';
        
        results.innerHTML = html;
    }
    
    results.style.display = 'block';
}

// Globale Variablen
let recorder = null;
let recordButton = null;

// Initialisierung
document.addEventListener('DOMContentLoaded', async function() {
    recordButton = document.getElementById('recordButton');
    recorder = new AudioRecorder();
    
    const initialized = await recorder.initialize();
    if (!initialized) {
        showError('Mikrofon-Zugriff nicht möglich. Bitte erlauben Sie den Zugriff auf das Mikrofon.');
        recordButton.disabled = true;
        return;
    }

    recordButton.addEventListener('click', function() {
        if (recorder.isRecording) {
            recorder.stopRecording();
            recordButton.textContent = '🎤 Aufnahme starten';
            recordButton.classList.remove('recording');
        } else {
            if (recorder.startRecording()) {
                recordButton.textContent = '⏹️ Aufnahme beenden';
                recordButton.classList.add('recording');
                
                // Verstecke vorherige Ergebnisse
                document.getElementById('results').style.display = 'none';
            }
        }
    });
});
"""
    
    with open('static/recorder.js', 'w', encoding='utf-8') as f:
        f.write(recorder_js)

    # CSS Styling
    css_content = """
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
    background-color: #f5f5f5;
    color: #333;
}

.container {
    background: white;
    border-radius: 12px;
    padding: 30px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

h1 {
    text-align: center;
    color: #2c3e50;
    margin-bottom: 30px;
}

.recorder-section {
    text-align: center;
    margin-bottom: 30px;
}

#recordButton {
    background: linear-gradient(45deg, #4CAF50, #45a049);
    color: white;
    border: none;
    padding: 15px 30px;
    font-size: 16px;
    border-radius: 25px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
}

#recordButton:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
}

#recordButton.recording {
    background: linear-gradient(45deg, #f44336, #da190b);
    animation: pulse 1s infinite;
}

@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

.instructions {
    background: #e3f2fd;
    padding: 20px;
    border-radius: 8px;
    margin: 20px 0;
    border-left: 4px solid #2196F3;
}

.instructions h3 {
    margin-top: 0;
    color: #1976D2;
}

.instructions ul {
    margin: 10px 0;
    padding-left: 20px;
}

.instructions li {
    margin: 5px 0;
}

#loading {
    text-align: center;
    padding: 20px;
    font-size: 18px;
    color: #666;
    display: none;
}

#results {
    margin-top: 20px;
    display: none;
}

.error {
    background: #ffebee;
    color: #c62828;
    padding: 15px;
    border-radius: 8px;
    border-left: 4px solid #f44336;
}

.no-results {
    background: #fff3e0;
    color: #e65100;
    padding: 15px;
    border-radius: 8px;
    text-align: center;
    border-left: 4px solid #ff9800;
}

.location-info {
    background: #e8f5e8;
    color: #2e7d32;
    padding: 10px;
    border-radius: 6px;
    margin-bottom: 15px;
    font-size: 14px;
    border-left: 4px solid #4caf50;
}

.bird-list {
    space-y: 10px;
}

.bird-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px;
    background: #fafafa;
    border-radius: 8px;
    margin-bottom: 10px;
    border: 1px solid #e0e0e0;
    transition: all 0.2s ease;
}

.bird-item:hover {
    background: #f0f0f0;
    border-color: #d0d0d0;
}

.bird-name strong {
    color: #2c3e50;
    font-size: 16px;
}

.scientific-name {
    color: #666;
    font-style: italic;
    font-size: 14px;
    margin-top: 2px;
}

.confidence {
    font-weight: bold;
    font-size: 16px;
    padding: 5px 10px;
    border-radius: 15px;
    background: rgba(255, 255, 255, 0.8);
}

.footer {
    text-align: center;
    margin-top: 30px;
    padding-top: 20px;
    border-top: 1px solid #eee;
    color: #666;
    font-size: 14px;
}

@media (max-width: 600px) {
    body {
        padding: 10px;
    }
    
    .container {
        padding: 20px;
    }
    
    .bird-item {
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
    }
    
    .confidence {
        align-self: flex-end;
    }
}
"""
    
    with open('static/styles.css', 'w', encoding='utf-8') as f:
        f.write(css_content)

# HTML Template erstellen
def create_template():
    os.makedirs('templates', exist_ok=True)
    
    html_template = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BirdNET - Vogelerkennung</title>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
    <div class="container">
        <h1>🐦 BirdNET Vogelerkennung</h1>
        
        <div class="instructions">
            <h3>📋 Anleitung:</h3>
            <ul>
                <li>Klicken Sie auf "Aufnahme starten" um eine Audioaufnahme zu beginnen</li>
                <li>Halten Sie das Gerät in Richtung der Vogelgeräusche</li>
                <li>Klicken Sie auf "Aufnahme beenden" wenn Sie fertig sind</li>
                <li>Die Analyse erfolgt automatisch und zeigt erkannte Vogelarten an</li>
                <li>Für bessere Ergebnisse erlauben Sie den Zugriff auf Ihren Standort</li>
            </ul>
        </div>

        <div class="recorder-section">
            <button id="recordButton">🎤 Aufnahme starten</button>
        </div>

        <div id="loading">
            <div>🔄 Analysiere Audioaufnahme...</div>
            <div style="margin-top: 10px; font-size: 14px;">Dies kann einen Moment dauern</div>
        </div>

        <div id="results"></div>

        <div class="footer">
            <p>Powered by <strong>BirdNET</strong> - Cornell Lab of Ornithology & Chemnitz University of Technology</p>
            <p>Diese App nutzt maschinelles Lernen zur Erkennung von Vogelgeräuschen</p>
        </div>
    </div>

    <script src="/static/recorder.js"></script>
</body>
</html>"""
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html_template)

if __name__ == '__main__':
    # Erstelle statische Dateien und Templates
    create_static_files()
    create_template()
    
    # Starte BirdNET Server
    print("Starte BirdNET Server...")
    if not start_birdnet_server():
        print("FEHLER: BirdNET Server konnte nicht gestartet werden!")
        sys.exit(1)
    
    # Starte Flask App
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
