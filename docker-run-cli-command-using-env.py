import os

def load_env_variables(dotenv_path):
    """Load environment variables from a .env file and return them."""
    env_vars = {}
    
    # Open and read the .env file
    with open(dotenv_path) as f:
        for line in f:
            # Ignore empty lines and comments (lines starting with '#')
            line = line.strip()
            if line and not line.startswith("#"):
                # Split the line into key and value at the first '='
                key, value = line.split('=', 1)
                env_vars[key] = value
    
    return env_vars

def generate_docker_command(image_name, container_name, env_vars):
    """Generate the docker run command with environment variables."""
    command = f"docker run -d --name {container_name}"
    
    # Add environment variables as -e flags
    for key, value in env_vars.items():
        command += f" -e {key}={value}"
    
    # Add the image name to the command
    command += f" {image_name}"
    
    return command

def main():
    """Main function to get user input and generate docker command."""
    # Get user input for the image name, .env path, and container name
    image_name = input("Enter the Docker image name: ")
    dotenv_path = input("Enter the path to the .env file: ")
    container_name = input("Enter the desired container name: ")

    # Load environment variables from the provided .env path
    env_vars = load_env_variables(dotenv_path)

    # Check if we have any environment variables in the .env file
    if not env_vars:
        print("No environment variables found in the provided .env file.")
        return

    # Generate and print the docker run command
    docker_command = generate_docker_command(image_name, container_name, env_vars)
    print(f"\nGenerated Docker run command:\n{docker_command}")

if __name__ == "__main__":
    main()
