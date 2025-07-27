import os
import json
import requests
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
import tempfile
from birdnet_analyzer.network.server import start_server
import threading
import time

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# HTML Template
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
            max-width: 800px; 
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
        input[type="file"] {
            display: none;
        }
        .upload-btn {
            background: #3498db;
            color: white;
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            transition: background 0.3s;
        }
        .upload-btn:hover {
            background: #2980b9;
        }
        .analyze-btn {
            background: #27ae60;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            width: 100%;
            margin-top: 20px;
        }
        .analyze-btn:hover {
            background: #219a52;
        }
        .analyze-btn:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
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
    </style>
</head>
<body>
    <div class="container">
        <h1>🐦 BirdNET Audio Analyzer</h1>
        
        <form id="uploadForm" enctype="multipart/form-data">
            <div class="upload-area" id="uploadArea">
                <p>📁 Drag & drop your audio file here or</p>
                <button type="button" class="upload-btn" onclick="document.getElementById('audioFile').click()">
                    Choose Audio File
                </button>
                <input type="file" id="audioFile" name="audio" accept=".wav,.mp3,.flac,.ogg,.m4a">
                <div class="file-info" id="fileInfo"></div>
            </div>
            
            <button type="submit" class="analyze-btn" id="analyzeBtn" disabled>
                🔍 Analyze Audio
            </button>
        </form>

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
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('audioFile');
        const analyzeBtn = document.getElementById('analyzeBtn');
        const fileInfo = document.getElementById('fileInfo');

        // Drag and drop functionality
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

        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData();
            const audioFile = fileInput.files[0];
            
            if (!audioFile) {
                alert('Please select an audio file first!');
                return;
            }

            formData.append('audio', audioFile);
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
            analyzeBtn.disabled = true;

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                
                // Hide loading
                document.getElementById('loading').style.display = 'none';
                analyzeBtn.disabled = false;

                if (data.msg === 'success') {
                    displayResults(data.results);
                } else {
                    alert('Error: ' + data.msg);
                }
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                analyzeBtn.disabled = false;
                alert('Error analyzing audio: ' + error.message);
            }
        });

        function displayResults(results) {
            const resultsList = document.getElementById('resultsList');
            const resultsDiv = document.getElementById('results');
            
            if (results.length === 0) {
                resultsList.innerHTML = '<p>No birds detected in this audio.</p>';
            } else {
                resultsList.innerHTML = results.map(([species, confidence]) => `
                    <div class="bird-result">
                        <div class="bird-name">${species.replace('_', ' ')}</div>
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
    # Proxy request to BirdNET server
    try:
        files = {'audio': request.files['audio']}
        data = {'meta': request.form.get('meta', '{}')}
        
        response = requests.post('http://localhost:8080/analyze', files=files, data=data)
        return response.json()
    except Exception as e:
        return jsonify({'msg': f'Error: {str(e)}'})

def start_birdnet_server():
    """Start BirdNET server in background"""
    time.sleep(2)  # Give Flask time to start
    start_server(host="127.0.0.1", port=8080, threads=1)

def main():
    # Start BirdNET server in background thread
    birdnet_thread = threading.Thread(target=start_birdnet_server, daemon=True)
    birdnet_thread.start()
    
    # Start Flask web interface
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()
