import logging
import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
)
from fastapi.responses import FileResponse

from pdfserve.tools.chat.chat import ChatConverter, ChatMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


# The ChatConversionRequest model is no longer needed as the body will be list[ChatMessage] directly.
# And other fields are moved to query parameters.


def _cleanup_file(file_path: str | Path):
    """Safely delete a file. Errors will propagate."""
    p = Path(file_path)
    if p.exists():
        p.unlink()
        logger.debug(f"Successfully cleaned up temporary file: {file_path}")
    else:
        logger.debug(f"Temporary file not found for cleanup (already deleted?): {file_path}")


@router.post(
    "/chat",
    response_class=FileResponse,
    summary="Convert chat history to PDF or HTML.",
    response_description="The generated PDF or HTML file containing the chat history.",
    responses={
        200: {
            "description": "The generated file (PDF or HTML).",
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "text/html": {"schema": {"type": "string"}},
            },
        },
        422: {"description": "Validation error (e.g., invalid JSON payload structure or types)."},
        500: {"description": "Internal server error (e.g., file generation failed)."},
    },
)
async def export_chat_document(
    chat_data: list[ChatMessage],
    background_tasks: BackgroundTasks,
    display_name_override: str | None = Query(
        None,
        alias="display_name",
        description="Name to display for 'outgoing' messages. If not set, the message's original name/role is used.",
    ),
    user_identifier_for_direction: str | None = Query(
        None,
        alias="user_identifier",
        description="Identifier (name or role) to determine 'outgoing' messages. If not set, inference is attempted.",
    ),
    output: str = Query(
        "chat_export",
        alias="output",
        description="Desired base filename for the output file (suffix .pdf or .html will be added).",
    ),
    fmt: str = Query(
        "pdf",
        alias="format",
        description="Output format: 'pdf' or 'html'.",
        enum=["pdf", "html"],
    ),
):
    """
    Converts chat history (from a JSON request body as a list of ChatMessage objects) to a PDF or HTML document.

    - **Request Body**: A JSON array of chat message objects. Each object should conform to the ChatMessage schema.
        Example:
        ```json
        [
            {
                "name": "UserX",
                "role": "user",
                "message": "Hello, how are you?",
                "timestamp": "2024-05-27T10:00:00Z"
            },
            {
                "name": "SupportAgent",
                "role": "agent",
                "message": "I am fine, thank you! How can I help you today?",
                "timestamp": "2024-05-27T10:00:30Z"
            }
        ]
        ```
    - **display_name** (query parameter, optional): The name to display for 'outgoing' messages.
    - **user_identifier** (query parameter, optional): Identifier (name or role) for 'outgoing' messages.
    - **output** (query parameter, optional, default: "chat_export"): Desired base filename for the output file.
    - **fmt** (query parameter, optional, default: "pdf"): Desired output format ('pdf' or 'html').
    """
    output_base_filename = output
    file_suffix = f".{fmt.lower()}"
    output_filename_with_suffix = output_base_filename
    if not output_filename_with_suffix.lower().endswith(file_suffix):
        output_filename_with_suffix = Path(output_base_filename).stem + file_suffix

    logger.info(f"Requested format: {fmt}, Output filename: {output_filename_with_suffix}")
    logger.debug(f"API - Display Name Override: {display_name_override}")
    logger.debug(f"API - User Identifier for Direction: {user_identifier_for_direction}")

    temp_file_path: Path | None = None

    try:
        converter = ChatConverter(
            messages=chat_data,
            display_name_override=display_name_override,
            user_identifier_for_direction=user_identifier_for_direction,
        )

        with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False) as tmp_file:
            temp_file_path = Path(tmp_file.name)
        background_tasks.add_task(_cleanup_file, temp_file_path)
        logger.debug(f"Created temporary file placeholder: {temp_file_path} for format {fmt}")

        saved_file_path: Path | None = None
        media_type: str = ""

        if fmt == "pdf":
            saved_file_path, _ = converter.to_pdf(output=temp_file_path)
            media_type = "application/pdf"
        elif fmt == "html":
            saved_file_path, _ = converter.to_html(output=temp_file_path)
            media_type = "text/html"
        else:
            # Should not happen due to Query(enum=...)
            raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

        if not saved_file_path:
            logger.error(f"Failed to generate or save {fmt.upper()} to {temp_file_path}.")
            raise HTTPException(status_code=500, detail=f"{fmt.upper()} generation or saving failed.")

        logger.info(
            f"Successfully generated {fmt.upper()}: {saved_file_path} (will be served as {output_filename_with_suffix})"
        )
        return FileResponse(
            str(saved_file_path),
            media_type=media_type,
            filename=output_filename_with_suffix,
        )
    except HTTPException:
        if temp_file_path and not any(
            task.func == _cleanup_file and task.args[0] == temp_file_path for task in background_tasks.tasks
        ):
            _cleanup_file(temp_file_path)
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred in export_chat_document: {e}", exc_info=True)
        if temp_file_path:
            _cleanup_file(temp_file_path)
        raise HTTPException(
            status_code=500, detail=f"An internal server error occurred: {str(e) or type(e).__name__}"
        ) from e
