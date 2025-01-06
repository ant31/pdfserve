import re


def parse_split_pages(split_input) -> list[tuple[int, int]]:
    """
    Parse the split input string into a list of tuples with the start and end page
    """
    # check format if split_input using regexp
    split_input = split_input.replace(" ", "")
    if not re.match(r"^\d+(-\d+)?(,\d+(-\d+)?)*$", split_input):
        raise ValueError("Invalid split format")

    split_input = split_input.replace(" ", "").split(",")
    split_pages = []
    for part in split_input:
        if "-" in part:
            start, end = part.split("-")
            if not start.isdigit() or not end.isdigit():
                raise ValueError("Invalid split format, start and end must be numbers")
            if int(start) > int(end):
                raise ValueError("Invalid split format start page is greater than end page")
            split_pages.append((int(start), int(end)))
        else:
            split_pages.append((int(part), int(part)))
    return split_pages
