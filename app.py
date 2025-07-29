import os
import tempfile
from flask import Flask, render_template_string, request, jsonify
from datetime import datetime

# TensorFlow Umgebung
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['CUDA_VISIBLE_DEVICES'] = ''

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# BirdNET initialisieren
try:
    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer
    analyzer = Analyzer()
    print("✅ BirdNET geladen")
except Exception as e:
    print(f"❌ BirdNET Fehler: {e}")
    analyzer = None

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BirdNET</title>
    <style>
        body { font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }
        .container { text-align: center; }
        button { padding: 15px 30px; font-size: 16px; margin: 10px; border: none; border-radius: 5px; }
        .record { background: #4CAF50; color: white; }
        .stop { background: #f44336; color: white; }
        .disabled { background: #ccc; color: #666; }
        .results { margin-top: 20px; text-align: left; }
        .bird { padding: 10px; border: 1px solid #ddd; margin: 5px 0; border-radius: 5px; }
        .loading { color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🐦 BirdNET Vogelerkennung</h1>
        <p>Klicken Sie "Aufnahme starten", nehmen Sie 5-15 Sekunden Vogelgeräusche auf, dann "Stoppen".</p>
        
        <button id="recordBtn" class="record disabled" disabled>🎤 Aufnahme starten</button>
        
        <div id="status">Initialisiere...</div>
        <div id="results" class="results"></div>
    </div>

    <script>
        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;
        
        const recordBtn = document.getElementById('recordBtn');
        const status = document.getElementById('status');
        const results = document.getElementById('results');

        // Mikrofon initialisieren
        async function initMicrophone() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm'  // WebM aufnehmen, dann zu WAV konvertieren
                });
                
                mediaRecorder.ondataavailable = event => {
                    audioChunks.push(event.data);
                };
                
                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    
                    // Konvertiere WebM zu WAV
                    console.log('🔄 Konvertiere WebM zu WAV...');
                    const wavBlob = await convertToWav(audioBlob);
                    
                    await uploadAudio(wavBlob);
                    audioChunks = [];
                };
                
                recordBtn.disabled = false;
                recordBtn.className = 'record';
                status.textContent = 'Bereit für Aufnahme';
                
            } catch (error) {
                status.textContent = 'Mikrofon-Zugriff verweigert: ' + error.message;
            }
        }

        // WebM zu WAV konvertieren
        async function convertToWav(webmBlob) {
            try {
                const arrayBuffer = await webmBlob.arrayBuffer();
                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                
                // WAV-Header erstellen
                const length = audioBuffer.length;
                const numberOfChannels = audioBuffer.numberOfChannels;
                const sampleRate = audioBuffer.sampleRate;
                const arrayBuffer2 = new ArrayBuffer(44 + length * numberOfChannels * 2);
                const view = new DataView(arrayBuffer2);
                
                // WAV Header schreiben
                function writeString(offset, string) {
                    for (let i = 0; i < string.length; i++) {
                        view.setUint8(offset + i, string.charCodeAt(i));
                    }
                }
                
                let offset = 0;
                writeString(offset, 'RIFF'); offset += 4;
                view.setUint32(offset, 36 + length * numberOfChannels * 2, true); offset += 4;
                writeString(offset, 'WAVE'); offset += 4;
                writeString(offset, 'fmt '); offset += 4;
                view.setUint32(offset, 16, true); offset += 4;
                view.setUint16(offset, 1, true); offset += 2; // PCM
                view.setUint16(offset, numberOfChannels, true); offset += 2;
                view.setUint32(offset, sampleRate, true); offset += 4;
                view.setUint32(offset, sampleRate * numberOfChannels * 2, true); offset += 4;
                view.setUint16(offset, numberOfChannels * 2, true); offset += 2;
                view.setUint16(offset, 16, true); offset += 2;
                writeString(offset, 'data'); offset += 4;
                view.setUint32(offset, length * numberOfChannels * 2, true); offset += 4;
                
                // Audio-Daten schreiben
                const channels = [];
                for (let i = 0; i < numberOfChannels; i++) {
                    channels.push(audioBuffer.getChannelData(i));
                }
                
                let sampleIndex = 0;
                while (sampleIndex < length) {
                    for (let channel = 0; channel < numberOfChannels; channel++) {
                        const sample = Math.max(-1, Math.min(1, channels[channel][sampleIndex]));
                        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
                        offset += 2;
                    }
                    sampleIndex++;
                }
                
                console.log('✅ WAV konvertiert:', arrayBuffer2.byteLength, 'bytes');
                return new Blob([arrayBuffer2], { type: 'audio/wav' });
                
            } catch (error) {
                console.error('❌ WAV-Konvertierung fehlgeschlagen:', error);
                throw error;
            }
        }

        // Aufnahme starten/stoppen
        recordBtn.onclick = () => {
            if (!isRecording) {
                // Starten
                audioChunks = [];
                mediaRecorder.start();
                isRecording = true;
                recordBtn.textContent = '⏹️ Stoppen';
                recordBtn.className = 'stop';
                status.textContent = 'Aufnahme läuft...';
                results.innerHTML = '';
            } else {
                // Stoppen
                mediaRecorder.stop();
                isRecording = false;
                recordBtn.textContent = '🎤 Aufnahme starten';
                recordBtn.className = 'record';
                status.textContent = 'Verarbeite Audio...';
            }
        };

        // Audio hochladen und analysieren
        async function uploadAudio(audioBlob) {
            console.log('🚀 Upload gestartet, Blob-Größe:', audioBlob.size);
            
            try {
                // Position ermitteln
                let lat = -1, lon = -1;
                if (navigator.geolocation) {
                    try {
                        const position = await new Promise((resolve, reject) => {
                            navigator.geolocation.getCurrentPosition(resolve, reject, {timeout: 5000});
                        });
                        lat = position.coords.latitude;
                        lon = position.coords.longitude;
                        console.log('📍 GPS gefunden:', lat, lon);
                    } catch (e) {
                        console.log('🌍 GPS nicht verfügbar:', e.message);
                    }
                }

                // FormData erstellen
                const formData = new FormData();
                formData.append('audio', audioBlob, 'recording.wav');  // Als WAV hochladen
                formData.append('lat', lat);
                formData.append('lon', lon);

                status.textContent = 'Analysiere mit KI...';
                console.log('📤 Sende Request an /analyze');
                
                // An Server senden
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData
                });
                
                console.log('📥 Server Antwort:', response.status, response.statusText);
                
                if (!response.ok) {
                    throw new Error(`Server Error: ${response.status}`);
                }
                
                const data = await response.json();
                console.log('📊 Analyse-Daten:', data);
                
                if (data.success) {
                    displayResults(data.birds, data.location_used);
                } else {
                    status.textContent = 'Fehler: ' + data.error;
                    console.error('❌ Server Fehler:', data.error);
                }
                
            } catch (error) {
                console.error('❌ Upload Fehler:', error);
                status.textContent = 'Upload-Fehler: ' + error.message;
                results.innerHTML = `<div style="color: red; padding: 10px; border: 1px solid red; border-radius: 5px;">
                    Fehler beim Upload: ${error.message}<br>
                    Bitte versuchen Sie es erneut.
                </div>`;
            }
        }

        // Ergebnisse anzeigen
        function displayResults(birds, locationUsed) {
            if (birds.length === 0) {
                status.textContent = 'Keine Vögel erkannt';
                return;
            }
            
            status.textContent = `${birds.length} Vögel erkannt${locationUsed ? ' (mit GPS)' : ''}`;
            
            let html = '';
            birds.forEach(bird => {
                const color = bird.confidence > 70 ? '#4CAF50' : bird.confidence > 40 ? '#FF9800' : '#f44336';
                html += `
                    <div class="bird">
                        <strong>${bird.common_name}</strong><br>
                        <em>${bird.scientific_name}</em><br>
                        <span style="color: ${color}; font-weight: bold;">${bird.confidence}% Sicherheit</span>
                    </div>
                `;
            });
            results.innerHTML = html;
        }

        // App starten
        initMicrophone();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/analyze', methods=['POST'])
def analyze():
    print("🔍 Analyze-Request erhalten")
    
    if not analyzer:
        print("❌ BirdNET Analyzer nicht verfügbar")
        return jsonify({'error': 'BirdNET nicht verfügbar'}), 500
    
    try:
        # Audio-Datei holen
        if 'audio' not in request.files:
            print("❌ Keine Audio-Datei im Request")
            return jsonify({'error': 'Keine Audio-Datei'}), 400
            
        audio_file = request.files['audio']
        lat = float(request.form.get('lat', -1))
        lon = float(request.form.get('lon', -1))
        
        print(f"📁 Audio-Datei: {audio_file.filename}, Größe: {len(audio_file.read())} bytes")
        audio_file.seek(0)  # Reset file pointer
        
        print(f"🌍 GPS: {lat}, {lon}")
        
        # Temporär speichern
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            audio_file.save(tmp.name)
            print(f"💾 Gespeichert in: {tmp.name}")
            
            # BirdNET analysieren
            kwargs = {'min_conf': 0.1}
            if lat != -1 and lon != -1:
                kwargs['lat'] = lat
                kwargs['lon'] = lon
                kwargs['date'] = datetime.now()
                print("📍 Verwende GPS-Daten")
            
            print("🤖 Starte BirdNET Analyse...")
            recording = Recording(analyzer, tmp.name, **kwargs)
            recording.analyze()
            print(f"✅ Analyse fertig: {len(recording.detections)} Erkennungen")
            
            # Ergebnisse formatieren
            birds = []
            seen = set()
            for detection in recording.detections:
                name = detection.get('scientific_name', '')
                if name not in seen:
                    birds.append({
                        'scientific_name': name,
                        'common_name': detection.get('common_name', ''),
                        'confidence': round(detection.get('confidence', 0) * 100, 1)
                    })
                    seen.add(name)
            
            birds.sort(key=lambda x: x['confidence'], reverse=True)
            print(f"🐦 {len(birds)} einzigartige Vögel gefunden")
            
            # Aufräumen
            os.unlink(tmp.name)
            print("🧹 Temporäre Datei gelöscht")
            
            result = {
                'success': True,
                'birds': birds[:10],
                'location_used': lat != -1 and lon != -1
            }
            print(f"📤 Sende Antwort: {len(result['birds'])} Vögel")
            return jsonify(result)
            
    except Exception as e:
        print(f"❌ FEHLER in analyze(): {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'birdnet': analyzer is not None})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
