import os
from birdnet_analyzer.network.server import start_server

if __name__ == '__main__':
    # Port von Render Environment Variable
    port = int(os.environ.get('PORT', 8080))
    
    # Server starten
    start_server(
        host="0.0.0.0", 
        port=port,
        spath="uploads/",
        threads=1,
        locale="en"
    )
