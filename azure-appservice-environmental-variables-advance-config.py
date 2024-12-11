import os
import json
from dotenv import dotenv_values

def parse_env_file(env_path):
    """
    Parses a .env file and converts it into a JSON list of objects.
    :param env_path: Path to the .env file
    :return: JSON formatted list of environment variable dictionaries
    """
    # Load environment variables from the file
    if not os.path.exists(env_path):
        raise FileNotFoundError(f".env file not found at: {env_path}")
    
    env_vars = dotenv_values(env_path)  # Parse .env file
    formatted_vars = []

    for key, value in env_vars.items():
        formatted_vars.append({
            "name": key,
            "value": value,
            "slotSetting": False  # Default slotSetting to False
        })

    return formatted_vars

# Example usage
if __name__ == "__main__":
    env_path = ".env"  # Replace with the path to your .env file
    try:
        env_list = parse_env_file(env_path)
        print(json.dumps(env_list, indent=2))  # Print formatted JSON
    except Exception as e:
        print(f"Error: {e}")
