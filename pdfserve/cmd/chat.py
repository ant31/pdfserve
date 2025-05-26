import json
import logging
from pathlib import Path

import click
from pydantic import ValidationError

from pdfserve.tools.chat.chat import ChatConverter, ChatMessage

logger = logging.getLogger(__name__)


def _process_chat_input(ctx: click.Context, input_str: str) -> tuple[list[ChatMessage] | None, Path | None, str]:
    """
    Processes the input string to determine if it's a file or JSON string,
    loads/parses messages, and returns processed data.
    """
    messages: list[ChatMessage] | None = None
    input_file: Path | None = None
    default_base_name = "chat_output"
    input_path = Path(input_str)

    if input_path.is_file():
        input_file = input_path.resolve()
        default_base_name = input_file.stem
        logger.info(f"Input is file: {input_file}")
    else:
        logger.info("Input is treated as a JSON string.")
        try:
            parsed_json = json.loads(input_str)
            if not isinstance(parsed_json, list):
                ctx.fail("Invalid JSON string: Input must be a JSON array of chat messages.")
            messages = [ChatMessage.model_validate(item) for item in parsed_json]
            logger.info("Successfully parsed chat data from JSON string.")
        except json.JSONDecodeError as e:
            ctx.fail(f"Input '{input_str}' is not an existing file and not a valid JSON string. Parse error: {e}")
        except ValidationError as e:
            ctx.fail(f"Invalid chat message format in JSON string: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing JSON string input: {e}", exc_info=True)
            ctx.fail(f"Unexpected error processing JSON string input: {str(e) or type(e).__name__}")
    return messages, input_file, default_base_name


def _prepare_output_base_path(ctx: click.Context, output_base_name_arg: str | None, default_base_name: str) -> Path:
    """Determines and prepares the output base path."""
    output_base_path: Path
    if output_base_name_arg:
        output_base_path = Path(output_base_name_arg)
    else:
        output_base_path = Path.cwd() / default_base_name

    if output_base_path.parent != Path("."):
        try:
            output_base_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            ctx.fail(f"Could not create output directory {output_base_path.parent}: {e}")
    return output_base_path


@click.command("chat")
@click.option(
    "--input",
    "-i",
    "input_str",
    required=True,
    help="Input JSON chat data, either as a file path or a JSON string.",
)
@click.option(
    "--output",
    "-o",
    "output_base_name_arg",
    default=None,
    help="Base name for the output HTML and PDF files (e.g., 'mydialog'). "
    "If not provided, it's derived from the input file name or "
    "defaults to 'chat_output' if input is a JSON string.",
)
@click.option(
    "--current-user-name",
    "-u",
    default="Me",
    show_default=True,
    help="Name to display for 'outgoing' messages.",
)
@click.pass_context
def chat_cli(ctx: click.Context, input_str: str, output_base_name_arg: str | None, current_user_name: str) -> None:
    """Converts chat history from JSON to HTML and PDF files."""
    messages, input_file, default_base_name = _process_chat_input(ctx, input_str)
    output_path_for_converter = _prepare_output_base_path(ctx, output_base_name_arg, default_base_name)

    # ChatConverter now expects messages to be loaded by the caller.
    # _process_chat_input already handles loading messages if input_str is a file or parsing if it's a string.
    # If input_file is not None, messages would be None from _process_chat_input.
    # We need to load them here if that's the case.

    if input_file and not messages:  # If input was a file, messages need to be loaded.
        # Re-using the logic from the now-removed _load_messages_from_file in ChatConverter,
        # or a similar utility if it were made public/static.
        # For now, let's inline a simplified version of that loading logic.
        try:
            with open(input_file, encoding="utf-8") as f:
                data_to_parse = json.load(f)
            if not isinstance(data_to_parse, list):
                ctx.fail(f"JSON content in {input_file} is not a list.")
            messages = [ChatMessage.model_validate(item) for item in data_to_parse]
        except json.JSONDecodeError as e:
            ctx.fail(f"Error decoding JSON from file {input_file}: {e}")
        except ValidationError as e:
            ctx.fail(f"Error validating chat data from file {input_file}: {e}")
        except OSError as e:
            ctx.fail(f"Error reading file {input_file}: {e}")
        except Exception as e:  # Should be more specific if possible
            ctx.fail(f"Unexpected error loading messages from {input_file}: {e}")

    converter = ChatConverter(
        messages=messages,  # messages are now guaranteed to be loaded if input was valid
        output=output_path_for_converter,  # Renamed from output_base_path
        current_user_name=current_user_name,
    )

    # Generate HTML
    # The 'output' argument to to_html/to_pdf now overrides the instance 'output' if provided.
    # Since we've set the instance 'output', we don't need to pass it again here
    # unless we specifically want a different path for HTML vs PDF from the base.
    # For simplicity, we'll rely on the instance 'output' which will derive .html and .pdf.
    html_output_path, _ = converter.to_html()

    if not html_output_path:
        # This implies output_path_for_converter was set, but writing failed.
        logger.error(f"Failed to generate HTML file at {output_path_for_converter.with_suffix('.html')}")
        ctx.fail("HTML generation failed.")
    else:
        click.echo(f"Successfully generated HTML: {html_output_path}")

    # Convert HTML to PDF
    pdf_output_path, _ = converter.to_pdf()

    if not pdf_output_path:
        logger.warning(f"Failed to convert to PDF. HTML file might be available at {html_output_path}")
        click.echo(
            f"Warning: PDF generation failed. HTML file might be available at {html_output_path}",
            err=True,
        )
    else:
        click.echo(f"Successfully generated PDF: {pdf_output_path}")

    ctx.exit(0)
