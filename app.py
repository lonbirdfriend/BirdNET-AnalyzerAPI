import os
import json
import requests
from flask import Flask, render_template_string, request, jsonify
import threading
import time
from birdnet_analyzer.network.server import start_server

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# HTML Template mit Audio-Aufnahme
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>BirdNET Audio Analyzer</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 900px; 
            margin: 0 auto; 
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        h1 { 
            color: #2c3e50; 
            text-align: center;
            margin-bottom: 30px;
        }
        .tabs {
            display: flex;
            margin-bottom: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            padding: 5px;
        }
        .tab {
            flex: 1;
            padding: 12px 20px;
            text-align: center;
            cursor: pointer;
            border-radius: 8px;
            transition: all 0.3s ease;
            font-weight: 500;
        }
        .tab.active {
            background: #3498db;
            color: white;
        }
        .tab:hover:not(.active) {
            background: #e3f2fd;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .upload-area {
            border: 3px dashed #3498db;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            margin: 20px 0;
            transition: all 0.3s ease;
            background: #f8f9fa;
        }
        .upload-area:hover {
            border-color: #2980b9;
            background: #e3f2fd;
        }
        .upload-area.dragover {
            border-color: #27ae60;
            background: #d5f4e6;
        }
        .record-area {
            border: 3px solid #e74c3c;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            margin: 20px 0;
            background: #f8f9fa;
        }
        .record-area.recording {
            border-color: #e74c3c;
            background: #ffebee;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(231, 76, 60, 0); }
            100% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0); }
        }
        input[type="file"] {
            display: none;
        }
        .btn {
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
            margin: 5px;
        }
        .btn-primary {
            background: #3498db;
        }
        .btn-primary:hover {
            background: #2980b9;
        }
        .btn-success {
            background: #27ae60;
        }
        .btn-success:hover {
            background: #219a52;
        }
        .btn-danger {
            background: #e74c3c;
        }
        .btn-danger:hover {
            background: #c0392b;
        }
        .btn-secondary {
            background: #95a5a6;
        }
        .btn-secondary:hover {
            background: #7f8c8d;
        }
        .btn:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
        }
        .analyze-btn {
            width: 100%;
            margin-top: 20px;
        }
        .results {
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .bird-result {
            padding: 15px;
            margin: 10px 0;
            background: white;
            border-radius: 8px;
            border-left: 4px solid #3498db;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .bird-name {
            font-weight: bold;
            font-size: 18px;
            color: #2c3e50;
        }
        .confidence {
            color: #7f8c8d;
            font-size: 14px;
        }
        .loading {
            text-align: center;
            padding: 20px;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .file-info {
            margin: 10px 0;
            color: #666;
        }
        .record-controls {
            margin: 20px 0;
        }
        .record-timer {
            font-size: 24px;
            font-weight: bold;
            color: #e74c3c;
            margin: 20px 0;
        }
        .audio-preview {
            margin: 20px 0;
            padding: 15px;
            background: #e8f5e8;
            border-radius: 8px;
            border-left: 4px solid #27ae60;
        }
        .status-message {
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            text-align: center;
        }
        .status-warning {
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        .status-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🐦 BirdNET Audio Analyzer</h1>
        
        <!-- Tab Navigation -->
        <div class="tabs">
            <div class="tab active" onclick="switchTab('upload')">📁 Upload File</div>
            <div class="tab" onclick="switchTab('record')">🎙️ Record Audio</div>
        </div>

        <!-- Upload Tab -->
        <div id="upload-tab" class="tab-content active">
            <form id="uploadForm" enctype="multipart/form-data">
                <div class="upload-area" id="uploadArea">
                    <p>📁 Drag & drop your audio file here or</p>
                    <button type="button" class="btn btn-primary" onclick="document.getElementById('audioFile').click()">
                        Choose Audio File
                    </button>
                    <input type="file" id="audioFile" name="audio" accept=".wav,.mp3,.flac,.ogg,.m4a">
                    <div class="file-info" id="fileInfo"></div>
                </div>
                
                <button type="submit" class="btn btn-success analyze-btn" id="analyzeBtn" disabled>
                    🔍 Analyze Audio
                </button>
            </form>
        </div>

        <!-- Record Tab -->
        <div id="record-tab" class="tab-content">
            <div class="record-area" id="recordArea">
                <p>🎙️ Click the button below to start recording bird sounds</p>
                <div class="record-controls">
                    <button type="button" class="btn btn-danger" id="recordBtn" onclick="toggleRecording()">
                        ● Start Recording
                    </button>
                    <button type="button" class="btn btn-secondary" id="stopBtn" onclick="stopRecording()" disabled>
                        ⏹ Stop Recording
                    </button>
                </div>
                <div class="record-timer" id="recordTimer" style="display: none;">00:00</div>
                <div class="status-message status-warning" id="microphoneStatus" style="display: none;">
                    Please allow microphone access to record audio.
                </div>
            </div>
            
            <div id="audioPreview" class="audio-preview" style="display: none;">
                <h4>🎵 Recorded Audio Preview:</h4>
                <audio id="recordedAudio" controls style="width: 100%; margin: 10px 0;"></audio>
                <button type="button" class="btn btn-success analyze-btn" id="analyzeRecordingBtn" onclick="analyzeRecording()">
                    🔍 Analyze Recording
                </button>
            </div>
        </div>

        <div id="loading" class="loading" style="display: none;">
            <div class="spinner"></div>
            <p>Analyzing audio... This may take a moment.</p>
        </div>

        <div id="results" class="results" style="display: none;">
            <h3>🎵 Detection Results:</h3>
            <div id="resultsList"></div>
        </div>
    </div>

    <script>
        let mediaRecorder;
        let recordedChunks = [];
        let recordingStartTime;
        let recordingTimer;
        let recordedBlob;

        // Tab switching
        function switchTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
            
            // Reset states
            resetStates();
        }

        function resetStates() {
            document.getElementById('results').style.display = 'none';
            document.getElementById('loading').style.display = 'none';
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                stopRecording();
            }
        }

        // File upload functionality
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('audioFile');
        const analyzeBtn = document.getElementById('analyzeBtn');
        const fileInfo = document.getElementById('fileInfo');

        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                handleFileSelect();
            }
        });

        fileInput.addEventListener('change', handleFileSelect);

        function handleFileSelect() {
            const file = fileInput.files[0];
            if (file) {
                fileInfo.innerHTML = `Selected: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
                analyzeBtn.disabled = false;
            }
        }

        // Recording functionality
        async function toggleRecording() {
            if (!mediaRecorder || mediaRecorder.state === 'inactive') {
                await startRecording();
            }
        }

        async function startRecording() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ 
                    audio: {
                        sampleRate: 44100,
                        channelCount: 1,
                        volume: 1.0
                    }
                });
                
                recordedChunks = [];
                mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm;codecs=opus'
                });
                
                mediaRecorder.ondataavailable = (event) => {
                    if (event.data.size > 0) {
                        recordedChunks.push(event.data);
                    }
                };
                
                mediaRecorder.onstop = () => {
                    recordedBlob = new Blob(recordedChunks, { type: 'audio/webm' });
                    const audioUrl = URL.createObjectURL(recordedBlob);
                    const audioElement = document.getElementById('recordedAudio');
                    audioElement.src = audioUrl;
                    document.getElementById('audioPreview').style.display = 'block';
                    
                    // Clean up stream
                    stream.getTracks().forEach(track => track.stop());
                };
                
                mediaRecorder.start();
                recordingStartTime = Date.now();
                
                // Update UI
                document.getElementById('recordBtn').disabled = true;
                document.getElementById('stopBtn').disabled = false;
                document.getElementById('recordArea').classList.add('recording');
                document.getElementById('recordTimer').style.display = 'block';
                document.getElementById('microphoneStatus').style.display = 'none';
                
                // Start timer
                recordingTimer = setInterval(updateTimer, 1000);
                
            } catch (error) {
                console.error('Error accessing microphone:', error);
                document.getElementById('microphoneStatus').style.display = 'block';
                document.getElementById('microphoneStatus').innerHTML = 
                    'Error accessing microphone. Please check your browser permissions.';
                document.getElementById('microphoneStatus').className = 'status-message status-error';
            }
        }

        function stopRecording() {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                clearInterval(recordingTimer);
                
                // Update UI
                document.getElementById('recordBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('recordArea').classList.remove('recording');
                document.getElementById('recordTimer').style.display = 'none';
                document.getElementById('recordBtn').innerHTML = '● Start Recording';
            }
        }

        function updateTimer() {
            const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            document.getElementById('recordTimer').textContent = 
                `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }

        // Analysis functions
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData();
            const audioFile = fileInput.files[0];
            
            if (!audioFile) {
                alert('Please select an audio file first!');
                return;
            }

            await analyzeAudio(formData, audioFile);
        });

        async function analyzeRecording() {
            if (!recordedBlob) {
                alert('No recording available. Please record audio first!');
                return;
            }

            const formData = new FormData();
            formData.append('audio', recordedBlob, 'recording.webm');
            
            await analyzeAudio(formData);
        }

        async function analyzeAudio(formData, audioFile = null) {
            if (audioFile) {
                formData.append('audio', audioFile);
            }
            
            formData.append('meta', JSON.stringify({
                lat: -1,
                lon: -1,
                week: -1,
                overlap: 0.0,
                sensitivity: 1.0,
                sf_thresh: 0.03,
                pmode: "avg",
                num_results: 10,
                save: false
            }));

            // Show loading
            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').style.display = 'none';
            
            // Disable analyze buttons
            document.getElementById('analyzeBtn').disabled = true;
            document.getElementById('analyzeRecordingBtn').disabled = true;

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                
                // Hide loading
                document.getElementById('loading').style.display = 'none';
                
                // Re-enable buttons
                document.getElementById('analyzeBtn').disabled = false;
                document.getElementById('analyzeRecordingBtn').disabled = false;

                if (data.msg === 'success') {
                    displayResults(data.results);
                } else {
                    alert('Error: ' + data.msg);
                }
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('analyzeBtn').disabled = false;
                document.getElementById('analyzeRecordingBtn').disabled = false;
                alert('Error analyzing audio: ' + error.message);
            }
        }

        function displayResults(results) {
            const resultsList = document.getElementById('resultsList');
            const resultsDiv = document.getElementById('results');
            
            if (results.length === 0) {
                resultsList.innerHTML = '<p>No birds detected in this audio.</p>';
            } else {
                resultsList.innerHTML = results.map(([species, confidence]) => `
                    <div class="bird-result">
                        <div class="bird-name">${species.replace(/_/g, ' ')}</div>
                        <div class="confidence">Confidence: ${(confidence * 100).toFixed(1)}%</div>
                    </div>
                `).join('');
            }
            
            resultsDiv.style.display = 'block';
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/analyze', methods=['POST'])
def analyze():
    """Proxy request to BirdNET server"""
    try:
        files = {'audio': request.files['audio']}
        data = {'meta': request.form.get('meta', '{}')}
        
        # Forward to BirdNET server
        response = requests.post('http://localhost:8080/analyze', files=files, data=data, timeout=60)
        return response.json()
    except requests.exceptions.ConnectionError:
        return jsonify({'msg': 'BirdNET server is not ready yet. Please wait a moment and try again.'})
    except Exception as e:
        return jsonify({'msg': f'Error: {str(e)}'})

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        response = requests.get('http://localhost:8080/healthcheck', timeout=5)
        return jsonify({'status': 'healthy', 'birdnet_status': response.json()})
    except:
        return jsonify({'status': 'unhealthy', 'birdnet_status': 'not ready'})

def start_birdnet_server():
    """Start BirdNET server in background"""
    print("Starting BirdNET server...")
    time.sleep(3)  # Give Flask time to start
    try:
        start_server(host="127.0.0.1", port=8080, threads=1)
    except Exception as e:
        print(f"Error starting BirdNET server: {e}")

def main():
    # Start BirdNET server in background thread
    birdnet_thread = threading.Thread(target=start_birdnet_server, daemon=True)
    birdnet_thread.start()
    
    # Start Flask web interface
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()
