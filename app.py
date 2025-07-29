import os
import tempfile
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import numpy as np
from datetime import datetime

# TensorFlow Umgebung konfigurieren
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Weniger TF Logs
os.environ['CUDA_VISIBLE_DEVICES'] = ''   # CPU nur

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Erstelle Ordner wenn nicht vorhanden
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static', exist_ok=True)

# BirdNET Analyzer laden
BIRDNET_AVAILABLE = False
analyzer = None

def initialize_birdnet():
    """Initialisiert BirdNET mit Fehlerbehandlung"""
    global BIRDNET_AVAILABLE, analyzer
    
    try:
        print("Lade BirdNET Dependencies...")
        
        # TensorFlow importieren
        import tensorflow as tf
        print(f"TensorFlow Version: {tf.__version__}")
        
        # BirdNET importieren
        from birdnetlib import Recording
        from birdnetlib.analyzer import Analyzer
        
        print("Initialisiere BirdNET Analyzer...")
        analyzer = Analyzer()
        
        BIRDNET_AVAILABLE = True
        print("✅ BirdNET erfolgreich geladen!")
        return True
        
    except ImportError as e:
        print(f"❌ Import Fehler: {e}")
        return False
    except Exception as e:
        print(f"❌ BirdNET Initialisierung fehlgeschlagen: {e}")
        return False

@app.route('/')
def index():
    """Hauptseite mit Audio-Recorder"""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_audio():
    """Analysiert hochgeladene Audiodatei mit BirdNET"""
    if not BIRDNET_AVAILABLE or analyzer is None:
        return jsonify({'error': 'BirdNET nicht verfügbar. Server wird möglicherweise noch initialisiert.'}), 500
    
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'Keine Audiodatei gefunden'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'Keine Datei ausgewählt'}), 400
        
        # Standortdaten aus dem Request
        lat = float(request.form.get('lat', -1))
        lon = float(request.form.get('lon', -1))
        
        print(f"Analysiere Audio-Datei (Größe: {len(audio_file.read())} bytes)")
        audio_file.seek(0)  # Reset file pointer
        
        # Temporäre Datei speichern
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            audio_file.save(temp_file.name)
            temp_filename = temp_file.name
        
        try:
            from birdnetlib import Recording
            
            # Recording-Parameter konfigurieren
            recording_kwargs = {
                'min_conf': 0.1  # Niedrigere Schwelle für mehr Ergebnisse
            }
            
            # GPS-Daten hinzufügen falls verfügbar
            if lat != -1 and lon != -1:
                recording_kwargs['lat'] = lat
                recording_kwargs['lon'] = lon
                recording_kwargs['date'] = datetime.now()
                print(f"Verwende GPS-Koordinaten: {lat:.4f}, {lon:.4f}")
            
            # BirdNET Recording erstellen
            print("Erstelle BirdNET Recording...")
            recording = Recording(
                analyzer,
                temp_filename,
                **recording_kwargs
            )
            
            # Analyse durchführen
            print("Starte BirdNET Analyse...")
            recording.analyze()
            print(f"Analyse abgeschlossen. Erkennungen: {len(recording.detections)}")
            
            if not recording.detections:
                return jsonify({
                    'success': True,
                    'birds': [],
                    'location_used': lat != -1 and lon != -1,
                    'message': 'Keine Vögel erkannt. Versuchen Sie eine lautere/längere Aufnahme.'
                })
            
            # Ergebnisse verarbeiten
            birds = []
            species_seen = set()
            
            for detection in recording.detections:
                scientific_name = detection.get('scientific_name', 'Unbekannt')
                
                # Vermeide Duplikate (höchste Konfidenz behalten)
                if scientific_name not in species_seen:
                    birds.append({
                        'scientific_name': scientific_name,
                        'common_name': detection.get('common_name', 'Unbekannt'),
                        'confidence': round(detection.get('confidence', 0) * 100, 1),
                        'start_time': round(detection.get('start_time', 0), 1),
                        'end_time': round(detection.get('end_time', 0), 1)
                    })
                    species_seen.add(scientific_name)
            
            # Nach Konfidenz sortieren
            birds.sort(key=lambda x: x['confidence'], reverse=True)
            
            return jsonify({
                'success': True,
                'birds': birds[:15],  # Top 15 Ergebnisse
                'location_used': lat != -1 and lon != -1,
                'total_detections': len(recording.detections)
            })
                
        finally:
            # Temporäre Datei löschen
            try:
                os.unlink(temp_filename)
            except:
                pass
                
    except Exception as e:
        print(f"❌ Analyse Fehler: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Analyse-Fehler: {str(e)}'}), 500

@app.route('/health')
def health():
    """Health Check für Render"""
    return jsonify({
        'status': 'healthy',
        'birdnet_available': BIRDNET_AVAILABLE,
        'analyzer_loaded': analyzer is not None
    })

@app.route('/static/<filename>')
def static_files(filename):
    """Statische Dateien servieren"""
    return send_from_directory('static', filename)

def create_static_files():
    """Erstellt CSS und JavaScript Dateien"""
    
    # CSS
    css_content = """
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    color: #333;
}

.container {
    background: rgba(255, 255, 255, 0.95);
    border-radius: 20px;
    padding: 40px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(10px);
}

h1 {
    text-align: center;
    color: #2c3e50;
    margin-bottom: 30px;
    font-size: 2.5em;
    text-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.status {
    text-align: center;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
    font-weight: bold;
}

.status.loading {
    background: #fff3cd;
    color: #856404;
    border: 2px solid #ffeaa7;
}

.status.ready {
    background: #d4edda;
    color: #155724;
    border: 2px solid #00b894;
}

.status.error {
    background: #f8d7da;
    color: #721c24;
    border: 2px solid #e74c3c;
}

.recorder-section {
    text-align: center;
    margin: 30px 0;
}

#recordButton {
    background: linear-gradient(45deg, #00b894, #00a085);
    color: white;
    border: none;
    padding: 20px 40px;
    font-size: 18px;
    border-radius: 50px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 8px 15px rgba(0, 184, 148, 0.3);
    min-width: 200px;
    font-weight: bold;
}

#recordButton:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 20px rgba(0, 184, 148, 0.4);
}

#recordButton.recording {
    background: linear-gradient(45deg, #e74c3c, #c0392b);
    animation: pulse 1.5s infinite;
}

#recordButton:disabled {
    background: #bdc3c7;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}

@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

.instructions {
    background: linear-gradient(135deg, #74b9ff, #0984e3);
    color: white;
    padding: 25px;
    border-radius: 15px;
    margin: 20px 0;
    box-shadow: 0 5px 15px rgba(116, 185, 255, 0.3);
}

.instructions h3 {
    margin-top: 0;
    font-size: 1.3em;
}

.instructions ul {
    margin: 15px 0;
    padding-left: 20px;
}

.instructions li {
    margin: 8px 0;
    line-height: 1.4;
}

#loading {
    text-align: center;
    padding: 30px;
    display: none;
}

.loading-spinner {
    width: 50px;
    height: 50px;
    border: 5px solid #f3f3f3;
    border-top: 5px solid #74b9ff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 20px;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

#results {
    margin-top: 30px;
    display: none;
}

.error {
    background: linear-gradient(135deg, #fd79a8, #e84393);
    color: white;
    padding: 20px;
    border-radius: 10px;
    text-align: center;
    box-shadow: 0 5px 15px rgba(232, 67, 147, 0.3);
}

.no-results {
    background: linear-gradient(135deg, #fdcb6e, #e17055);
    color: white;
    padding: 20px;
    border-radius: 10px;
    text-align: center;
    box-shadow: 0 5px 15px rgba(225, 112, 85, 0.3);
}

.location-info {
    background: linear-gradient(135deg, #00b894, #00a085);
    color: white;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
    text-align: center;
    box-shadow: 0 5px 15px rgba(0, 184, 148, 0.3);
}

.bird-list {
    display: grid;
    gap: 15px;
}

.bird-item {
    background: linear-gradient(135deg, #ffffff, #f8f9fa);
    padding: 20px;
    border-radius: 15px;
    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
    border-left: 5px solid #74b9ff;
    transition: all 0.3s ease;
}

.bird-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
}

.bird-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}

.bird-name {
    font-size: 1.2em;
    font-weight: bold;
    color: #2c3e50;
}

.scientific-name {
    color: #636e72;
    font-style: italic;
    font-size: 0.9em;
    margin-top: 5px;
}

.confidence {
    font-weight: bold;
    font-size: 1.1em;
    padding: 8px 15px;
    border-radius: 20px;
    color: white;
    min-width: 60px;
    text-align: center;
}

.time-info {
    color: #636e72;
    font-size: 0.85em;
    margin-top: 5px;
}

.footer {
    text-align: center;
    margin-top: 40px;
    padding-top: 30px;
    border-top: 2px solid #ddd;
    color: #666;
}

@media (max-width: 600px) {
    body { padding: 10px; }
    .container { padding: 20px; }
    h1 { font-size: 2em; }
    .bird-header { flex-direction: column; align-items: flex-start; gap: 10px; }
    .confidence { align-self: flex-end; }
}
"""
    
    with open('static/styles.css', 'w', encoding='utf-8') as f:
        f.write(css_content)

    # JavaScript
    js_content = """
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.stream = null;
    }

    async initialize() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 44100
                } 
            });
            
            this.mediaRecorder = new MediaRecorder(this.stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                this.convertAndUpload(audioBlob);
                this.audioChunks = [];
            };

            return true;
        } catch (error) {
            console.error('Mikrofon-Fehler:', error);
            return false;
        }
    }

    startRecording() {
        if (this.mediaRecorder && !this.isRecording) {
            this.audioChunks = [];
            this.mediaRecorder.start(100); // Sammle Daten alle 100ms
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
            showLoading(true);
            
            // Konvertiere zu WAV
            const arrayBuffer = await audioBlob.arrayBuffer();
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            
            const wavBlob = this.audioBufferToWav(audioBuffer);
            await this.uploadAudio(wavBlob);
            
        } catch (error) {
            console.error('Konvertierung fehlgeschlagen:', error);
            showError('Fehler bei der Audio-Verarbeitung: ' + error.message);
            showLoading(false);
        }
    }

    audioBufferToWav(buffer) {
        const numChannels = buffer.numberOfChannels;
        const sampleRate = buffer.sampleRate;
        const format = 1;
        const bitDepth = 16;

        const result = new ArrayBuffer(44 + buffer.length * numChannels * 2);
        const view = new DataView(result);

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
        
        const location = await getCurrentLocation();
        formData.append('lat', location.lat);
        formData.append('lon', location.lon);

        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            
            if (result.success) {
                displayResults(result.birds, result.location_used, result.total_detections, result.message);
            } else {
                showError(result.error || 'Unbekannter Fehler');
            }
        } catch (error) {
            console.error('Upload-Fehler:', error);
            showError('Netzwerk-Fehler: ' + error.message);
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
                () => resolve({ lat: -1, lon: -1 }),
                { timeout: 5000, enableHighAccuracy: true }
            );
        } else {
            resolve({ lat: -1, lon: -1 });
        }
    });
}

function showLoading(show) {
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    
    loading.style.display = show ? 'block' : 'none';
    if (show) results.style.display = 'none';
}

function showError(message) {
    const results = document.getElementById('results');
    results.innerHTML = `<div class="error">❌ ${message}</div>`;
    results.style.display = 'block';
}

function displayResults(birds, locationUsed, totalDetections, message) {
    const results = document.getElementById('results');
    
    let html = '';
    
    if (locationUsed) {
        html += '<div class="location-info">📍 GPS-Koordinaten für bessere Genauigkeit verwendet</div>';
    }
    
    if (!birds || birds.length === 0) {
        html += `<div class="no-results">🔍 ${message || 'Keine Vögel erkannt'}</div>`;
    } else {
        html += `<h3>🐦 Erkannte Vögel (${birds.length} von ${totalDetections} Erkennungen):</h3>`;
        html += '<div class="bird-list">';
        
        birds.forEach(bird => {
            const confidence = bird.confidence;
            let confidenceColor = '#e74c3c';
            if (confidence > 70) confidenceColor = '#00b894';
            else if (confidence > 40) confidenceColor = '#fdcb6e';
            
            html += `
                <div class="bird-item">
                    <div class="bird-header">
                        <div>
                            <div class="bird-name">${bird.common_name}</div>
                            <div class="scientific-name">${bird.scientific_name}</div>
                            ${bird.start_time !== undefined ? 
                                `<div class="time-info">⏱️ ${bird.start_time}s - ${bird.end_time}s</div>` : ''
                            }
                        </div>
                        <div class="confidence" style="background: ${confidenceColor}">
                            ${confidence}%
                        </div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
    }
    
    results.innerHTML = html;
    results.style.display = 'block';
}

// Globale Variablen
let recorder = null;
let recordButton = null;

// Initialisierung
document.addEventListener('DOMContentLoaded', async function() {
    recordButton = document.getElementById('recordButton');
    const statusDiv = document.getElementById('status');
    
    // Überprüfe Server-Status
    try {
        const response = await fetch('/health');
        const health = await response.json();
        
        if (health.birdnet_available) {
            statusDiv.innerHTML = '✅ BirdNET bereit für Analysen';
            statusDiv.className = 'status ready';
        } else {
            statusDiv.innerHTML = '⚠️ BirdNET wird geladen, bitte warten...';
            statusDiv.className = 'status loading';
            recordButton.disabled = true;
        }
    } catch (error) {
        statusDiv.innerHTML = '❌ Server nicht erreichbar';
        statusDiv.className = 'status error';
        recordButton.disabled = true;
    }
    
    // Mikrofon initialisieren
    recorder = new AudioRecorder();
    const initialized = await recorder.initialize();
    
    if (!initialized) {
        showError('Mikrofon-Zugriff nicht möglich. Bitte erlauben Sie den Zugriff.');
        recordButton.disabled = true;
        return;
    }

    recordButton.addEventListener('click', function() {
        if (recorder.isRecording) {
            recorder.stopRecording();
            recordButton.textContent = '🎤 Aufnahme starten';
            recordButton.classList.remove('recording');
            document.getElementById('results').style.display = 'none';
        } else {
            if (recorder.startRecording()) {
                recordButton.textContent = '⏹️ Aufnahme beenden';
                recordButton.classList.add('recording');
            }
        }
    });
});
"""
    
    with open('static/recorder.js', 'w', encoding='utf-8') as f:
        f.write(js_content)

def create_template():
    """Erstellt HTML Template"""
    os.makedirs('templates', exist_ok=True)
    
    html_template = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BirdNET - KI Vogelerkennung</title>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
    <div class="container">
        <h1>🐦 BirdNET Vogelerkennung</h1>
        
        <div id="status" class="status loading">
            🔄 System wird initialisiert...
        </div>
        
        <div class="instructions">
            <h3>📋 So funktioniert's:</h3>
            <ul>
                <li><strong>Aufnahme starten:</strong> Klicken Sie den Button und halten Sie Ihr Gerät in Richtung der Vogelgeräusche</li>
                <li><strong>Optimale Bedingungen:</strong> Ruhige Umgebung, deutliche Vogelrufe, 10-30 Sekunden Aufnahme</li>
                <li><strong>GPS aktivieren:</strong> Für bessere Ergebnisse erlauben Sie den Standortzugriff</li>
                <li><strong>Geduld:</strong> Die KI-Analyse kann 10-30 Sekunden dauern</li>
            </ul>
        </div>

        <div class="recorder-section">
            <button id="recordButton" disabled>🎤 Aufnahme starten</button>
        </div>

        <div id="loading">
            <div class="loading-spinner"></div>
            <div><strong>🤖 KI analysiert Ihre Aufnahme...</strong></div>
            <div style="margin-top: 10px; font-size: 14px; color: #666;">
                Dies kann je nach Aufnahmelänge 10-30 Sekunden dauern
            </div>
        </div>

        <div id="results"></div>

        <div class="footer">
            <p><strong>🧠 Powered by BirdNET</strong></p>
            <p>Cornell Lab of Ornithology & Chemnitz University of Technology</p>
            <p>Erkennt über 6.000 Vogelarten weltweit mit Künstlicher Intelligenz</p>
        </div>
    </div>

    <script src="/static/recorder.js"></script>
</body>
</html>"""
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html_template)

if __name__ == '__main__':
    print("🚀 Starte BirdNET Web-App...")
    
    # Erstelle statische Dateien
    create_static_files()
    create_template()
    
    # Initialisiere BirdNET im Hintergrund
    print("🔄 Initialisiere BirdNET...")
    initialize_birdnet()
    
    # Starte Flask App
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Server startet auf Port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
