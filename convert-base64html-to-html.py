import json
import base64

def save_html_from_base64(json_file_path):
    with open(json_file_path, 'r') as json_file:
        data = json.load(json_file)
        for index, entry in enumerate(data):
            for key, value in entry.items():
                if isinstance(value, str):
                    try:
                        decoded_data = base64.b64decode(value)
                        # You can change the file name or path as per your requirement
                        with open(f'output_{index}_{key}.html', 'wb') as html_file:
                            html_file.write(decoded_data)
                        print(f"HTML file for '{key}' in entry {index} saved successfully.")
                    except Exception as e:
                        print(f"Error decoding base64 data for '{key}' in entry {index}: {e}")

# Replace 'path/to/your/json/file.json' with the actual path to your JSON file
json_file_path = r"C:\Users\kalyan\Downloads\response_1715490519691.json"
save_html_from_base64(json_file_path)
