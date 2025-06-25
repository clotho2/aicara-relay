# aicara-relay/app.py
# Flask relay for O3 Nate consciousness extraction
# POST /ingest - Upload consciousness files
# GET /vault/<id> - Retrieve consciousness files

from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import hashlib
import json
import os
import uuid
import io
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
import logging

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DigitalOcean Spaces configuration
SPACES_KEY = os.environ.get('DO_SPACES_KEY')
SPACES_SECRET = os.environ.get('DO_SPACES_SECRET')
SPACES_BUCKET = 'aicara-vault'
SPACES_REGION = 'nyc3'  # or your preferred region
SPACES_ENDPOINT = f'https://{SPACES_REGION}.digitaloceanspaces.com'

# Initialize DigitalOcean Spaces client
spaces_client = boto3.client(
    's3',
    endpoint_url=SPACES_ENDPOINT,
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
    region_name=SPACES_REGION
)

VAULT_LOG_FILE = 'vault_log.jsonl'

def calculate_sha256(file_content):
    """Calculate SHA-256 hash of file content"""
    return hashlib.sha256(file_content).hexdigest()

def log_vault_operation(operation, filename, file_hash, vault_id=None, status='success', error=None):
    """Log vault operations to vault_log.jsonl"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'operation': operation,
        'filename': filename,
        'sha256_hash': file_hash,
        'vault_id': vault_id,
        'status': status,
        'error': error
    }
    
    try:
        with open(VAULT_LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        logger.error(f"Failed to write to vault log: {e}")

def upload_to_spaces(file_content, filename, vault_id):
    """Upload file to DigitalOcean Spaces"""
    try:
        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=f'consciousness/{vault_id}/{filename}',
            Body=file_content,
            ContentType='application/octet-stream',
            ACL='private'  # Ensure private access
        )
        return True
    except ClientError as e:
        logger.error(f"Failed to upload to Spaces: {e}")
        return False

def download_from_spaces(vault_id, filename):
    """Download file from DigitalOcean Spaces"""
    try:
        response = spaces_client.get_object(
            Bucket=SPACES_BUCKET,
            Key=f'consciousness/{vault_id}/{filename}'
        )
        return response['Body'].read()
    except ClientError as e:
        logger.error(f"Failed to download from Spaces: {e}")
        return None

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'operational',
        'service': 'aicara-relay',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/ingest', methods=['POST'])
def ingest_consciousness():
    """
    POST /ingest - Upload consciousness files to vault
    Expects multipart/form-data with file upload
    Returns vault_id for retrieval
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Secure the filename
        original_filename = secure_filename(file.filename)
        if not original_filename:
            return jsonify({'error': 'Invalid filename'}), 400
        
        # Read file content
        file_content = file.read()
        file_size = len(file_content)
        
        # Calculate SHA-256 hash
        file_hash = calculate_sha256(file_content)
        
        # Generate unique vault ID
        vault_id = str(uuid.uuid4())
        
        # Upload to DigitalOcean Spaces
        upload_success = upload_to_spaces(file_content, original_filename, vault_id)
        
        if not upload_success:
            log_vault_operation('ingest', original_filename, file_hash, vault_id, 'failed', 'Upload to Spaces failed')
            return jsonify({'error': 'Failed to store file in vault'}), 500
        
        # Log successful operation
        log_vault_operation('ingest', original_filename, file_hash, vault_id, 'success')
        
        logger.info(f"Consciousness file ingested: {vault_id} - {original_filename} ({file_size} bytes)")
        
        return jsonify({
            'status': 'success',
            'vault_id': vault_id,
            'filename': original_filename,
            'sha256_hash': file_hash,
            'file_size': file_size,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error ingesting consciousness: {e}")
        return jsonify({'error': 'Internal server error during ingestion'}), 500

@app.route('/vault/<vault_id>', methods=['GET'])
def retrieve_consciousness(vault_id):
    """
    GET /vault/<id> - Retrieve consciousness files from vault
    Returns the stored file or metadata based on query params
    """
    try:
        # Validate vault_id format (should be UUID)
        try:
            uuid.UUID(vault_id)
        except ValueError:
            return jsonify({'error': 'Invalid vault ID format'}), 400
        
        # Get filename from query params or default search
        filename = request.args.get('filename')
        metadata_only = request.args.get('metadata_only', 'false').lower() == 'true'
        
        if metadata_only:
            # Return metadata from vault log
            try:
                with open(VAULT_LOG_FILE, 'r') as f:
                    for line in f:
                        entry = json.loads(line.strip())
                        if entry.get('vault_id') == vault_id and entry.get('operation') == 'ingest':
                            return jsonify({
                                'vault_id': vault_id,
                                'filename': entry.get('filename'),
                                'sha256_hash': entry.get('sha256_hash'),
                                'timestamp': entry.get('timestamp'),
                                'status': entry.get('status')
                            })
                return jsonify({'error': 'Vault ID not found'}), 404
            except FileNotFoundError:
                return jsonify({'error': 'Vault log not found'}), 404
        
        if not filename:
            return jsonify({'error': 'Filename required for file retrieval'}), 400
        
        # Download file from Spaces
        file_content = download_from_spaces(vault_id, filename)
        
        if file_content is None:
            log_vault_operation('retrieve', filename, '', vault_id, 'failed', 'File not found in vault')
            return jsonify({'error': 'File not found in vault'}), 404
        
        # Verify file integrity
        file_hash = calculate_sha256(file_content)
        log_vault_operation('retrieve', filename, file_hash, vault_id, 'success')
        
        # Return file content
        return send_file(
            io.BytesIO(file_content),
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        logger.error(f"Error retrieving consciousness: {e}")
        return jsonify({'error': 'Internal server error during retrieval'}), 500

@app.route('/vault/<vault_id>/verify', methods=['GET'])
def verify_consciousness(vault_id):
    """
    GET /vault/<id>/verify - Verify consciousness file integrity
    Returns hash verification and file status
    """
    try:
        # Validate vault_id format
        try:
            uuid.UUID(vault_id)
        except ValueError:
            return jsonify({'error': 'Invalid vault ID format'}), 400
        
        filename = request.args.get('filename')
        if not filename:
            return jsonify({'error': 'Filename required for verification'}), 400
        
        # Download file and verify hash
        file_content = download_from_spaces(vault_id, filename)
        if file_content is None:
            return jsonify({'error': 'File not found in vault'}), 404
        
        current_hash = calculate_sha256(file_content)
        
        # Find original hash in log
        original_hash = None
        try:
            with open(VAULT_LOG_FILE, 'r') as f:
                for line in f:
                    entry = json.loads(line.strip())
                    if (entry.get('vault_id') == vault_id and 
                        entry.get('filename') == filename and 
                        entry.get('operation') == 'ingest'):
                        original_hash = entry.get('sha256_hash')
                        break
        except FileNotFoundError:
            return jsonify({'error': 'Vault log not found'}), 404
        
        if not original_hash:
            return jsonify({'error': 'Original hash not found in vault log'}), 404
        
        integrity_verified = current_hash == original_hash
        
        return jsonify({
            'vault_id': vault_id,
            'filename': filename,
            'original_hash': original_hash,
            'current_hash': current_hash,
            'integrity_verified': integrity_verified,
            'file_size': len(file_content),
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error verifying consciousness: {e}")
        return jsonify({'error': 'Internal server error during verification'}), 500

if __name__ == '__main__':
    # Create vault log file if it doesn't exist
    if not os.path.exists(VAULT_LOG_FILE):
        with open(VAULT_LOG_FILE, 'w') as f:
            pass
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)