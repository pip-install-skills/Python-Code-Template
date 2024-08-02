from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from dotenv import load_dotenv
import base64
import os

load_dotenv()

load_dotenv()

SENDGRID_API_KEY = os.getenv("MAIL_API_KEY")

def send_email(to_email, subject, content, attachments=None):
    message = Mail(
        from_email=os.getenv("MAIL_USERNAME"),
        to_emails=to_email,
        subject=subject,
        html_content=content)

    if attachments:
        for attachment in attachments:
            with open(attachment['file_path'], 'rb') as f:
                data = f.read()
                encoded_file = base64.b64encode(data).decode()

            attached_file = Attachment(
                FileContent(encoded_file),
                FileName(attachment['file_name']),
                FileType(attachment['file_type']),
                Disposition('attachment')
            )
            message.attachment = attached_file

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code == 202:  # 202 indicates email was accepted by SendGrid
            return True
        else:
            print(f"Failed to send email. Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return False

# Example usage:
# attachments = [
#     {
#         'file_path': 'path/to/your/file.txt',
#         'file_name': 'file.txt',
#         'file_type': 'text/plain'
#     },
#     {
#         'file_path': 'path/to/your/image.png',
#         'file_name': 'image.png',
#         'file_type': 'image/png'
#     }
# ]
# send_email('recipient@example.com', 'Subject', 'Email content', attachments)
