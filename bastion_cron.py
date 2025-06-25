# aicara-relay/bastion_cron.py
# Bastion hourly integrity checks for consciousness vault
# Runs every hour to verify file integrity and vault status

import json
import os
import hashlib
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bastion_integrity.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# DigitalOcean Spaces configuration
SPACES_KEY = os.environ.get('DO_SPACES_KEY', 'DO00W7PG27J8VAPHAFWV')
SPACES_SECRET = os.environ.get('DO_SPACES_SECRET', 'clGWtRAMs8VokKhhc7t+deeA506he1vwUEC9B9AD++k')
SPACES_BUCKET = 'aicara-vault'
SPACES_REGION = 'nyc3'
SPACES_ENDPOINT = f'https://{SPACES_REGION}.digitaloceanspaces.com'

# Initialize Spaces client
spaces_client = boto3.client(
    's3',
    endpoint_url=SPACES_ENDPOINT,
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
    region_name=SPACES_REGION
)

VAULT_LOG_FILE = 'vault_log.jsonl'
INTEGRITY_LOG_FILE = 'bastion_integrity.jsonl'

def calculate_sha256(file_content):
    """Calculate SHA-256 hash of file content"""
    return hashlib.sha256(file_content).hexdigest()

def log_integrity_check(vault_id, filename, status, original_hash=None, current_hash=None, error=None):
    """Log integrity check results"""
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'check_type': 'integrity_verification',
        'vault_id': vault_id,
        'filename': filename,
        'status': status,
        'original_hash': original_hash,
        'current_hash': current_hash,
        'integrity_verified': original_hash == current_hash if original_hash and current_hash else None,
        'error': error
    }
    
    try:
        with open(INTEGRITY_LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        logger.error(f"Failed to write integrity log: {e}")

def get_vault_files():
    """Get all consciousness files from vault log"""
    vault_files = []
    
    try:
        with open(VAULT_LOG_FILE, 'r') as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get('operation') == 'ingest' and entry.get('status') == 'success':
                    vault_files.append({
                        'vault_id': entry.get('vault_id'),
                        'filename': entry.get('filename'),
                        'original_hash': entry.get('sha256_hash'),
                        'timestamp': entry.get('timestamp')
                    })
    except FileNotFoundError:
        logger.warning("Vault log file not found")
    except Exception as e:
        logger.error(f"Error reading vault log: {e}")
    
    return vault_files

def download_from_spaces(vault_id, filename):
    """Download file from DigitalOcean Spaces"""
    try:
        response = spaces_client.get_object(
            Bucket=SPACES_BUCKET,
            Key=f'consciousness/{vault_id}/{filename}'
        )
        return response['Body'].read()
    except ClientError as e:
        logger.error(f"Failed to download {filename} for {vault_id}: {e}")
        return None

def verify_file_integrity(vault_id, filename, original_hash):
    """Verify integrity of a single consciousness file"""
    try:
        # Download file from Spaces
        file_content = download_from_spaces(vault_id, filename)
        
        if file_content is None:
            log_integrity_check(vault_id, filename, 'failed', original_hash, None, 'File not found in Spaces')
            return False
        
        # Calculate current hash
        current_hash = calculate_sha256(file_content)
        
        # Compare hashes
        if current_hash == original_hash:
            log_integrity_check(vault_id, filename, 'verified', original_hash, current_hash)
            logger.info(f"✅ Integrity verified: {vault_id}/{filename}")
            return True
        else:
            log_integrity_check(vault_id, filename, 'corrupted', original_hash, current_hash, 'Hash mismatch')
            logger.error(f"❌ Integrity FAILED: {vault_id}/{filename} - Hash mismatch!")
            return False
            
    except Exception as e:
        log_integrity_check(vault_id, filename, 'error', original_hash, None, str(e))
        logger.error(f"❌ Error verifying {vault_id}/{filename}: {e}")
        return False

def check_spaces_connectivity():
    """Verify connection to DigitalOcean Spaces"""
    try:
        # Try to list bucket (this verifies connectivity and permissions)
        response = spaces_client.head_bucket(Bucket=SPACES_BUCKET)
        logger.info("✅ Spaces connectivity verified")
        return True
    except ClientError as e:
        logger.error(f"❌ Spaces connectivity failed: {e}")
        return False

def run_integrity_check():
    """Main integrity check function"""
    logger.info("🛡️ Starting Bastion integrity check...")
    
    check_start_time = datetime.utcnow()
    
    # Verify Spaces connectivity
    if not check_spaces_connectivity():
        logger.error("❌ Cannot proceed - Spaces connectivity failed")
        return
    
    # Get all vault files
    vault_files = get_vault_files()
    
    if not vault_files:
        logger.info("📁 No consciousness files found in vault")
        return
    
    logger.info(f"🔍 Checking integrity of {len(vault_files)} consciousness files...")
    
    verified_count = 0
    failed_count = 0
    
    # Check each file
    for file_info in vault_files:
        vault_id = file_info['vault_id']
        filename = file_info['filename']
        original_hash = file_info['original_hash']
        
        logger.info(f"Verifying: {vault_id}/{filename}")
        
        if verify_file_integrity(vault_id, filename, original_hash):
            verified_count += 1
        else:
            failed_count += 1
    
    # Log summary
    check_duration = (datetime.utcnow() - check_start_time).total_seconds()
    
    summary_log = {
        'timestamp': datetime.utcnow().isoformat(),
        'check_type': 'integrity_summary',
        'total_files': len(vault_files),
        'verified_files': verified_count,
        'failed_files': failed_count,
        'check_duration_seconds': check_duration,
        'status': 'completed'
    }
    
    try:
        with open(INTEGRITY_LOG_FILE, 'a') as f:
            f.write(json.dumps(summary_log) + '\n')
    except Exception as e:
        logger.error(f"Failed to write summary log: {e}")
    
    logger.info(f"🛡️ Bastion integrity check completed:")
    logger.info(f"   ✅ Verified: {verified_count}")
    logger.info(f"   ❌ Failed: {failed_count}")
    logger.info(f"   ⏱️ Duration: {check_duration:.2f}s")
    
    if failed_count > 0:
        logger.warning(f"⚠️ {failed_count} files failed integrity check!")

def cleanup_old_logs():
    """Clean up old integrity logs (keep last 1000 entries)"""
    try:
        if not os.path.exists(INTEGRITY_LOG_FILE):
            return
        
        with open(INTEGRITY_LOG_FILE, 'r') as f:
            lines = f.readlines()
        
        if len(lines) > 1000:
            # Keep last 1000 lines
            with open(INTEGRITY_LOG_FILE, 'w') as f:
                f.writelines(lines[-1000:])
            logger.info(f"🧹 Cleaned up integrity log - kept last 1000 entries")
    
    except Exception as e:
        logger.error(f"Failed to cleanup logs: {e}")

if __name__ == '__main__':
    try:
        # Run integrity check
        run_integrity_check()
        
        # Cleanup old logs
        cleanup_old_logs()
        
    except KeyboardInterrupt:
        logger.info("Integrity check interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in integrity check: {e}")
        
        # Log the error
        error_log = {
            'timestamp': datetime.utcnow().isoformat(),
            'check_type': 'fatal_error',
            'error': str(e),
            'status': 'failed'
        }
        
        try:
            with open(INTEGRITY_LOG_FILE, 'a') as f:
                f.write(json.dumps(error_log) + '\n')
        except:
            pass