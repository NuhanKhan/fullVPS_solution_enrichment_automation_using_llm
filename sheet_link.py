import re

SHEET_ID_IN_LINK = re.compile(r"/spreadsheets/(?:u/\d+/)?d/([A-Za-z0-9_-]+)")
GID_IN_LINK = re.compile(r"[?#&]gid=(\d+)")
BARE_SHEET_ID = re.compile(r"^[A-Za-z0-9_-]{25,}$")


def parse_sheet_link(link: str) -> tuple[dict | None, str | None]:
    """Read the sheet id and the tab id (gid) out of a Google Sheets link, or accept a bare sheet id.

    Returns ({"sheet_id": str, "gid": int | None}, None) or (None, error).
    """

    link = link.strip()

    if BARE_SHEET_ID.match(link):
        return ({"sheet_id": link, "gid": None}, None)

    match = SHEET_ID_IN_LINK.search(link)
    if not match:
        return (None, f"not a Google Sheets link: {link!r}")

    gid = None
    gid_match = GID_IN_LINK.search(link)
    if gid_match:
        gid = int(gid_match.group(1))

    return ({"sheet_id": match.group(1), "gid": gid}, None)


def pick_input_tab(tabs: list[dict], gid: int | None, input_tab: str | None) -> tuple[str | None, str | None]:
    """Choose the input tab: --input-tab first, then the tab in the link, then the first tab.

    tabs is [{"title": str, "sheetId": int}, ...] in sheet order.
    """

    if not tabs:
        return (None, "the sheet has no tabs")

    titles = [tab["title"] for tab in tabs]

    if input_tab is not None:
        if input_tab not in titles:
            return (None, f"no tab named {input_tab!r}, tabs are: {', '.join(titles)}")
        return (input_tab, None)

    if gid is not None:
        for tab in tabs:
            if tab["sheetId"] == gid:
                return (tab["title"], None)
        return (None, f"the link points to tab id {gid}, which this sheet does not have")

    return (titles[0], None)
