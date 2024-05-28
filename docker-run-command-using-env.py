def parse_env_file(file_path):
    env_vars = {}
    with open(file_path) as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip('"')
                env_vars[key.strip()] = value.strip()
    return env_vars

def generate_docker_run_command(image_name, env_file, container_name):
    env_vars = parse_env_file(env_file)
    env_flags = ' '.join([f'-e {key}="{value}"' for key, value in env_vars.items()])
    command = f'docker run --name {container_name} {env_flags} {image_name}'
    return command

if __name__ == "__main__":
    docker_image_name = input("Enter your docker image name: ")
    container_name = input("Enter you docker container name: ")
    env_file_path = input("Enter the path for .env file: ")

    docker_command = generate_docker_run_command(docker_image_name, env_file_path, container_name)
    print(docker_command)
