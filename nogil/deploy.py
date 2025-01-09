import boto3
import os
import docker
import time

def deploy_docker_image_to_lambda(
    image_name: str,
    lambda_function_name: str,
    region_name: str = "us-east-1",
    role_name: str = "lambda_basic_execution",  # Replace with your Lambda execution role
    timeout: int = 30,
    memory_size: int = 128,
):
    """
    Deploys a Docker image to AWS Lambda.

    Args:
        image_name: The name of the Docker image to build and deploy.
        lambda_function_name: The name of the AWS Lambda function.
        region_name: The AWS region to deploy to.
        role_name: The name of the IAM role for Lambda execution.
        timeout: The timeout for the Lambda function (in seconds).
        memory_size: The memory allocated to the Lambda function (in MB).
    """

    # 1. Build the Docker image
    print(f"Building Docker image: {image_name}...")
    client = docker.from_env()
    try:
        image, build_logs = client.images.build(
            path=".", dockerfile="Dockerfile", tag=image_name
        )
        for log in build_logs:
            print(log)
    except docker.errors.BuildError as e:
        print(f"Error building Docker image: {e}")
        for log in e.build_log:
            if "stream" in log:
                print(log["stream"].strip())
        return

    # 2. Create an ECR repository (if it doesn't exist)
    ecr_client = boto3.client("ecr", region_name=region_name)
    repository_name = lambda_function_name.lower()  # ECR repo names must be lowercase

    try:
        ecr_client.describe_repositories(repositoryNames=[repository_name])
        print(f"ECR repository '{repository_name}' already exists.")
    except ecr_client.exceptions.RepositoryNotFoundException:
        print(f"Creating ECR repository: {repository_name}...")
        ecr_client.create_repository(repositoryName=repository_name)

    # 3. Tag the Docker image for ECR
    account_id = boto3.client("sts").get_caller_identity().get("Account")
    ecr_registry = f"{account_id}.dkr.ecr.{region_name}.amazonaws.com"
    ecr_image_uri = f"{ecr_registry}/{repository_name}:latest"

    print(f"Tagging image for ECR: {ecr_image_uri}...")
    image.tag(ecr_image_uri)

    # 4. Push the Docker image to ECR
    print(f"Pushing image to ECR: {ecr_image_uri}...")
    auth_config = ecr_client.get_authorization_token()
    username, password = (
        auth_config["authorizationData"][0]["authorizationToken"]
        .encode("utf-8")
        .decode()
        .split(":")
    )
    auth_config_dict = {"username": username, "password": password}

    for line in client.images.push(
        ecr_image_uri, auth_config=auth_config_dict, stream=True, decode=True
    ):
        print(line)

    # 5. Create or update the Lambda function
    lambda_client = boto3.client("lambda", region_name=region_name)

    try:
        response = lambda_client.get_function(FunctionName=lambda_function_name)
        print(f"Lambda function '{lambda_function_name}' already exists. Updating...")

        # Wait for the function to be in a 'Successful' state before updating
        while True:
            response = lambda_client.get_function(FunctionName=lambda_function_name)
            function_state = response["Configuration"]["State"]
            if function_state == "Successful":
                break
            print(f"Waiting for Lambda function to be in 'Successful' state (current state: {function_state})...")
            time.sleep(5)

        lambda_client.update_function_code(
            FunctionName=lambda_function_name,
            ImageUri=ecr_image_uri,
        )

        lambda_client.update_function_configuration(
            FunctionName=lambda_function_name,
            Timeout=timeout,
            MemorySize=memory_size,
        )

    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"Creating Lambda function: {lambda_function_name}...")
        lambda_client.create_function(
            FunctionName=lambda_function_name,
            Role=f"arn:aws:iam::{account_id}:role/{role_name}",
            Code={"ImageUri": ecr_image_uri},
            PackageType="Image",
            Timeout=timeout,
            MemorySize=memory_size,
        )

    print(f"Successfully deployed Docker image to Lambda function: {lambda_function_name}")

if __name__ == "__main__":
    # --- Configuration ---
    IMAGE_NAME = "my-python-lambda"  # Replace with your desired image name
    LAMBDA_FUNCTION_NAME = "MyPythonLambdaFunction"  # Replace with your Lambda function name
    REGION_NAME = "us-east-1"  # Replace with your desired AWS region
    ROLE_NAME = "lambda_basic_execution"  # Replace with your Lambda execution role name
    TIMEOUT = 60  # Lambda timeout in seconds
    MEMORY_SIZE = 256  # Lambda memory in MB
    # ---------------------

    deploy_docker_image_to_lambda(
        IMAGE_NAME, LAMBDA_FUNCTION_NAME, REGION_NAME, ROLE_NAME, TIMEOUT, MEMORY_SIZE
    )