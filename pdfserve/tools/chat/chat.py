import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal  # Retaining for compatibility, though specific list/tuple/optional not needed with |

import pdfkit
from pydantic import AliasChoices, BaseModel, Field

logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    name: str | None = Field(default=None, description="The name of the sender or participant.")
    role: str | None = Field(
        default=None, description="The role of the message sender (e.g., 'user', 'agent', 'system')."
    )
    content: str = Field(
        ...,
        validation_alias=AliasChoices("content", "message"),
        description="The textual content of the message. Accepts 'content' or 'message' as input keys for validation. Serializes as 'content'.",
    )
    time: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("time", "timestamp", "datetime"),
        description="The timestamp of when the message was sent or recorded. Accepts 'time' or 'timestamp' as input keys for validation. Serializes as 'time'.",
    )
    direction: Literal["incoming", "outgoing"] | None = Field(
        default=None, description="The direction of the message relative to the primary user."
    )


HTML_TEMPLATE_HEADER = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat History</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0; /* Body margin is controlled by PDF options for the page itself */
            padding: 0;
            background-color: #f4f4f8;
            color: #333;
            /* display: flex; flex-direction: column; align-items: center; /* These might not be ideal for PDF page flow */
        }
        .chat-container {
            width: 100%; /* Takes width of the printable area */
            max-width: 800px; /* Still useful for HTML view, PDF will use page width */
            margin: 0 auto; /* Centering for HTML view */
            padding: 20px; /* Padding inside the container, distinct from page margins */
            background-color: #fff;
            border-radius: 12px; /* May not render in all PDF viewers or be desired */
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); /* Likely removed in print styles */
            display: flex;
            flex-direction: column;
            gap: 15px; /* This provides spacing BETWEEN message bubbles */
                      /* If more spacing is needed in PDF, increase this value, possibly in @media print */
        }
        .message {
            display: flex;
            flex-direction: column;
            max-width: 75%;
            word-wrap: break-word;
            page-break-inside: avoid !important;
            break-inside: avoid-page !important;
        }
        .message-bubble {
            padding: 12px 18px;
            border-radius: 20px;
            line-height: 1.5;
            display: inline-block; /* Help wkhtmltopdf keep this block together */
            width: auto; /* Allow it to size to content, constrained by parent .message */
            max-width: 100%; /* Ensure it doesn't overflow .message */
            page-break-inside: avoid !important;
            break-inside: avoid-page !important;
        }
        .message.outgoing {
            align-self: flex-end;
        }
        .message.outgoing .message-bubble {
            background-color: #007bff;
            color: white;
            border-bottom-right-radius: 5px;
        }
        .message.ingoing {
            align-self: flex-start;
        }
        .message.ingoing .message-bubble {
            background-color: #e9e9eb;
            color: #333;
            border-bottom-left-radius: 5px;
        }
        .message-author {
            font-weight: bold;
            font-size: 0.9em;
            margin-bottom: 4px;
            color: #555;
        }
        .message.outgoing .message-author {
             color: #f0f0f0;
             text-align: right;
        }
        .message-content {
            font-size: 1em;
            page-break-inside: avoid !important; /* Primary rule to prevent breaking within content */
            break-inside: avoid-page !important; /* Modern equivalent */
            display: block; /* Ensure it's treated as a block for break calculations */
        }
        .message-datetime {
            font-size: 0.75em;
            color: #777;
            margin-top: 6px;
            text-align: right;
        }
        .message.outgoing .message-datetime {
            color: #d0d0d0;
        }
        .message.ingoing .message-datetime {
            color: #888;
        }
        .no-datetime .message-datetime {
            display: none;
        }

        @media (max-width: 600px) {
            .chat-container {
                margin: 10px; /* For HTML view on small screens */
                padding: 15px;
            }
            .message {
                max-width: 85%;
            }
            .message-bubble {
                padding: 10px 15px;
            }
        }
        @media print {
            body {
                background-color: #fff !important; /* Ensure white background for printing */
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                margin: 0; /* Body margin is controlled by PDF options */
                padding: 0;
            }
            .chat-container {
                box-shadow: none !important;
                border: none; /* Remove border for print, or use a subtle one if preferred */
                margin: 0 !important; /* Container margin should be 0, page margins control spacing */
                padding: 0 !important; /* Container padding can be 0 if page margins are sufficient */
                                   /* Or keep some padding if you want space between page edge and first bubble */
                max-width: 100% !important; /* Use full printable width */
                border-radius: 0 !important; /* No rounded corners in PDF */
                gap: 20px !important; /* Increase gap slightly for PDF if needed */
            }
            .message, .message-bubble, .message-content {
                page-break-inside: avoid !important;
                break-inside: avoid-page !important;
            }
        }
    </style>
</head>
<body>
    <div class="chat-container">
"""

HTML_TEMPLATE_FOOTER = """
    </div>
</body>
</html>
"""


class ChatConverter:
    def __init__(
        self,
        messages: list[ChatMessage],
        output: str | Path | None = None,
        display_name_override: str | None = None,
        user_identifier_for_direction: str | None = None,
    ):
        """
        Initializes the ChatConverter.

        Args:
            messages: A list of ChatMessage objects.
            output: Base path/name for output files (e.g., "my_chat" or "exports/my_chat").
                    Extensions will be added automatically (.html, .pdf).
                    If None, files are not written to disk, only returned as BytesIO.
            display_name_override: Name to display for 'outgoing' messages. If None,
                                   the message's original name or role is used.
            user_identifier_for_direction: The name or role to identify as the 'user' for
                                           determining outgoing messages. If None, inference is attempted.
        """
        self.messages: list[ChatMessage] = messages
        self.output_path: Path | None = None
        if output:
            self.output_path = Path(output).with_suffix("")
        self._raw_html_content: str | None = None  # Cache for generated HTML

        self.display_name_override = display_name_override
        self._final_user_identifier_for_direction: str | None = user_identifier_for_direction

        if not self._final_user_identifier_for_direction and self.messages:
            # 1. Try to infer based on display_name_override matching a message author
            if self.display_name_override:
                for msg_item in self.messages:
                    msg_author = msg_item.name or msg_item.role
                    if msg_author and msg_author.lower() == self.display_name_override.lower():
                        self._final_user_identifier_for_direction = msg_author
                        break
            
            # 2. If still not found, try to infer based on common "user" or "me" roles/names
            if not self._final_user_identifier_for_direction:
                for msg_item in self.messages:
                    msg_author = msg_item.name or msg_item.role
                    if msg_author and msg_author.lower() in ["user", "me"]:
                        self._final_user_identifier_for_direction = msg_author
                        break

            # 3. If still not found, use the first message's author
            if not self._final_user_identifier_for_direction and self.messages: # Should be true if we are in this block
                # Ensure messages[0] exists and has an author
                first_msg_author = self.messages[0].name or self.messages[0].role
                if first_msg_author: # Check first_msg_author is not None
                    self._final_user_identifier_for_direction = first_msg_author
        
        logger.debug(f"Final user identifier for direction: {self._final_user_identifier_for_direction}")
        logger.debug(f"Display name override: {self.display_name_override}")

    def _determine_message_sender_info(self, msg: ChatMessage) -> tuple[str, str]:
        """
        Determines the effective direction and display author for a message.
        """
        message_actual_author = msg.name or msg.role or "Unknown" # Fallback for display if name/role are None

        eff_direction = "ingoing"  # Default direction

        # Use explicit direction if provided in the message
        if msg.direction:
            eff_direction = msg.direction.lower()
        elif (
            self._final_user_identifier_for_direction
            and message_actual_author.lower() == self._final_user_identifier_for_direction.lower()
        ):
            # Infer direction if not explicit and an identifier is set
            eff_direction = "outgoing"
        
        # Determine display author
        display_author = message_actual_author # Default to the message's own identifier

        if eff_direction == "outgoing" and self.display_name_override:
            display_author = self.display_name_override
            # If no display_name_override, display_author remains message_actual_author

        return eff_direction, display_author

    @staticmethod
    def _format_message_datetime(dt_obj: datetime | None) -> tuple[str, str]:
        formatted_datetime = ""
        message_extra_class = "no-datetime"
        if dt_obj:
            try:
                formatted_datetime = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                message_extra_class = ""
            except ValueError:
                formatted_datetime = str(dt_obj)
                message_extra_class = ""
        return formatted_datetime, message_extra_class

    def _generate_single_message_html(self, msg: ChatMessage) -> str:
        content = msg.content
        dt_obj = msg.time

        eff_direction, display_author = self._determine_message_sender_info(msg)

        content_safe = content.replace("<", "&lt;").replace(">", "&gt;")
        display_author_safe = display_author.replace("<", "&lt;").replace(">", "&gt;")

        formatted_datetime, message_extra_class = self._format_message_datetime(dt_obj)

        return f"""
            <div class="message {eff_direction} {message_extra_class}">
                <div class="message-bubble">
                    <div class="message-author">{display_author_safe}</div>
                    <div class="message-content">{content_safe}</div>
                    <div class="message-datetime">{formatted_datetime}</div>
                </div>
            </div>"""

    def _generate_html_content(self) -> str:
        if self._raw_html_content is None:  # Generate and cache
            if not self.messages:
                logger.info("No messages to generate HTML from. Generating empty chat HTML.")
                # Produce a valid empty chat structure
                self._raw_html_content = HTML_TEMPLATE_HEADER + HTML_TEMPLATE_FOOTER
            else:
                messages_html_parts: list[str] = []
                for msg_obj in self.messages:
                    messages_html_parts.append(self._generate_single_message_html(msg_obj))
                self._raw_html_content = HTML_TEMPLATE_HEADER + "".join(messages_html_parts) + HTML_TEMPLATE_FOOTER
        return self._raw_html_content

    def _prepare_output_path(self, output: str | Path | None, suffix: str) -> Path | None:
        """
        Determines the final output path for a file.
        Uses the 'output' argument if provided, otherwise falls back to 'self.output_path'.
        Ensures parent directories exist.
        """
        final_path: Path | None = None
        if output:  # Method-specific output path takes precedence
            final_path = Path(output).with_suffix(suffix)
        elif self.output_path:  # Fallback to instance-level output path
            final_path = self.output_path.with_suffix(suffix)

        if final_path:
            final_path.parent.mkdir(parents=True, exist_ok=True)
        return final_path

    def to_html(self, output: str | Path | None = None) -> tuple[Path | None, io.BytesIO]:
        """
        Generates HTML content from chat messages.

        Args:
            output: Optional path to save the HTML file. If None, uses instance's output path.
                    If both are None, file is not saved.

        Returns:
            A tuple containing the Path to the saved HTML file (or None) and an io.BytesIO object
            with the HTML content.
        """
        html_content_str = self._generate_html_content()
        html_bytes = html_content_str.encode("utf-8")
        html_file_like = io.BytesIO(html_bytes)
        html_file_like.seek(0)  # Reset stream position for reading

        final_output_path = self._prepare_output_path(output, ".html")

        if final_output_path:
            with open(final_output_path, "wb") as f:
                f.write(html_bytes)
            logger.info(f"Chat history successfully written to {final_output_path}")

        return final_output_path, html_file_like

    def to_pdf(self, output: str | Path | None = None) -> tuple[Path | None, io.BytesIO]:
        """
        Generates a PDF document from chat messages.

        Args:
            output: Optional path to save the PDF file. If None, uses instance's output path.
                    If both are None, file is not saved.

        Returns:
            A tuple containing the Path to the saved PDF file (or None) and an io.BytesIO object
            with the PDF content (empty if generation fails or no messages).
        """
        final_output_path = self._prepare_output_path(output, ".pdf")
        pdf_file_like = io.BytesIO()  # Default to empty

        html_content_str = self._generate_html_content()

        if not self.messages:
            raise ValueError("No messages to convert to PDF. Ensure chat data is provided.")
        pdf_bytes: bytes | None = None
        options = {
            "encoding": "UTF-8",
            "custom-header": [("Accept-Encoding", "gzip")],
            "no-outline": None,
            "enable-local-file-access": None,
            "margin-top": "20mm",
            "margin-right": "15mm",
            "margin-bottom": "20mm",
            "margin-left": "15mm",
            "print-media-type": None,
            "load-error-handling": "ignore",
        }
        pdf_bytes_or_bool = pdfkit.from_string(html_content_str, output_path=False, options=options)
        if not isinstance(pdf_bytes_or_bool, bytes) or not pdf_bytes_or_bool:
            raise ValueError("no pdf bytes")
        pdf_bytes = pdf_bytes_or_bool

        pdf_file_like = io.BytesIO(pdf_bytes)
        pdf_file_like.seek(0)
        if final_output_path:
            with open(final_output_path, "wb") as f:
                f.write(pdf_bytes)
                logger.info(f"Chat PDF successfully written to {final_output_path}")
        return final_output_path, pdf_file_like
