import docker
import os

def run_docker_container(image_name: str, container_name: str, env_file_path: str, tag: str = "latest"):
    try:
        # Load environment variables from .env file
        if os.path.exists(env_file_path):
            print(f"Loading environment variables from {env_file_path}")
            with open(env_file_path, 'r') as env_file:
                environment = {}
                for line in env_file:
                    if line.strip() and not line.startswith('#'):
                        key, value = line.strip().split('=', 1)
                        environment[key] = value
        else:
            raise FileNotFoundError(f"File not found: {env_file_path}")

        # Initialize Docker client
        client = docker.from_env()

        # Full image name with tag
        image_with_tag = f"{image_name}:{tag}"

        # Run container with specified image, name, and environment variables
        print(f"Running container {container_name} from image {image_with_tag}...")
        container = client.containers.run(
            image=image_with_tag,
            name=container_name,
            environment=environment,
            detach=True,  # Run container in the background
        )

        print(f"Container {container_name} is running.")
        return container

    except Exception as e:
        print(f"Error running container: {e}")

if __name__ == "__main__":
    docker_image_name = input("Enter your docker image name: ")
    container_name = input("Enter you docker container name: ")
    env_file_path = input("Enter the path for .env file: ")

    run_docker_container(docker_image_name, container_name, env_file_path)
