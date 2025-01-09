import boto3
import os
import subprocess
import json
import time
import hashlib
from typing import Optional, Tuple
from datetime import datetime
from botocore.exceptions import ClientError

def load_aws_credentials(creds_file: str = 'aws_credentials.json') -> dict:
    """
    Load AWS credentials from JSON file
    Expected format:
    {
        "aws_access_key_id": "YOUR_ACCESS_KEY",
        "aws_secret_access_key": "YOUR_SECRET_KEY",
        "aws_region": "us-east-1"
    }
    """
    try:
        with open(creds_file, 'r') as f:
            creds = json.load(f)
            required_keys = ['aws_access_key_id', 'aws_secret_access_key', 'aws_region']
            if not all(key in creds for key in required_keys):
                raise KeyError("Missing required credentials in JSON file")
            return creds
    except FileNotFoundError:
        raise FileNotFoundError(f"Credentials file {creds_file} not found")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in credentials file {creds_file}")

def initialize_aws_clients(creds: dict):
    """
    Initialize AWS clients with credentials
    """
    session = boto3.Session(
        aws_access_key_id=creds['aws_access_key_id'],
        aws_secret_access_key=creds['aws_secret_access_key'],
        region_name=creds['aws_region']
    )
    
    return {
        'ecr': session.client('ecr'),
        'lambda': session.client('lambda')
    }

def verify_aws_credentials(clients: dict) -> bool:
    """
    Verify AWS credentials are valid by making a test API call
    """
    try:
        # Test ECR access
        clients['ecr'].describe_repositories(maxResults=1)
        # Test Lambda access
        clients['lambda'].get_account_settings()
        return True
    except ClientError as e:
        if e.response['Error']['Code'] in ['InvalidSignatureException', 'UnrecognizedClientException']:
            print("Invalid AWS credentials")
        else:
            print(f"Error verifying AWS access: {e}")
        return False

def get_dockerfile_hash(dockerfile_path: str) -> str:
    """
    Calculate hash of Dockerfile and all referenced files
    """
    def hash_file(filepath: str) -> str:
        with open(filepath, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    # Get Dockerfile hash
    dockerfile_hash = hash_file(dockerfile_path)
    
    # Get hash of all files referenced in COPY and ADD commands
    with open(dockerfile_path, 'r') as f:
        dockerfile_content = f.read().splitlines()
    
    referenced_files = []
    for line in dockerfile_content:
        if line.startswith(('COPY ', 'ADD ')):
            files = line.split()[1:-1]  # Exclude command and destination
            referenced_files.extend(files)
    
    # Combine all hashes
    all_hashes = dockerfile_hash + ''.join(
        hash_file(f) for f in referenced_files if os.path.isfile(f)
    )
    return hashlib.sha256(all_hashes.encode()).hexdigest()

def get_cache_info() -> dict:
    """
    Load deployment cache information
    """
    cache_file = '.lambda_deploy_cache'
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

def save_cache_info(cache_info: dict):
    """
    Save deployment cache information
    """
    with open('.lambda_deploy_cache', 'w') as f:
        json.dump(cache_info, f, indent=2)

def check_lambda_config(lambda_client, function_name: str, expected_config: dict) -> bool:
    """
    Check if Lambda function configuration matches expected values
    """
    try:
        current_config = lambda_client.get_function_configuration(
            FunctionName=function_name
        )
        for key, value in expected_config.items():
            if current_config.get(key) != value:
                return False
        return True
    except Exception:
        return False

def build_docker_image(dockerfile_path: str, image_tag: str) -> bool:
    """
    Build Docker image from Dockerfile
    """
    try:
        subprocess.run([
            'docker', 'build',
            '-f', dockerfile_path,
            '-t', image_tag,
            '.'
        ], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error building Docker image: {e}")
        return False

def get_ecr_repository(ecr_client, repository_name: str) -> Optional[str]:
    """
    Get ECR repository URI, create if it doesn't exist
    """
    try:
        response = ecr_client.describe_repositories(repositoryNames=[repository_name])
        return response['repositories'][0]['repositoryUri']
    except ecr_client.exceptions.RepositoryNotFoundException:
        response = ecr_client.create_repository(repositoryName=repository_name)
        return response['repository']['repositoryUri']
    except Exception as e:
        print(f"Error with ECR repository: {e}")
        return None

def get_latest_image_digest(ecr_client, repository_uri: str) -> Optional[str]:
    """
    Get the digest of the latest image in ECR
    """
    try:
        repository_name = repository_uri.split('/')[-1]
        response = ecr_client.describe_images(
            repositoryName=repository_name,
            imageIds=[{'imageTag': 'latest'}]
        )
        return response['imageDetails'][0]['imageDigest']
    except Exception:
        return None

def push_to_ecr(ecr_client, repository_uri: str, image_tag: str) -> Optional[str]:
    """
    Push Docker image to ECR
    """
    try:
        # Get ECR authentication token
        auth = ecr_client.get_authorization_token()
        token = auth['authorizationData'][0]['authorizationToken']
        endpoint = auth['authorizationData'][0]['proxyEndpoint']
        
        # Login to ECR
        subprocess.run([
            'docker', 'login',
            '--username', 'AWS',
            '--password-stdin',
            endpoint
        ], input=token.encode(), check=True)
        
        # Tag the image for ECR
        ecr_image_tag = f"{repository_uri}:latest"
        subprocess.run(['docker', 'tag', image_tag, ecr_image_tag], check=True)
        
        # Push to ECR
        subprocess.run(['docker', 'push', ecr_image_tag], check=True)
        return ecr_image_tag
    except Exception as e:
        print(f"Error pushing to ECR: {e}")
        return None

def update_lambda_function(lambda_client, function_name: str, image_uri: str) -> bool:
    """
    Update Lambda function with new container image
    """
    try:
        lambda_client.update_function_code(
            FunctionName=function_name,
            ImageUri=image_uri
        )
        
        # Wait for update to complete
        while True:
            response = lambda_client.get_function(FunctionName=function_name)
            if response['Configuration']['State'] == 'Active':
                break
            time.sleep(5)
        
        return True
    except Exception as e:
        print(f"Error updating Lambda function: {e}")
        return False

def main():
    # Load AWS credentials
    try:
        creds = load_aws_credentials()
        print("AWS credentials loaded successfully")
    except Exception as e:
        print(f"Error loading AWS credentials: {e}")
        return

    # Initialize AWS clients
    try:
        aws_clients = initialize_aws_clients(creds)
        if not verify_aws_credentials(aws_clients):
            return
    except Exception as e:
        print(f"Error initializing AWS clients: {e}")
        return

    # Configuration
    ECR_REPOSITORY_NAME = 'test'
    LAMBDA_FUNCTION_NAME = 'test-function'
    DOCKERFILE_PATH = 'lambda.Dockerfile'
    LOCAL_IMAGE_TAG = 'test:latest'
    
    # Load cache
    cache_info = get_cache_info()
    current_hash = get_dockerfile_hash(DOCKERFILE_PATH)
    
    # Check if rebuild is necessary
    if cache_info.get('dockerfile_hash') == current_hash:
        print("No changes detected in Dockerfile or referenced files. Skipping build...")
        should_build = False
    else:
        print("Changes detected in Dockerfile or referenced files. Building...")
        should_build = True
    
    # Build Docker image if necessary
    if should_build:
        if not build_docker_image(DOCKERFILE_PATH, LOCAL_IMAGE_TAG):
            return
        
        # Update cache with new hash
        cache_info['dockerfile_hash'] = current_hash
        cache_info['last_build'] = datetime.now().isoformat()
    
    # Get or create ECR repository
    print("Getting ECR repository...")
    repository_uri = get_ecr_repository(aws_clients['ecr'], ECR_REPOSITORY_NAME)
    if not repository_uri:
        return
    
    # Check if image needs to be pushed
    current_digest = get_latest_image_digest(aws_clients['ecr'], repository_uri)
    if not should_build and current_digest == cache_info.get('last_image_digest'):
        print("Image already up to date in ECR. Skipping push...")
    else:
        print("Pushing image to ECR...")
        ecr_image_uri = push_to_ecr(aws_clients['ecr'], repository_uri, LOCAL_IMAGE_TAG)
        if not ecr_image_uri:
            return
        
        # Update cache with new image digest
        cache_info['last_image_digest'] = get_latest_image_digest(aws_clients['ecr'], repository_uri)
    
    # Check if Lambda update is necessary
    lambda_config = {
        'ImageUri': f"{repository_uri}:latest"
    }
    
    if check_lambda_config(aws_clients['lambda'], LAMBDA_FUNCTION_NAME, lambda_config):
        print("Lambda function already up to date. Skipping update...")
    else:
        print("Updating Lambda function...")
        if update_lambda_function(aws_clients['lambda'], LAMBDA_FUNCTION_NAME, f"{repository_uri}:latest"):
            print("Deployment completed successfully!")
            cache_info['last_deployment'] = datetime.now().isoformat()
        else:
            print("Deployment failed!")
            return
    
    # Save updated cache
    save_cache_info(cache_info)

if __name__ == '__main__':
    main()